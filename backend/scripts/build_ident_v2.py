"""Build civil_collection__ident_v2: ident_v1 with the CPC label repair checked against the official Pakistan Code text.

ISOLATED. Writes ONE new collection and nothing else: ident_v1, the base collection and the active collection constant
(cpc_provisions.IDENT_COLLECTION) are not touched -- switching is a separate, approved step.

The diff it applies is FROZEN: evals/drafter_v2/ident_v2_dryrun/ident_v2_metadata_diff.v3.json, applied only when its
sha256 equals the one in ident_v2_metadata_diff.v3.lock.json (and its counts match the lock). Classes A and B only;
REVIEW rows are never applied. Every chunk keeps its id, document and embedding; only the planned metadata of the planned
chunks changes:
  provision_label / rule   the official rule (class A: "Order N (rule not shown)" chunks)
  also_rules               later rules the chunk also holds (";"-joined)
  rule_spans               "Order IX Rule 12@0;Order IX Rule 13@612": where each rule's text begins in the chunk
                           (cpc_provisions.split_rules reads it)
  ident_version            "ident-v2" on changed chunks; ident_basis "official_pakistancode_2026-10-15"

Safety:
  * an existing ident_v2 is NEVER overwritten or removed -- the run refuses before reading anything else;
  * the collection is created with this run's random `build_run_id`; the run may delete ONLY a collection it created
    itself and that carries that id (after a failed verification or an error mid-build). Nothing else is ever deleted.

  python scripts/build_ident_v2.py            # read-only checks (default) -- nothing written
  python scripts/build_ident_v2.py --build    # checks, build, verify; removes its OWN ident_v2 if verification fails

Stop the backend first (embedded Chroma)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]

SOURCE = "civil_collection__ident_v1"
TARGET = "civil_collection__ident_v2"
DIFF = BACKEND / "evals/drafter_v2/ident_v2_dryrun/ident_v2_metadata_diff.v3.json"
BASIS = "official_pakistancode_2026-10-15"
BATCH = 500


class Refused(Exception):
    """A check failed: nothing was written."""


def _read_all(col, embeddings: bool) -> dict:
    out = {}
    total = col.count()
    inc = ["documents", "metadatas"] + (["embeddings"] if embeddings else [])
    for off in range(0, total, BATCH):
        got = col.get(include=inc, limit=BATCH, offset=off)
        embs = got["embeddings"] if embeddings else [None] * len(got["ids"])
        for i, d, m, e in zip(got["ids"], got["documents"], got["metadatas"], embs):
            out[i] = (d, m, None if e is None else [float(x) for x in e])
    return out


def fingerprint(rows: dict) -> str:
    h = hashlib.sha256()
    for i in sorted(rows):
        d, m, e = rows[i]
        h.update(i.encode()); h.update((d or "").encode("utf-8"))
        h.update(json.dumps(m, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        if e is not None:
            h.update(json.dumps(e).encode())
    return h.hexdigest()


def load_frozen_diff(path: Path) -> tuple[dict, dict]:
    """(diff, lock). Refused unless the file's sha256 and class counts equal its lock's."""
    lock_path = path.with_name(path.stem + ".lock.json")
    if not lock_path.exists():
        raise Refused(f"no lock file {lock_path.name}: only a frozen diff may be applied")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != lock.get("sha256"):
        raise Refused(f"{path.name} sha256 {sha[:12]}... != locked {str(lock.get('sha256'))[:12]}...: the diff changed")
    diff = json.loads(raw.decode("utf-8"))
    cls = Counter(r["class"].split(":")[0] for r in diff["changes_and_reviews"])
    got = {"A": cls["A"], "B": cls["B"], "REVIEW": cls["REVIEW"], "changes": cls["A"] + cls["B"]}
    if got != lock.get("counts") or got != diff.get("counts"):
        raise Refused(f"class counts {got} != locked {lock.get('counts')}")
    return diff, lock


def rule_offsets(doc: str, labels: list[str]) -> list[int] | None:
    """Offset where each label's text begins: 0 for the first, then the heading of each later rule (number + ".")
    found in order, moved back over a short group heading (cpc_provisions.group_heading_start). None if any
    later rule's heading cannot be found after the previous one."""
    from app.ai import cpc_provisions as cp
    offs, pos = [0], 0
    for lab in labels[1:]:
        num = re.match(r"Order\s+[IVXLC]+\s+Rule\s+(\d+[A-Z]?)$", lab).group(1)
        pat = re.compile(rf"(?:(?<=\s)|^)(?:\d{{1,2}}\s*\[\s*|\[\s*)?(?<![\d.]){re.escape(num)}\s*\.\s*[A-Z]")
        found = [m.start() for m in pat.finditer(doc) if m.start() > pos]
        if not found:
            return None
        at = cp.group_heading_start(doc, found[0])
        if at <= pos:
            return None
        offs.append(at)
        pos = found[0]
    return offs


def plan_and_check(v1: dict, diff: dict, counts: dict) -> tuple[dict, list[str], dict]:
    """(planned metadata per id, problems, stats). problems == [] means the build may proceed."""
    from app.ai import cpc_provisions as cp
    problems, plan, stats = [], {}, Counter()
    rows = diff["changes_and_reviews"]
    ids = [r["chunk_id"] for r in rows]
    if len(ids) != len(set(ids)):
        problems.append("duplicate chunk ids in the diff")
    for r in rows:
        k = r["class"].split(":")[0]
        if k not in ("A", "B"):
            stats["review_rows_skipped"] += 1
            continue
        cid = r["chunk_id"]
        if cid not in v1:
            problems.append(f"{cid}: not in {SOURCE}"); continue
        doc, md, _ = v1[cid]
        if md.get("provision_label") != r["current_label"]:
            problems.append(f"{cid}: ident_v1 label is {md.get('provision_label')!r}, the diff expected {r['current_label']!r}")
            continue
        labels = [r["new_label"], *r["also_rules"]]
        official = [x for x in (r["official_rules_spanned"] or []) if x.startswith("Order ") and " Rule " in x]
        if labels != official:
            problems.append(f"{cid}: planned {labels} != official span {official}"); continue
        new = dict(md)
        new.update(provision_label=r["new_label"], rule=re.search(r"Rule\s+(\S+)$", r["new_label"]).group(1),
                   ident_version="ident-v2", ident_basis=BASIS)
        if r["also_rules"]:
            offs = rule_offsets(doc, labels)
            if offs is None:
                problems.append(f"{cid}: a rule heading for {labels[1:]} not found in the chunk text"); continue
            spans = ";".join(f"{lab}@{o}" for lab, o in zip(labels, offs))
            pieces = cp.split_rules(doc, r["new_label"], spans)
            if [p[0] for p in pieces] != labels:
                problems.append(f"{cid}: split_rules gives {[p[0] for p in pieces]} for {labels}"); continue
            if "".join(t for _, t in pieces) != doc:
                problems.append(f"{cid}: the split pieces do not rebuild the chunk text"); continue
            bad = [lab for lab, text in pieces[1:]
                   if not re.search(rf"(?<![\d.]){re.escape(re.search(r'Rule\s+(\S+)$', lab).group(1))}\s*\.", text[:200])]
            if bad:
                problems.append(f"{cid}: the {bad} slice does not open with its heading"); continue
            new.update(also_rules=";".join(r["also_rules"]), rule_spans=spans)
            stats["chunks_with_rule_spans"] += 1
        plan[cid] = new
        stats[f"class_{k}"] += 1
    stats["planned_changes"] = len(plan)
    if stats["class_A"] != counts["A"] or stats["class_B"] != counts["B"] or len(plan) != counts["changes"]:
        problems.append(f"planned A={stats['class_A']} B={stats['class_B']} total={len(plan)}, locked {counts}")
    return plan, problems, stats


# ── embeddings: measured tolerance (2026-10-15) ─────────────────────────────
# The first live build failed "every embedding byte-identical": writing unit-length vectors into a cosine collection
# changes ~5% of them by ONE unit in the last float32 place, and a second copy changes others again (measured on an
# isolated copy -- evals/drafter_v2/ident_v2_dryrun/EMBEDDING_ROUNDTRIP_FINDINGS.md). What must hold instead:
#   1. every component within 1 ULP of float32 (anything larger is a real change);
#   2. EXACT top-10 neighbours of every stored vector unchanged (measured: 4,648 / 4,648);
#   3. the new approximate (HNSW) index agrees with exact search at least as often as the source's.
MAX_ULPS = 1
TOP_K = 10
# Pre-registered gate (evals/drafter_v2/ident_v2_dryrun/PREREGISTERED_GATE.md, locked 2026-10-15 BEFORE any further
# live build): the lowest of 10 measured rebuilds (4,579) minus 10. The script refuses to run if the gate file no
# longer matches its lock.
HNSW_FLOOR = 4569
GATE = BACKEND / "evals/drafter_v2/ident_v2_dryrun/PREREGISTERED_GATE.md"


def check_gate_lock(gate: Path = GATE) -> dict:
    """The locked gate, or Refused: the numbers here are only valid while the gate file is the one locked."""
    lock_path = gate.with_name(gate.stem + ".lock.json")
    if not gate.exists() or not lock_path.exists():
        raise Refused("pre-registered gate or its lock is missing")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    sha = hashlib.sha256(gate.read_bytes()).hexdigest()
    if sha != lock.get("sha256"):
        raise Refused(f"PREREGISTERED_GATE.md changed (sha {sha[:12]}... != locked {str(lock.get('sha256'))[:12]}...)")
    return lock


def _exact_topk(embs):
    import numpy as np
    sims = embs @ embs.T
    return np.argsort(-sims, axis=1, kind="stable")[:, :TOP_K]


def _hnsw_agreement(col, ids: list[str], embs, exact) -> int:
    pos = {x: j for j, x in enumerate(ids)}
    agree = 0
    for off in range(0, len(ids), 200):
        got = col.query(query_embeddings=embs[off:off + 200].tolist(), n_results=TOP_K, include=[])["ids"]
        agree += sum(set(pos[x] for x in g) == set(exact[off + k]) for k, g in enumerate(got))
    return agree


def embedding_tolerance(src, dst, v1: dict, v2: dict, floor: int = None) -> tuple[list[str], dict]:
    floor = HNSW_FLOOR if floor is None else floor
    import numpy as np
    ids = sorted(set(v1) & set(v2))
    e1 = np.asarray([v1[i][2] for i in ids], dtype=np.float32)
    e2 = np.asarray([v2[i][2] for i in ids], dtype=np.float32)
    problems = []
    if e1.shape != e2.shape:
        return [f"embedding shapes differ: {e1.shape} vs {e2.shape}"], {}
    ulps = np.abs(e2.astype(np.float64) - e1) / np.spacing(np.abs(e1)).astype(np.float64)
    worst = ulps.max(axis=1)
    over = [ids[j] for j in np.nonzero(worst > MAX_ULPS)[0]]
    problems += [f"{i}: embedding moved more than {MAX_ULPS} ULP" for i in over[:20]]
    t1, t2 = _exact_topk(e1), _exact_topk(e2)
    knn_same = int(sum(np.array_equal(a, b) for a, b in zip(t1, t2)))
    if knn_same != len(ids):
        problems.append(f"exact top-{TOP_K} neighbours changed for {len(ids) - knn_same} of {len(ids)} vectors")
    a_src, a_dst = _hnsw_agreement(src, ids, e1, t1), _hnsw_agreement(dst, ids, e1, t1)
    # Pre-registered gate B (PREREGISTERED_GATE.md): "new >= source" compared two draws of a random process -- the
    # UNCHANGED source rebuilt 5x measured 4,580-4,595 -- so the floor is fixed from that distribution instead.
    if a_dst < floor:
        problems.append(f"new HNSW index agrees with exact search {a_dst} / {len(ids)}, below the pre-registered "
                        f"floor {floor}")
    facts = {"vectors": len(ids), "byte_identical": int((worst == 0).sum()), "within_1_ulp_not_identical":
             int(((worst > 0) & (worst <= MAX_ULPS)).sum()), "over_tolerance": len(over),
             "max_ulps": float(worst.max()) if len(ids) else 0.0,
             "max_abs_delta": float(np.abs(e2.astype(np.float64) - e1).max()) if len(ids) else 0.0,
             "exact_topk_identical": knn_same, "hnsw_agreement_source": a_src, "hnsw_agreement_new": a_dst,
             "hnsw_floor": floor}
    return problems, facts


# ── the only write path ──────────────────────────────────────────────────────

def _names(client) -> list[str]:
    return [getattr(c, "name", c) for c in client.list_collections()]


def remove_own(client, run_id: str, created_here: bool) -> bool:
    """Delete TARGET only if THIS run created it and it carries THIS run's id. True if deleted."""
    if not created_here or TARGET not in _names(client):
        return False
    col = client.get_collection(TARGET)
    if (col.metadata or {}).get("build_run_id") != run_id:
        return False
    client.delete_collection(TARGET)
    return True


def build_and_verify(client, src, v1: dict, plan: dict, run_id: str, floor: int = None) -> tuple[list[str], dict]:
    """(post-build problems, facts). Refuses if TARGET exists; removes only its own collection on failure."""
    if TARGET in _names(client):
        raise Refused(f"{TARGET} already exists -- never overwritten or removed by this script")
    created_here = False
    try:
        dst = client.create_collection(TARGET, metadata={**(src.metadata or {}), "base_collection": SOURCE,
                                                         "ident_version": "ident-v2", "ident_basis": BASIS,
                                                         "build_run_id": run_id})
        created_here = True
        ids = sorted(v1)
        for off in range(0, len(ids), BATCH):
            part = ids[off:off + BATCH]
            dst.add(ids=part, documents=[v1[i][0] for i in part], embeddings=[v1[i][2] for i in part],
                    metadatas=[plan.get(i, v1[i][1]) for i in part])
        v2 = _read_all(dst, embeddings=True)
        post, changed = [], 0
        if set(v2) != set(v1):
            post.append(f"id sets differ: {len(v2)} vs {len(v1)}")
        for i in v1:
            if i not in v2:
                continue
            (d1, m1, e1), (d2, m2, e2) = v1[i], v2[i]
            if d1 != d2:
                post.append(f"{i}: document changed")
            if m2 != plan.get(i, m1):
                post.append(f"{i}: metadata is not the planned metadata")
            changed += m1 != m2
        if changed != len(plan):
            post.append(f"{changed} chunks' metadata changed, planned {len(plan)}")
        emb_problems, emb_facts = embedding_tolerance(src, dst, v1, v2, floor)
        post += emb_problems
        facts = {"chunks_written": len(v2), "metadata_changed": changed, "embeddings": emb_facts}
    except Exception:
        remove_own(client, run_id, created_here)
        raise
    if post:
        facts["own_collection_removed"] = remove_own(client, run_id, created_here)
    return post, facts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--diff", type=Path, default=DIFF, help="a FROZEN diff (with its .lock.json)")
    ap.add_argument("--store", type=Path, default=None,
                    help="an ISOLATED copy of the Chroma store to work on (default: the live backend/chroma_data)")
    ap.add_argument("--live-approved", action="store_true",
                    help="required for --build on the live store: the user approved a live build")
    args = ap.parse_args()
    live = (BACKEND / "chroma_data").resolve()
    on_live = args.store is None or args.store.resolve() == live
    if args.build and on_live and not args.live_approved:
        print("REFUSED: --build on the live store needs --live-approved (a separate user approval).")
        return 2
    diff_path = args.diff if args.diff.is_absolute() else BACKEND / args.diff
    report_path = diff_path.with_name(diff_path.stem.replace("ident_v2_metadata_diff", "build_checks")
                                      + ("" if on_live else ".isolated") + ".json")
    report = {"source": SOURCE, "target": TARGET, "diff": diff_path.name, "build": args.build}
    try:
        diff, lock = load_frozen_diff(diff_path)
        report["gate_sha256"] = check_gate_lock()["sha256"]
    except Refused as e:
        report.update(pre_checks_passed=False, problems=[str(e)])
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print("REFUSED:", e)
        return 1
    report.update(diff_sha256=lock["sha256"], locked_counts=lock["counts"])
    import eval_chat_length as EC
    EC._apply_overlay()
    if on_live:
        from app.db.chroma import connect_chroma, get_chroma
        connect_chroma()
        client = get_chroma()
    else:
        import chromadb
        client = chromadb.PersistentClient(path=str(args.store))
    report["store"] = "live backend/chroma_data" if on_live else str(args.store)
    problems = []
    if TARGET in _names(client):
        problems.append(f"{TARGET} already exists -- never overwritten or removed by this script")
    src = client.get_collection(SOURCE)
    v1 = _read_all(src, embeddings=True)
    report.update(source_chunks=len(v1), source_fingerprint_before=fingerprint(v1))
    plan, found, stats = plan_and_check(v1, diff, lock["counts"])
    problems += found
    report.update(stats=dict(stats), problems=problems, pre_checks_passed=not problems)
    if problems or not args.build:
        report["source_fingerprint_after_checks"] = fingerprint(_read_all(client.get_collection(SOURCE), embeddings=True))
        report["collections_after"] = sorted(n for n in _names(client) if "ident" in n)
        report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=1, ensure_ascii=False))
        if not args.build:
            print("read-only checks -- nothing written (use --build after approval)")
        return 1 if problems else 0

    run_id = uuid.uuid4().hex
    report["build_run_id"] = run_id
    post, facts = build_and_verify(client, src, v1, plan, run_id)
    after = fingerprint(_read_all(client.get_collection(SOURCE), embeddings=True))
    if after != report["source_fingerprint_before"]:
        post.append(f"{SOURCE} CHANGED during the build")
        facts["own_collection_removed"] = facts.get("own_collection_removed") or remove_own(client, run_id, True)
    report.update(facts, source_fingerprint_after=after, post_problems=post[:50], post_checks_passed=not post)
    report_path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("problems", "post_problems")}, indent=1))
    print("POST-BUILD PROBLEMS:" if post else "built and verified", *post[:30], sep="\n  ")
    return 1 if post else 0


if __name__ == "__main__":
    raise SystemExit(main())
