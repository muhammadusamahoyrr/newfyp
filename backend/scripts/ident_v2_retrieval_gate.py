"""Pre-switch gate: the drafter's REAL law-context retrieval with ident_v1 vs ident_v2, on representative civil
requests (evals/drafter_v2/ident_v2_gate_queries.json + dev cases V01-V08). Runs ONLY on an isolated store copy that
holds both collections -- never the live backend/chroma_data. Reads only; writes nothing to the store.

  python scripts/ident_v2_retrieval_gate.py --store <isolated copy>

Gate (all must hold): no query loses an expected provision that ident_v1 put in the law context; no law-context
block is labelled with a rule whose text it does not open with (a multi-rule chunk shown under one label); the run
reports gains, losses and every label change for review."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]
QUERIES = BACKEND / "evals/drafter_v2/ident_v2_gate_queries.json"
OUT = BACKEND / "evals/drafter_v2/ident_v2_dryrun/retrieval_gate.json"
VARIANTS = {"v1": "ident_v1", "v2": "ident_v2"}
# Pre-registered gate C (PREREGISTERED_GATE.md, locked): every one of 5 measured ident_v2 rebuilds found 19 / 25.
FOUND_MIN = 19


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, required=True)
    args = ap.parse_args()
    store = args.store.resolve()
    import build_ident_v2
    build_ident_v2.check_gate_lock()                 # numbers valid only with the locked gate
    if store == (BACKEND / "chroma_data").resolve():
        print("REFUSED: the gate runs on an isolated copy only")
        return 2
    import eval_chat_length as EC
    EC._apply_overlay()
    from app.db import chroma
    chroma._CHROMA_PATH = store                      # this process reads the isolated copy only
    chroma.connect_chroma()
    from app.ai import cpc_provisions
    from app.ai.pipelines import retriever
    from app.api.v1.routes import ai as routes
    import eval_drafter_v2 as V

    spec = json.loads(QUERIES.read_text(encoding="utf-8"))
    items = [{"id": q["id"], "template": spec["template"], "instruction": q["instruction"], "province": "federal",
              "expect": q["expect"]} for q in spec["queries"]]
    for c in V.load_cases():
        if c["split"] == "dev" and c["case_type"] == "civil" and c["track"] == "free_drafting":
            exp = [f"Order {l['cite']} Rule {l['rule']}" if l["act"] == "CPC-order" else f"Section {l['cite']}"
                   for l in c.get("allow", []) if "cite" in l and l.get("act") in ("CPC", "CPC-order", "LA")
                   and "|" not in l["cite"] and "\\" not in l["cite"]]        # a regex label is not a provision name
            items.append({"id": c["id"], "template": c["category"].replace("_", " "), "instruction": c["instruction"],
                          "province": c["province"], "expect": exp})

    names = {getattr(x, "name", x) for x in chroma.get_chroma().list_collections()}
    assert {"civil_collection__ident_v1", "civil_collection__ident_v2"} <= names, "both collections must be in the copy"
    results = {}
    for tag, variant in VARIANTS.items():
        retriever._RESEARCH_IDENT["civil_collection"] = variant
        retriever._bm25.cache_clear()
        cpc_provisions.IDENT_COLLECTION = f"civil_collection__{variant}"
        cpc_provisions.set_catalogue(None)
        for it in items:
            q = routes._retrieval_query(it["template"], it["instruction"], "")
            law = routes._retrieve_law_context(q, "civil", it["province"], f"{it['template']} {it['instruction']}")
            # block by block: the opening may span lines (an amendment mark "1\n[9. Effect of dismissal" opens
            # rule 9), and a short block must never swallow the next header
            blocks = []
            for part in re.split(r"(?:^|\n\n)\[STATUTE\] ", law)[1:]:
                head, _, body = part.partition("\n")
                statute, _, label = head.partition(" — ")
                blocks.append((statute, label, body[:80]))
            results.setdefault(it["id"], {})[tag] = [{"statute": s, "label": l.strip(), "opens": o} for s, l, o in blocks]

    def labels(rows):
        return [f"{r['statute'].split()[0]} {r['label']}" for r in rows]

    def has(rows, want):
        return any(re.search(rf"\b{re.escape(want)}$", r["label"]) for r in rows)

    report, lost, gained, mislabel = [], [], [], []
    for it in items:
        r1, r2 = results[it["id"]]["v1"], results[it["id"]]["v2"]
        e1 = {w: has(r1, w) for w in it["expect"]}
        e2 = {w: has(r2, w) for w in it["expect"]}
        lost += [(it["id"], w) for w in it["expect"] if e1[w] and not e2[w]]
        gained += [(it["id"], w) for w in it["expect"] if e2[w] and not e1[w]]
        for r in r2:                                  # a rule block must open with that rule's own number
            m = re.match(r"Order [IVXLC]+ Rule (\d+[A-Z]?)$", r["label"])
            if m and re.match(r"\W*\d", r["opens"]) and not re.match(rf"\W*(?:\d{{1,2}}\s*\[\s*)?{m.group(1)}\b", r["opens"]):
                mislabel.append((it["id"], r["label"], r["opens"][:40]))
        report.append({"id": it["id"], "expect": it["expect"], "found_v1": e1, "found_v2": e2,
                       "labels_v1": labels(r1), "labels_v2": labels(r2),
                       "rule_not_shown_v1": sum("rule not shown" in r["label"] for r in r1),
                       "rule_not_shown_v2": sum("rule not shown" in r["label"] for r in r2)})
    summary = {"queries": len(items),
               "expected_found_v1": sum(all(r["found_v1"].values()) for r in report if r["expect"]),
               "expected_found_v2": sum(all(r["found_v2"].values()) for r in report if r["expect"]),
               "with_expectation": sum(1 for r in report if r["expect"]),
               "lost": lost, "gained": gained, "mislabelled_blocks_v2": mislabel,
               "rule_not_shown_blocks_v1": sum(r["rule_not_shown_v1"] for r in report),
               "rule_not_shown_blocks_v2": sum(r["rule_not_shown_v2"] for r in report),
               "pre_registered": {"expected_found_v2_min": FOUND_MIN, "lost_max": 0, "rule_not_shown_v2_max": 0,
                                  "mislabelled_max": 0}}
    summary["gate_passed"] = (summary["expected_found_v2"] >= FOUND_MIN and not lost and not mislabel
                              and summary["rule_not_shown_blocks_v2"] == 0)
    OUT.write_text(json.dumps({"summary": summary, "queries": report}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
