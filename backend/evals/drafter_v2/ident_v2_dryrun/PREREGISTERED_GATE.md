# ident_v2 -- pre-registered build-and-switch gate (PROPOSAL, 2026-10-15)

Status: **proposed, not applied, not approved.** Written and hash-locked (`PREREGISTERED_GATE.lock.json`) BEFORE any
further live build. The build script is unchanged; the live store, its two orphan folders and both backups are untouched.

## Evidence (isolated copy of backup 2; `hnsw_variability.json`; live store byte-identical before and after)

| measurement | result |
|---|---|
| ident_v1 queried 3x in one process (all 4,648 vectors, top 10 vs exact) | 4,590 / 4,590 / 4,590 -- query time is deterministic |
| ident_v1 across separate processes (earlier runs) | 4,590 - 4,594 |
| UNCHANGED ident_v1 content rebuilt 5x | **4,595 / 4,587 / 4,587 / 4,585 / 4,580** (spread 15) |
| diff v3 applied, rebuilt 5x | 4,587 / 4,579 / 4,590 / 4,581 / 4,583 |
| exact top-10 neighbours, all 10 rebuilds | 4,648 / 4,648 every time |
| real legal-query retrieval, 29 requests (18 gate + 11 dev civil) | source rebuilds: 18 / 25 expected found every time; v2 rebuilds: 19 / 25 every time; v2 "rule not shown" blocks 0 (source 26); per-query label lists identical across rebuilds for 28 / 29 |
| failed live build #2 | 4,586 -- inside the UNCHANGED source's own rebuild spread |

Conclusion: "new HNSW agreement >= source's" compares two draws of a random process; even an unchanged rebuild fails it
about half the time. It is not a valid gate. What the drafter actually sees -- the law context for real requests -- did
not move across rebuilds.

## The gate (all must hold; numbers fixed now)

A. Exact, as today:
  1. diff = `ident_v2_metadata_diff.v3.json`, sha256 `eda16e32...fb0462`; 233 planned changes;
  2. every id and document identical to ident_v1; metadata = plan for the 233, unchanged elsewhere;
  3. every vector within 1 float32 ULP of ident_v1;
  4. EXACT top-10 neighbours identical for all 4,648 vectors;
  5. ident_v1 fingerprint `987f36c7...0787` unchanged.
B. Approximate index (replaces "new >= source"):
  6. agreement with exact search >= **4,569** of 4,648 -- the lowest of the 10 measured rebuilds (4,579) minus 10.
     Derived from the rebuild distribution above, NOT from the 4,586 of build #2 (it would admit 4,586, and every one
     of the 10 measured rebuilds).
C. Real legal-query retrieval (new; run on a BYTE COPY of the live store after the build -- never by opening live):
  7. the 29 requests of `ident_v2_gate_queries.json` + dev civil cases (`hnsw_variability.py --stage retrieval`):
     expected provision found **>= 19 / 25** (every v2 rebuild measured 19), and **0 lost** versus ident_v1;
  8. "rule not shown" blocks in the law context: **0**;
  9. no law-context block under a rule label it does not open with (`ident_v2_retrieval_gate.py`).
D. Process:
  10. the build's own collection is removed on ANY failure of A-B; a failure of C after the build leaves the collection
      in place but NOT switched, and is reported;
  11. the switch remains a separate approval after the gate passes.

## What this does not settle

The retrieval set is small (29 requests, developer expectations from official headings, provisional) and was already
used in development; holdout v3 is untouched and not part of this gate. A gate pass shows the repair did not degrade
retrieval on these requests -- not that retrieval is good.
