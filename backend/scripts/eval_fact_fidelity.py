"""Measure input-fact fidelity methods on evals/drafter_v2/fact_fidelity_dev.json + the synthetic probe -- DEV ONLY.

  python scripts/eval_fact_fidelity.py

Methods: L = lexical (draft_claims.invented_facts, the guard's S3); E(t) = semantic (fact_semantic, flag a factual
clause whose best similarity to the input is below t); L+E(t) = either. Reports misses (invented, not flagged) and
false flags (ok, flagged) per method -- every threshold, none picked here. Also the Urdu sentence-boundary cases.
Loads only the local embedding model; reads no Chroma store; calls no provider."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND)]
DEV = BACKEND / "evals/drafter_v2/fact_fidelity_dev.json"
PROBE = BACKEND / "evals/drafter_v2/fact_fidelity_probe.json"
OUT = BACKEND / "evals/drafter_v2/fact_fidelity_eval.json"
THRESHOLDS = (0.80, 0.82, 0.84, 0.86, 0.88)


def main() -> int:
    from app.ai import draft_claims, draft_guard, fact_semantic
    from app.ai.pipelines.retriever import _embeddings
    from app.ai.visible_authority import _units
    emb = _embeddings()
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    items = [{"set": "dev" if not str(r["n"]).startswith("U") else "urdu", **r} for r in dev["rows"]]
    items += [{"set": "probe", "n": x["id"], "input": probe["input_default"], "sentence": x["sentence"],
               "label": "invented", "fact": x["kind"]} for x in probe["invented"]]
    items += [{"set": "probe", "n": x["id"], "input": x["input"], "sentence": x["sentence"], "label": "ok", "fact": ""}
              for x in probe["given"]]
    for it in items:
        norm = draft_guard.normalise(it["sentence"])
        it["L"] = bool(draft_claims.invented_facts(norm, it["input"]))
        scores = fact_semantic.support_scores([it["sentence"]], it["input"], emb.embed_query, emb.embed_documents)[0]
        it["clauses"] = scores
        it["min_support"] = min((s for _, s in scores), default=None)

    def flag(it, method, t=None):
        e = it["min_support"] is not None and t is not None and it["min_support"] < t
        return {"L": it["L"], "E": e, "L+E": it["L"] or e}[method]

    report = {"sets": {}, "methods": {}}
    for st in ("dev", "urdu", "probe", "all"):
        sub = [it for it in items if st == "all" or it["set"] == st]
        report["sets"][st] = {"rows": len(sub), "invented": sum(it["label"] == "invented" for it in sub)}
        for method, ts in (("L", [None]), ("E", THRESHOLDS), ("L+E", THRESHOLDS)):
            for t in ts:
                key = f"{st}:{method}" + (f"@{t}" if t else "")
                inv = [it for it in sub if it["label"] == "invented"]
                ok = [it for it in sub if it["label"] == "ok"]
                miss = [it["n"] for it in inv if not flag(it, method, t)]
                false = [it["n"] for it in ok if flag(it, method, t)]
                report["methods"][key] = {"caught": len(inv) - len(miss), "of_invented": len(inv), "missed": miss,
                                          "false_flags": len(false), "of_ok": len(ok), "false_flag_ids": false}
    bounds = []
    for b in dev["urdu_boundaries"]:
        n = draft_guard.normalise(b["text"])
        got = len(_units(n))
        bounds.append({"text": b["text"][:60], "expect": b["expect_units"], "got": got, "ok": got == b["expect_units"]})
    report["urdu_boundaries"] = bounds
    report["items"] = [{k: it[k] for k in ("set", "n", "label", "L", "min_support", "clauses")} for it in items]
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in report["methods"].items():
        if k.split(":")[0] in ("dev", "urdu", "probe", "all"):
            print(f"{k:22s} caught {v['caught']:>2}/{v['of_invented']:<2}  false flags {v['false_flags']:>2}/{v['of_ok']}")
    print("urdu boundaries:", [(b["expect"], b["got"]) for b in bounds])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
