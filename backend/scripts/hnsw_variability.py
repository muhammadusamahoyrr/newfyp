"""Approximate-index (HNSW) variability -- ISOLATED store copy only (2026-10-15). Writes scratch collections INTO THE
COPY; never touches the live backend/chroma_data.

  python scripts/hnsw_variability.py --store <isolated copy> --reps 5 --stage index
  python scripts/hnsw_variability.py --store <isolated copy> --stage retrieval

Stage `index`:
  * query-time repeatability: ident_v1 queried 3x (every stored vector, top 10) -> agreement with exact search;
  * build-time spread: ident_v1's content rebuilt `reps` times (same ids, documents, metadata, embeddings, insertion
    order) as civil_collection__hnswsrcN, and diff v3 applied `reps` times as civil_collection__hnswv2N.
Stage `retrieval`: the drafter's real law-context path (ident_v2_gate_queries.json + dev civil cases) on ident_v1 and
every rebuild: expected provision present, label sets.
Results: evals/drafter_v2/ident_v2_dryrun/hnsw_variability.json"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]
OUT = BACKEND / "evals/drafter_v2/ident_v2_dryrun/hnsw_variability.json"


def _load(out_path):
    return json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}


def stage_index(client, reps: int, res: dict) -> None:
    import numpy as np
    import build_ident_v2 as B
    src = client.get_collection(B.SOURCE)
    v1 = B._read_all(src, embeddings=True)
    ids = sorted(v1)
    e1 = np.asarray([v1[i][2] for i in ids], dtype=np.float32)
    exact = B._exact_topk(e1)
    res["query_repeat_source"] = [B._hnsw_agreement(src, ids, e1, exact) for _ in range(3)]
    diff, lock = B.load_frozen_diff(B.DIFF)
    plan, problems, _ = B.plan_and_check(v1, diff, lock["counts"])
    assert not problems, problems
    names = {getattr(c, "name", c) for c in client.list_collections()}
    for kind, meta in (("src", {}), ("v2", plan)):
        out = []
        for r in range(1, reps + 1):
            name = f"civil_collection__hnsw{kind}{r}"
            if name in names:
                client.delete_collection(name)          # scratch collection IN THE ISOLATED COPY only
            dst = client.create_collection(name, metadata=dict(src.metadata or {}))
            for off in range(0, len(ids), B.BATCH):
                part = ids[off:off + B.BATCH]
                dst.add(ids=part, documents=[v1[i][0] for i in part], embeddings=[v1[i][2] for i in part],
                        metadatas=[meta.get(i, v1[i][1]) for i in part])
            v = B._read_all(dst, embeddings=True)
            e = np.asarray([v[i][2] for i in ids], dtype=np.float32)
            out.append({"name": name, "agreement": B._hnsw_agreement(dst, ids, e1, exact),
                        "agreement_requery": B._hnsw_agreement(dst, ids, e1, exact),
                        "exact_topk_identical": int(sum(np.array_equal(a, b) for a, b in zip(exact, B._exact_topk(e))))})
            print(kind, r, out[-1], flush=True)
        res[f"rebuilds_{kind}"] = out


def stage_retrieval(store: Path, res: dict) -> None:
    import eval_chat_length as EC
    EC._apply_overlay()
    from app.db import chroma
    chroma._CHROMA_PATH = store
    chroma.connect_chroma()
    from app.ai import cpc_provisions
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes
    import eval_drafter_v2 as V
    import ident_v2_retrieval_gate as G
    spec = json.loads(G.QUERIES.read_text(encoding="utf-8"))
    items = [{"id": q["id"], "template": spec["template"], "instruction": q["instruction"], "province": "federal",
              "expect": q["expect"]} for q in spec["queries"]]
    for c in V.load_cases():
        if c["split"] == "dev" and c["case_type"] == "civil" and c["track"] == "free_drafting":
            exp = [f"Order {l['cite']} Rule {l['rule']}" if l["act"] == "CPC-order" else f"Section {l['cite']}"
                   for l in c.get("allow", []) if "cite" in l and l.get("act") in ("CPC", "CPC-order", "LA")
                   and "|" not in l["cite"] and "\\" not in l["cite"]]
            items.append({"id": c["id"], "template": c["category"].replace("_", " "), "instruction": c["instruction"],
                          "province": c["province"], "expect": exp})
    variants = ["ident_v1"] + [x["name"].split("__")[1] for x in res.get("rebuilds_src", []) + res.get("rebuilds_v2", [])]
    import re
    per = {}
    for variant in variants:
        retriever._RESEARCH_IDENT["civil_collection"] = variant
        retriever._bm25.cache_clear()
        cpc_provisions.IDENT_COLLECTION = f"civil_collection__{variant}"
        cpc_provisions.set_catalogue(None)
        rows = {}
        for it in items:
            q = routes._retrieval_query(it["template"], it["instruction"], "")
            law = routes._retrieve_law_context(q, "civil", it["province"], f"{it['template']} {it['instruction']}")
            labels = []
            for part in re.split(r"(?:^|\n\n)\[STATUTE\] ", law)[1:]:
                head = part.partition("\n")[0]
                labels.append(head)
            found = {w: any(re.search(rf"\b{re.escape(w)}$", l) for l in labels) for w in it["expect"]}
            rows[it["id"]] = {"labels": labels, "found": found}
        per[variant] = rows
        print(variant, sum(all(r["found"].values()) for r in rows.values() if r["found"]), flush=True)
    res["retrieval"] = {"queries": [it["id"] for it in items], "with_expectation": sum(1 for it in items if it["expect"]),
                        "per_variant": per}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--stage", choices=("index", "retrieval"), required=True)
    a = ap.parse_args()
    store = a.store.resolve()
    if store == (BACKEND / "chroma_data").resolve() or "scratchpad" not in str(store).lower():
        print("REFUSED: isolated copies only")
        return 2
    res = _load(OUT)
    if a.stage == "index":
        import chromadb
        stage_index(chromadb.PersistentClient(path=str(store)), a.reps, res)
    else:
        stage_retrieval(store, res)
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
