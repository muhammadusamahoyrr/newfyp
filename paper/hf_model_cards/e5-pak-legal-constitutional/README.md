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
- constitutional-law
---

# e5-pak-legal-constitutional

A dense retriever for the **Constitution of Pakistan**, fine-tuned from
[intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base) on 471 English
question–article pairs from LEGAL-UQA.

This is the **constitutional model** of the FIT 2026 paper *In-Distribution Gains Do Not Transfer:
Leakage-Free Evaluation of Retrieval Interventions for Low-Resource Legal Question Answering*. For
statutory law beyond the Constitution, see the general model,
[usama1111/e5-pakistani-legal](https://huggingface.co/usama1111/e5-pakistani-legal).

> **Use revision `6aec3e7a`.** The weights evaluated in the paper have SHA-256 `9761c235d497c6c3…`. The
> same weights are also at revision `445e441d` of `usama1111/e5-pakistani-legal`, whose later revisions
> hold the general model.

## How to use

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("usama1111/e5-pak-legal-constitutional", revision="6aec3e7a")
model.max_seq_length = 224

q = model.encode(["query: Who appoints the Chief Election Commissioner?"], normalize_embeddings=True)
p = model.encode(["passage: 213. Chief Election Commissioner ..."], normalize_embeddings=True)
print(q @ p.T)
```

## Training

| | |
|---|---|
| Base model | intfloat/multilingual-e5-base |
| Training pairs | 471 English LEGAL-UQA question–article pairs (constitutional law only) |
| Held-out split | 121 questions, split so that no gold passage appears in both halves |
| Loss | Multiple-negatives ranking loss, with hard negatives mined from the deployed retriever |
| Hyperparameters | 2 epochs, batch size 12, learning rate 2 × 10⁻⁵, max sequence length 224 |
| Runs | 1 (seed variance is unmeasured) |

Source dataset: F. Faisal and U. Yousaf, *LEGAL-UQA: A low-resource Urdu-English dataset for legal question
answering*, arXiv:2410.13013.

## Evaluation

Every number below is dense retrieval only. It ranks a fixed 9,042-passage corpus, with normalised
embeddings and the `query: ` / `passage: ` prefixes. A gold passage below rank 10 counts as a miss.
Significance is McNemar's exact test, and intervals are 95% bootstrap CIs.

| Test set | n | Hit@1, base → this model | Δ Hit@1 (95% CI) | p |
|---|---|---|---|---|
| Own held-out LEGAL-UQA split | 121 | 43.8% → 59.5% | **+15.7** (7.4 to 24.0) | 0.0005 |
| … in Urdu (the dataset's own translation) | 121 | 11.6% → 28.9% | +17.4 | < 10⁻⁵ |
| … in layperson English | 120 | 42.5% → 57.5% | +15.0 | 0.002 |
| … in Roman Urdu | 119 | 17.6% → 29.4% | +11.8 | 0.003 |
| … as keywords | 120 | 27.5% → 34.2% | +6.7 | 0.20 |
| Citation questions (a different generator, 5 domains) | 1,191 | 41.5% → 41.1% | **−0.3** (−2.9 to 2.3) | 0.85 |
| … constitutional questions only | 337 | 39.8% → 45.1% | +5.3 (0.6 to 10.1) | 0.036 |
| … evidence-law questions | 207 | 43.0% → 33.8% | −9.2 | 0.009 |

MRR@10 is 0.568 → 0.690 on the own split, and 0.516 → 0.516 on the citation questions. The layperson,
Roman Urdu and keyword versions were written by an LLM, with content and gold passage held fixed. Any rewrite
that added a number or a provision reference was rejected.

**What this means.** On its own kind of questions, the gain survives rewording into other styles and
scripts. On another generator's questions it is gone overall, and only about a third of it (+5.3) survives
within constitutional law. Outside its domain, on evidence law, it is worse than the base model.

**Do not evaluate this model on LEGAL-UQA questions it was trained on.** 106 of the 128 LEGAL-UQA questions
used to test the general model are training questions of this model. Its 76.6% Hit@1 on that set is
memorisation, not retrieval skill.

**In the deployed hybrid system** (BM25 0.6 + dense 0.4), its dense-only gain of +16.5 on the own split
becomes +6.6. BM25 already supplies much of what fine-tuning adds.

**Against a larger encoder.** Zero-shot [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) scores 46.3% on
the own split, against 59.5% for this model. On the Urdu renderings, BGE-M3 is ahead (38.0% vs 28.9%,
p = 0.08).

## Limitations

- Constitutional law only; there were no Urdu-script training queries.
- One small training set (471 pairs). All evaluation sets are generator-derived or developer-built.
- Retrieval only: it returns passages, not legal advice.

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
