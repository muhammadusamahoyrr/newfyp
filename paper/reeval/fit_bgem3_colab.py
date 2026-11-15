"""FIT paper: BGE-M3 (dense only, zero-shot) on every evaluation set used in the
paper, so it can be compared question-by-question with the base e5 and the two
fine-tuned retrievers. Read-only; nothing is trained.

Sets (same order as the earlier result files, so ranks line up row by row):
    citation_1191 -- general_bundle.json "test"
    legaluqa_128  -- crossstyle_test.json
    legaluqa_121  -- test_questions.json
    thirdstyle    -- thirdstyle_test.json
    stylegrid     -- stylegrid_test.json
Conventions: no instruction prefixes (BGE-M3 uses none), normalised dense
embeddings, max_seq 512, top-10, a gold chunk beyond rank 10 = miss.
The exact model revision is recorded in the output.

HOW TO RUN (T4 GPU):
    %cd /content
    !pip -q install -U sentence-transformers
    !unzip -o -q fit_bgem3_data.zip
    !python fit_bgem3_colab.py
Then download fit_bgem3_result.json.
"""
import json, time

import torch
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer

device = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", device)
if device != "cuda":
    raise SystemExit("No GPU: Runtime -> Change runtime type -> T4 GPU, then re-upload and rerun.")

REPO = "BAAI/bge-m3"
b = json.load(open("general_bundle.json", encoding="utf-8"))
corpus = b["corpus"]; ids = list(corpus)
SETS = {
    "citation_1191": [{"q": r["query"], "gold": [r["positive_id"]]} for r in b["test"]],
    "legaluqa_128": [{"q": t["question"], "gold": t["relevant_chunks"]}
                     for t in json.load(open("crossstyle_test.json", encoding="utf-8"))],
    "legaluqa_121": [{"q": t["question"], "gold": t["relevant_chunks"]}
                     for t in json.load(open("test_questions.json", encoding="utf-8"))],
    "thirdstyle": [{"q": t["query"], "gold": t["relevant_chunks"]}
                   for t in json.load(open("thirdstyle_test.json", encoding="utf-8"))],
    "stylegrid": [{"q": t["query"], "gold": t["relevant_chunks"]}
                  for t in json.load(open("stylegrid_test.json", encoding="utf-8"))],
}
for name, rows in SETS.items():
    miss = {g for r in rows for g in r["gold"]} - set(corpus)
    if miss:
        raise SystemExit(f"{name}: {len(miss)} gold chunk(s) missing from corpus")
print("sets:", {k: len(v) for k, v in SETS.items()}, "corpus:", len(ids))

rev = HfApi().model_info(REPO).sha
t0 = time.time()
m = SentenceTransformer(REPO, device=device, revision=rev)
m.max_seq_length = 512
m.half()
m.eval()


def enc(xs):
    return m.encode(xs, batch_size=64, convert_to_tensor=True, normalize_embeddings=True,
                    show_progress_bar=False)


out = {"model": f"{REPO}@{rev}", "conventions": "dense only, no prefixes, max_seq 512, fp16, top-10",
       "sets": {k: len(v) for k, v in SETS.items()}, "ranks": {}}
with torch.no_grad():
    mat = enc([corpus[c] for c in ids])
    for name, rows in SETS.items():
        qv = enc([r["q"] for r in rows])
        top = torch.topk(qv @ mat.T, k=10, dim=1).indices.cpu().tolist()
        out["ranks"][name] = [next((i for i, c in enumerate([ids[j] for j in idxs], 1) if c in set(r["gold"])), None)
                              for r, idxs in zip(rows, top)]
        h1 = sum(1 for x in out["ranks"][name] if x == 1) / len(rows)
        print(f"  {name:<14} Hit@1 {h1:.4f}", flush=True)
print(f"done in {time.time() - t0:.0f}s")
json.dump(out, open("fit_bgem3_result.json", "w", encoding="utf-8"), indent=1)
print("\nDONE -> download fit_bgem3_result.json")
