# Scratch experiment: relabel the Punjab-Code CPC from `federal` to `punjab` (2026-10-17)

**Approval:** given by you on 2026-10-17 to build a scratch CPC-relabel experiment from a copy of the verified snapshot only.

**Not done:** live-store access, model call, deletion, index switch. Retrieval was measured with the app's **own BM25 retriever and chunk filter** (no neural model). The **dense half was not run**, because it needs the local embedding model. Its filter is the same metadata rule, so the eligibility numbers below hold for it exactly; its *ranking* is unmeasured.

**Store:** `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\SCRATCH_cpc_relabel_20261017T025355Z` (a robocopy of the verified snapshot, 101/101 files). Raw results: `…\SCRATCH_cpc_relabel_20261017T025355Z.experiment.json`.

## What was relabelled

- **Which chunks:** those with `statute = "CPC 1908"`, `province = "federal"` and `source_file = "code of civil procedure 1908.pdf"` (the Punjab Code text).
- **Where:** **1,967 chunks** in each of `civil_collection`, `civil_collection__ident_v1` and `civil_collection__ident_v2`.
- **The change:** `province` → `"punjab"`, plus a `province_relabel` provenance note. Metadata only: counts stayed 4,648 and embeddings are unchanged.
- **Health:** `index_health` reports **ok** for `ident_v2` and `sec_v2` both before and after (counts and build markers unchanged).

## How the code uses `province`

| Path | Rule |
|---|---|
| Retrieval, known province P (BM25 and dense) | `province ∈ {P, "federal"}` |
| Retrieval, **unknown** province | **no province filter** |
| Exact-provision lookup | **no province filter** |
| Intake evidence gate | drops a statute chunk whose province is not `federal`, empty, or the matter's own |

## Results (A = today's labels, B = relabelled)

**Eligibility** (the same in `civil_collection` and `ident_v2`):

| Province | CPC chunks A → B | non-CPC chunks A → B |
|---|---|---|
| punjab | 1,967 → 1,967 | 2,681 → 2,681 |
| sindh / kpk / balochistan / federal | 1,967 → **0** | 1,617 → 1,617 (unchanged) |
| unknown | 1,967 → 1,967 | 2,681 → 2,681 |

**Unrelated laws stay available:** non-CPC eligibility is identical before and after for every province.

**BM25 top-10, five procedural (CPC) questions**, in both collections:

| Province | Right law in top 10 (A → B) | Chunks returned | Intake gate (A → B) |
|---|---|---|---|
| punjab | yes → yes | 10 → 10 | supported → supported |
| sindh / kpk / balochistan / federal | **yes → no** (all 5 questions) | 10 → **2–4** for 4 of 5 questions (10 → 10 for "rejection of plaint") | **supported → supported** |
| unknown | yes → yes | 10 → 10 | **supported → wrong_jurisdiction** for 3 of 5 (injunction, execution, court jurisdiction) |

**BM25, five other-law questions:**

| Question | Result |
|---|---|
| Limitation (two questions) | right law present for every province, before and after |
| Specific Relief | not in the top 10 for **any** province, **before and after**. Correction (batch 9): the **Specific Relief Act is not in the corpus at all** (`corpus_instruments.json`), so this is a corpus gap, not a retrieval-ranking gap. |
| Pre-emption, eviction (Punjab Acts) | present for Punjab and unknown; absent elsewhere, **before and after** (expected) |
| Gate verdicts | unchanged, except the unknown-province pre-emption/eviction rows, which were already `wrong_jurisdiction` before |

**Exact-provision lookup** (client and research paths):
- **CPC lookups:** Section 9 / 20 / 151 CPC are found **before and after (same counts)**, now labelled `punjab`.
- **Control:** Transfer of Property Act s.54 is unchanged.

## New abstentions, and the risk the experiment exposed

1. **New abstentions: unknown province only.** For 3 of 5 procedural questions, the intake gate now says `wrong_jurisdiction`: every chunk retrieved is now Punjab-labelled, and an unknown-province matter does not admit Punjab chunks. Intake normally requires a province, so this mainly affects legacy or edge records. Client chat and research don't use this gate.
2. **The bigger risk: NO abstention where one is needed.** For Sindh, KP, Balochistan and federal:
   - the procedural law disappears from retrieval, but the gate still says `supported` on whatever 2–10 unrelated chunks remain;
   - Intake would then analyse a procedure question from irrelevant law, **silently**;
   - today, the Punjab CPC is retrieved and the batch-5/6 output gates label it.

   **Switching the relabel live without a gate change would be a regression.**

## Before any live switch (each a separate decision)

1. **Gate:** when a known non-Punjab matter's question is procedural (CPC) and no CPC text for that province is held, the gate should return an honest `wrong_jurisdiction`-style result, instead of `supported` on leftover chunks.
2. **Unknown province:** decide whether Punjab-labelled CPC should stay eligible (with today's notices) or be held back.
3. **Exact-provision lookup:** make it province-aware, or keep relying on the output labels.
4. **Dense retrieval:** measure with the local embedding model, which needs your OK to run that model.
5. **The real fix:** ingest a verified federal and/or other-province CPC text (licence, status and commencement first), so non-Punjab procedural questions have lawful text to retrieve.

## Store health found on the way

- **The failing collection:** `judgments_collection_broken_2026_08_27`, an old copy already named "broken", **cannot be opened** ("Failed to apply logs to the hnsw segment writer"). The app does not use it; it uses `judgments_collection` (23,978 records, opens fine).
- **Everything else:** every collection the app uses opens and counts correctly.
- **Pending log:** many collections have unapplied write-log entries (`embeddings_queue`). That is normal for this Chroma version; noted, not a fault.

## Files (outside the repository; nothing deleted)

- `chroma_snapshots\SCRATCH_cpc_relabel_20261017T025355Z\` (+ `.robocopy.log`, `.experiment.json`).
- The verified snapshot and the fingerprint work copy from the earlier step are unchanged and kept.
