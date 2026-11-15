"""FIT paper re-evaluation on Google Colab (GPU) -- per-question ranks.

What it does (read-only on the models; nothing is trained):
  * loads base / constitutional / general retrievers at their PINNED revisions
    and checks each model.safetensors sha256 before any number is computed;
  * evaluates every model on three sets with the same conventions as the
    original Colab scripts (query:/passage: prefixes, max_seq 224, normalised,
    top-10, a gold chunk beyond rank 10 = miss):
        citation_1191  -- held-out citation pairs (general model's own split)
        legaluqa_128   -- LEGAL-UQA questions with no gold shared with general training
        legaluqa_121   -- the constitutional model's own held-out split
  * near-duplicate check: each test query's highest cosine similarity to any
    training query (base model), plus exact duplicate count.

Output: fit_reeval_result.json  (download it and send it back).

HOW TO RUN
  1. Runtime -> Change runtime type -> T4 GPU.
  2. Upload fit_reeval_data.zip to the Colab file panel.
  3. In one cell:
        !pip -q install -U sentence-transformers
        !unzip -o -q fit_reeval_data.zip
        !python fit_reeval_colab.py
  4. Download fit_reeval_result.json from the file panel.
If a model is private, first run:  import os; os.environ["HF_TOKEN"] = "<your token>"
(never paste the token anywhere else).
"""
import json, time

import torch
from huggingface_hub import HfApi
from sentence_transformers import SentenceTransformer

device = "cuda" if torch.cuda.is_available() else "cpu"
print("device:", device)

b = json.load(open("general_bundle.json", encoding="utf-8"))
cross = json.load(open("crossstyle_test.json", encoding="utf-8"))
tq = json.load(open("test_questions.json", encoding="utf-8"))
tt = json.load(open("train_triplets.json", encoding="utf-8"))

corpus = b["corpus"]; ids = list(corpus)
texts = [f"passage: {corpus[c]}" for c in ids]
gen_pos = {r["positive_id"] for r in b["train"]}

SETS = {
    "citation_1191": [{"q": r["query"], "gold": [r["positive_id"]], "domain": r["domain"],
                       "urdu": bool(r.get("urdu_query"))} for r in b["test"]],
    "legaluqa_128": [{"q": t["question"], "gold": t["relevant_chunks"], "domain": t.get("case_type"),
                      "urdu": False} for t in cross],
    "legaluqa_121": [{"q": t["question"], "gold": t["relevant_chunks"], "domain": t.get("case_type"),
                      "urdu": False} for t in tq],
}
for name, rows in SETS.items():
    miss = {g for r in rows for g in r["gold"]} - set(corpus)
    if miss:
        raise SystemExit(f"{name}: {len(miss)} gold chunk(s) missing from corpus")
print("sets:", {k: len(v) for k, v in SETS.items()}, "corpus:", len(ids))

out = {
    "conventions": "query:/passage:, max_seq 224, normalised, top-10, miss beyond 10",
    "sets": {k: len(v) for k, v in SETS.items()},
    "rows": {k: [{"domain": r["domain"], "urdu": r["urdu"], "ngold": len(r["gold"])} for r in v]
             for k, v in SETS.items()},
    "leak_general_121": [bool(set(t["relevant_chunks"]) & gen_pos) for t in tq],
    "leak_general_128": [bool(set(t["relevant_chunks"]) & gen_pos) for t in cross],
    "verified": {}, "ranks": {},
}

SPECS = [("base", b["base_model"], None, None),
         ("constitutional", b["constitutional_model"], b["constitutional_revision"],
          b["constitutional_weights_sha256"]),
         ("general", b["general_model"], b["general_revision"], b["general_weights_sha256"])]


def enc(m, xs, prefix):
    return m.encode([f"{prefix}{x}" for x in xs], batch_size=128, convert_to_tensor=True,
                    normalize_embeddings=True, show_progress_bar=False)


for label, repo, rev, want in SPECS:
    t0 = time.time()
    if rev:
        info = HfApi().model_info(repo, revision=rev, files_metadata=True)
        got = getattr(getattr({s.rfilename: s for s in info.siblings}.get("model.safetensors"),
                              "lfs", None), "sha256", "")
        if got != want:
            raise SystemExit(f"{label}: weights {got[:16]} != pinned {want[:16]}")
        out["verified"][label] = f"{repo}@{rev[:8]} sha256 {got[:16]} OK"
        m = SentenceTransformer(repo, device=device, revision=rev)
    else:
        out["verified"][label] = repo
        m = SentenceTransformer(repo, device=device)
    m.max_seq_length = 224
    m.eval()
    with torch.no_grad():
        mat = enc(m, [corpus[c] for c in ids], "passage: ")
        out["ranks"][label] = {}
        for name, rows in SETS.items():
            qv = enc(m, [r["q"] for r in rows], "query: ")
            top = torch.topk(qv @ mat.T, k=10, dim=1).indices.cpu().tolist()
            out["ranks"][label][name] = [
                next((i for i, c in enumerate([ids[j] for j in idxs], 1) if c in set(r["gold"])), None)
                for r, idxs in zip(rows, top)]
        if label == "base":
            gtr = enc(m, [r["query"] for r in b["train"]], "query: ")
            gte = enc(m, [r["query"] for r in b["test"]], "query: ")
            out["nd_citation_test_vs_general_train"] = (gte @ gtr.T).max(dim=1).values.cpu().tolist()
            ctr = enc(m, sorted({r["query"].removeprefix("query: ") for r in tt}), "query: ")
            cte = enc(m, [t["question"] for t in tq], "query: ")
            out["nd_121_vs_constitutional_train"] = (cte @ ctr.T).max(dim=1).values.cpu().tolist()
            xs = enc(m, [t["question"] for t in cross], "query: ")
            out["nd_128_vs_general_train"] = (xs @ gtr.T).max(dim=1).values.cpu().tolist()
            trs = {r["query"].strip().lower() for r in b["train"]}
            out["exact_dup_citation_test_in_train"] = sum(r["query"].strip().lower() in trs for r in b["test"])
    h1 = {n: round(sum(1 for x in v if x == 1) / len(v), 4) for n, v in out["ranks"][label].items()}
    print(f"{label:<15} Hit@1 {h1}  ({time.time() - t0:.0f}s)")
    del m, mat
    if device == "cuda":
        torch.cuda.empty_cache()

json.dump(out, open("fit_reeval_result.json", "w", encoding="utf-8"), indent=1)
print("\nDONE -> download fit_reeval_result.json")
