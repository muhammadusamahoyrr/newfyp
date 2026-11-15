# ident_v2 build failure -- embedding round-trip findings (2026-10-15)

All measurements on an ISOLATED copy of the pre-build backup (session scratchpad `chroma_iso_diag`, verified identical to
the backup's sha256 list). The live `backend/chroma_data`, its orphan folder `9cd66922-...` and the backup were not
touched. Nothing below changes the build; any tolerance needs separate approval.

## What failed

`scripts/build_ident_v2.py --build` (diff v3) wrote 4,648 chunks with exactly 233 metadata changes; the post-check
"every embedding equals ident_v1" failed, the script removed its own collection, ident_v1's fingerprint was unchanged.

## Measured on the isolated copy (copy of ident_v1 made exactly as the build does)

| comparison | vectors changed | max abs delta | max ULPs | min cosine to original |
|---|---|---|---|---|
| ident_v1 read twice (control) | 0 / 4,648 | 0 | 0 | -- |
| ident_v1 -> copy | 234 / 4,648 | 1.49e-08 | **1** | 0.99999983 |
| copy -> second copy | 100 / 4,648 | 1.49e-08 | 1 | 0.99999983 |

Vectors are unit length (norms 0.99999982 - 1.00000024; `hnsw:space = cosine`). Writing them again changes some by one
unit in the last float32 place, and a second round trip changes others: storage rounding, not data change. Changed
vectors span many Acts (CPC 83, TPA 29, Punjab Land Revenue 32, Succession 27, Punjab Tenancy 21, QSO 19, ...).

## Retrieval

| check (every stored vector as a query, top 10) | result |
|---|---|
| EXACT neighbours, original vectors vs copied vectors | **4,648 / 4,648 identical** (order and set) |
| HNSW index of ident_v1 agrees with exact | 4,592 / 4,648 |
| HNSW index of the copy agrees with exact | 4,592 / 4,648 |
| HNSW ident_v1 vs HNSW copy, same top-10 | 4,575 / 4,648 |

The 1-ULP changes do not change any exact neighbour. The HNSW differences between the two collections come from
building a new approximate index (both are equally close to exact search), which any rebuild would show.

## Proposal (NOT applied)

Replace "embedding byte-identical" in the post-build check with all of:
1. every vector within 1 ULP of float32 per component (max |delta| <= 1.5e-08) -- reported with counts;
2. exact top-10 neighbours identical for every stored vector as a query;
3. the new HNSW index agrees with exact search at least as often as ident_v1's (>= 4,592 / 4,648);
4. ids, documents, the 233 planned metadata changes and the unchanged ident_v1 fingerprint stay EXACT.
A retry of the live build, and cleanup of the orphan folder, each need separate approval.
