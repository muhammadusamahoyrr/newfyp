"""Section-level leakage for the third style: is the gold SECTION (any chunk of
it, not only the gold chunk) a training positive of the general model?
Read-only on Chroma; backend must be stopped."""
import json, sys
from pathlib import Path
BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
from app.db.chroma import connect_chroma, get_chroma  # noqa: E402

b = json.load(open(BACKEND / "data" / "general_bundle.json", encoding="utf-8"))
third = json.load(open(Path(__file__).parent / "thirdstyle_test.json", encoding="utf-8"))
R = json.load(open(Path(__file__).parent / "fit_thirdstyle_result.json", encoding="utf-8"))
connect_chroma(); cl = get_chroma(); meta = {}
for coll in ("constitutional_collection", "criminal_collection", "civil_collection", "family_collection"):
    g = cl.get_collection(coll).get(include=["metadatas"])
    for cid, m in zip(g["ids"], g["metadatas"]):
        if cid in b["corpus"]:
            meta[cid] = ((m or {}).get("statute", ""), str((m or {}).get("section_number", "")).strip())
train_sections = {meta.get(r["positive_id"]) for r in b["train"]}
def secs(t): return {meta.get(c) for c in t["relevant_chunks"]}
rk = R["ranks"]
groups = {"clean chunk, section ALSO a training positive": [], "clean chunk AND clean section": []}
for i, t in enumerate(third):
    if t["leak_general"]:
        continue
    key = "clean chunk, section ALSO a training positive" if secs(t) & train_sections else "clean chunk AND clean section"
    groups[key].append(i)
for k, idx in groups.items():
    if not idx:
        print(k, "n=0"); continue
    bb = sum(rk["base"]["thirdstyle"][i] == 1 for i in idx); gg = sum(rk["general"]["thirdstyle"][i] == 1 for i in idx)
    print(f"{k}: n={len(idx)}  base Hit@1 {bb}/{len(idx)}  general Hit@1 {gg}/{len(idx)}  "
          f"queries: {[third[i]['query_id'] for i in idx]}")
    for i in idx:
        print("    ", third[i]["query_id"], third[i]["targets"], "| base", rk["base"]["thirdstyle"][i],
              "gen", rk["general"]["thirdstyle"][i], "|", third[i]["query"][:60])
