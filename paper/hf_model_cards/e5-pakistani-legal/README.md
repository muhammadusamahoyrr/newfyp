---
license: mit
base_model: intfloat/multilingual-e5-base
language:
- en
- ur
library_name: sentence-transformers
pipeline_tag: sentence-similarity
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- legal
- retrieval
- pakistan
- urdu
- roman-urdu
---

# e5-pakistani-legal

A dense retriever for **Pakistani statutory law**, fine-tuned from
[intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) on 4,692 verified
question–statute pairs in English and Urdu script. It maps a legal question to the statute section that
governs it.

This is the **general model** of the FIT 2026 paper *In-Distribution Gains Do Not Transfer: Leakage-Free
Evaluation of Retrieval Interventions for Low-Resource Legal Question Answering*. The paper's headline
finding is about this model, so please read [Evaluation](#evaluation) before relying on it. It improves
strongly on questions like its training data, but not on every new source of questions.

> **Use revision `0efe7b2b` (or later).** Revision `445e441d` of this repository, from before
> 2026-08-07 15:12 UTC, holds a *different* model: the constitutional-only model, now published as
> [usama1111/e5-pak-legal-constitutional](https://huggingface.co/usama1111/e5-pak-legal-constitutional).
> The weights evaluated in the paper have SHA-256 `a3e7e4c1b650051b…`.

## How to use

As with the base model, prefix queries with `query: ` and passages with `passage: `.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("usama1111/e5-pakistani-legal", revision="0efe7b2b")
model.max_seq_length = 224  # the length used in training

queries = ["query: What is the punishment for theft?"]
passages = ["passage: 379. Punishment for theft. Whoever commits theft shall be punished ..."]

q = model.encode(queries, normalize_embeddings=True)
p = model.encode(passages, normalize_embeddings=True)
print(q @ p.T)  # cosine similarity
```

## Training

| | |
|---|---|
| Base model | intfloat/multilingual-e5-base |
| Training pairs | 4,692 (query, gold statute passage) |
| Held-out pairs | 1,191, split so that no gold passage appears in both halves |
| Legal domains | 5 (constitutional, criminal, evidence, civil procedure, family) |
| Urdu-script queries | 32% |
| Loss | Multiple-negatives ranking loss, with hard negatives mined from the deployed retriever |
| Hyperparameters | 2 epochs, batch size 12, learning rate 2 × 10⁻⁵, max sequence length 224 |
| Runs | 1 (seed variance is unmeasured) |

**Where the pairs come from.** The pairs come from 11,195 Pakistani legal Q&A pairs with
machine-parseable citations (e.g., PPC s.467). The answers were LLM-generated, so only the citation is
used. Four filters were applied:
1. LEGAL-UQA rows dropped, since that dataset is used for evaluation.
2. Citations naming an unindexed section dropped.
3. Citations validated by rarity-weighted vocabulary overlap with the answer; wrong citations dropped.
4. Exact duplicates removed.

5,883 pairs survive. Passages are statute chunks from the
[Pakistan Laws Dataset](https://huggingface.co/datasets/AyeshaJadoon/Pakistan_Laws_Dataset) (ODC-BY) and
the official [Pakistan Code](https://pakistancode.gov.pk/).

## Evaluation

Every number below is dense retrieval only (no BM25). It ranks a fixed 9,042-passage corpus, with
normalised embeddings and the prefixes above. A gold passage below rank 10 counts as a miss.
Significance is McNemar's exact test on paired Hit@1 outcomes, and intervals are 95% bootstrap CIs.

| Test set | n | Hit@1, base → this model | Δ Hit@1 (95% CI) | p | MRR@10, base → this model |
|---|---|---|---|---|---|
| Own held-out citation pairs | 1,191 | 41.5% → 68.0% | **+26.5** (23.5 to 29.6) | < 10⁻⁵⁰ | 0.516 → 0.758 |
| … Urdu-script queries | 389 | 16.7% → 64.0% | +47.3 | < 10⁻⁴⁷ | 0.255 → 0.718 |
| … English queries | 802 | 53.5% → 70.0% | +16.5 | < 10⁻¹⁷ | 0.643 → 0.778 |
| LEGAL-UQA questions (a different generator), English | 128 | 52.3% → 54.7% | **+2.3** (−6.2 to 10.9) | 0.72 | 0.605 → 0.632 |
| Same LEGAL-UQA questions, Urdu (the dataset's own translation) | 128 | 18.0% → 42.2% | +24.2 | < 10⁻⁵ | — |
| Same LEGAL-UQA questions, Roman Urdu (LLM-written) | 126 | 21.4% → 38.9% | +17.5 | 0.0003 | — |
| Developer-written queries (a third source) | 25 | 20.0% → 60.0% | +40.0 | 0.002 | 0.285 → 0.620 |

**What this means.**
- On questions like its training data, the model gains a lot (+26.5 Hit@1), most of all on Urdu-script
  queries.
- On English questions written by a different generator (LEGAL-UQA), the gain is not distinguishable
  from zero, even within the same domain and script: English constitutional citation questions gain
  +23.3 in-distribution (n = 236).
- Rewording questions (layperson English, keywords) does not change this. The failure is tied to the
  source of the questions, not their wording.
- The Urdu and Roman Urdu renderings of those same questions, and an independent developer-written set,
  do show gains.

**An in-distribution number does not predict which of these you will see.** Evaluate on your own
questions before deploying.

Zero-shot [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) (dense, length 512) scores 51.9% on the
held-out citation pairs, against 68.0% for this model. It matches this model on Urdu LEGAL-UQA
(41.4% vs 42.2%).

## Limitations

- **Coverage.** Provincial coverage is Punjab only; federal law is covered. There are no amendment dates:
  the corpus is a snapshot.
- **Weak domains.** No improvement over the base model on civil procedure (n = 19, −5.3) or family law
  (n = 21, −4.8). These samples are small and not significant.
- **Evaluation data.** All evaluation sets are generator-derived or developer-built. No independent,
  human-labelled benchmark exists yet.
- **Retrieval only.** It returns passages, not legal advice. Retrieved law must be checked by a qualified
  practitioner.

## Citation

```bibtex
@inproceedings{usama2026indistribution,
  title     = {In-Distribution Gains Do Not Transfer: Leakage-Free Evaluation of Retrieval
               Interventions for Low-Resource Legal Question Answering},
  author    = {Usama, Muhammad and Khan, Muhammad Amir Zarmaan Ullah},
  booktitle = {Proc. International Conference on Frontiers of Information Technology (FIT)},
  year      = {2026},
  note      = {To appear}
}
```

Base model: L. Wang et al., *Multilingual E5 Text Embeddings: A Technical Report*, arXiv:2402.05672 (MIT
licence).
