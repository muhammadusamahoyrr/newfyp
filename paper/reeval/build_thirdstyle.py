"""Third question style for the FIT paper: map the developer-written legal_rag
eval queries (backend/evals/legal_rag/datasets) onto the fine-tuning bundle
corpus (backend/data/general_bundle.json, 9,042 chunks), read-only.

A bundle chunk takes its statute/section from the live Chroma base collections
ONLY if its text there is byte-identical to the bundle text (same chunk). A
lettered target (PPC 489-F, indexed as "489" in the base index) is gold only in
chunks labelled with the index section whose text names the lettered section.
Writes thirdstyle_test.json (+ a mapping report). Backend must be stopped.

Usage: backend/venv/Scripts/python.exe paper/reeval/build_thirdstyle.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
from app.db.chroma import connect_chroma, get_chroma  # noqa: E402

DATA = BACKEND / "data"
MAX_GOLD = 10
SETS = ["dev_v1", "citation_probe_v1", "lettered_probe_v1", "coverage_v1", "multi_issue_v1"]
OUT = Path(__file__).resolve().parent

bundle = json.load(open(DATA / "general_bundle.json", encoding="utf-8"))
corpus = bundle["corpus"]

connect_chroma()
client = get_chroma()
meta = {}
mismatch = 0
for coll in ("constitutional_collection", "criminal_collection", "civil_collection", "family_collection"):
    try:
        g = client.get_collection(coll).get(include=["documents", "metadatas"])
    except Exception as e:  # noqa: BLE001
        print("skip", coll, type(e).__name__)
        continue
    for cid, doc, m in zip(g["ids"], g["documents"], g["metadatas"]):
        if cid in corpus:
            if (doc or "") == corpus[cid]:
                meta[cid] = ((m or {}).get("statute", ""), str((m or {}).get("section_number", "")).strip())
            else:
                mismatch += 1
print(f"bundle chunks: {len(corpus)}  with identical text + metadata: {len(meta)}  text changed: {mismatch}")


def norm_sec(s):
    return re.sub(r"\s+", "", str(s)).upper()


by_key = {}
for cid, (st, sec) in meta.items():
    by_key.setdefault((st, norm_sec(sec)), []).append(cid)


def gold_for(target):
    # Statute-level targets ("Punjab Rented Premises Act 2009") are not
    # passage-level gold; every other set in the paper is passage-level.
    if "section" not in target:
        return None
    st, sec = target["statute"], target["section"]
    # A plain section's label also sits on its lettered siblings in the base
    # index (PPC "489" on 489-A..F): drop chunks whose text opens a lettered one.
    sib = re.compile(rf"^\s*{re.escape(str(sec))}\s*-\s*[A-Z]\b")
    hits = [c for c in by_key.get((st, norm_sec(sec)), []) if not sib.match(corpus[c])]
    idx = target.get("index_section")
    if idx and norm_sec(idx) != norm_sec(sec):
        pat = re.compile(rf"\b{re.escape(str(idx))}\s*-?\s*{re.escape(norm_sec(sec)[len(norm_sec(idx)):].lstrip('-'))}\b",
                         re.IGNORECASE)
        hits += [c for c in by_key.get((st, norm_sec(idx)), []) if pat.search(corpus[c])]
    return sorted(set(hits))


rows, report = [], Counter()
for name in SETS:
    for line in open(BACKEND / "evals" / "legal_rag" / "datasets" / f"{name}.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        q = json.loads(line)
        if not q.get("answerable_by_corpus", True) or not q.get("relevant"):
            report[f"{name}: skipped (unanswerable)"] += 1
            continue
        per = [gold_for(t) for t in q["relevant"]]
        if any(g is None for g in per):
            report[f"{name}: skipped (statute-level target)"] += 1
            continue
        if any(len(g) > MAX_GOLD for g in per):
            report[f"{name}: skipped (section label on >{MAX_GOLD} chunks: corpus label defect)"] += 1
            continue
        gold = sorted({c for g in per for c in g})
        if not gold:
            report[f"{name}: skipped (target not in bundle)"] += 1
            continue
        report[f"{name}: kept"] += 1
        rows.append({"query_id": q["query_id"], "set": name, "query": q["query"],
                     "language": q.get("language"), "case_type": q.get("case_type"),
                     "question_type": q.get("question_type"), "relevant_chunks": gold,
                     "targets": q["relevant"]})

# Target leakage, the same test the 128-question set passed: does any gold
# passage appear among either model's training positives?
gen_pos = {r["positive_id"] for r in bundle["train"]}
text2id = {}
for cid, t in corpus.items():
    text2id.setdefault(t.strip(), cid)
triplets = json.load(open(DATA / "finetune" / "train_triplets.json", encoding="utf-8"))
const_pos = {text2id.get(r["positive"].removeprefix("passage: ").strip()) for r in triplets} - {None}
for r in rows:
    r["leak_general"] = bool(set(r["relevant_chunks"]) & gen_pos)
    r["leak_constitutional"] = bool(set(r["relevant_chunks"]) & const_pos)
print("constitutional training positives mapped to corpus ids:", len(const_pos))
print("leak_general:", sum(r["leak_general"] for r in rows),
      " leak_constitutional:", sum(r["leak_constitutional"] for r in rows),
      " clean for general:", sum(not r["leak_general"] for r in rows),
      " clean for constitutional:", sum(not r["leak_constitutional"] for r in rows))

json.dump(rows, open(OUT / "thirdstyle_test.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in sorted(report.items()):
    print(f"  {k}: {v}")
print("kept:", len(rows), " languages:", dict(Counter(r["language"] for r in rows)),
      " case types:", dict(Counter(r["case_type"] for r in rows)))
print("gold chunks per query:", dict(Counter(len(r["relevant_chunks"]) for r in rows)))
