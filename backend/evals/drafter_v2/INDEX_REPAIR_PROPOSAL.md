# Proposal: versioned metadata repair of the CPC identity index -- diff v3 (NOT APPLIED)

Status: **awaiting approval to build** (2026-10-15). Nothing has been written to any collection. The active collection is
unchanged (`civil_collection__ident_v1`); switching to `ident_v2` is a further, separate approval.

## 1. What is proposed

Build a NEW collection `civil_collection__ident_v2` = `ident_v1` with **233 metadata changes** to CPC First Schedule
chunks, taken from the frozen diff v3. Same ids, documents and embeddings; only those chunks' metadata differs.

| Artifact | Value |
|---|---|
| Diff | `ident_v2_dryrun/ident_v2_metadata_diff.v3.json` (+ readable `.v3.md`) |
| sha256 | `eda16e32634a6e5a34cc091de773fa0e80ea809663d98f665f2a43a5fbfb0462` (`.v3.lock.json`) |
| Changes | 233 = A 213 ("Order N (rule not shown)" -> the official rule) + B 20 (label kept; later rule(s) in the same chunk recorded as `also_rules` + `rule_spans`) |
| Not applied | 16 REVIEW rows (12 whose current label is outside the official span, e.g. Order XXVII-A filed as Order XXVII; 4 where the official text puts the next rule in the chunk but the local copy shows no heading for it) |
| Read-only checks | `ident_v2_dryrun/build_checks.v3.json`: `pre_checks_passed: true`, `problems: []`, ident_v1 fingerprint `987f36c7...0787` unchanged by the checks |

Targets: `_0998` -> Order I Rule 10 (r.10(2), "Court may strike out or add parties"); `_1153` stays Order IX Rule 12 with
`also_rules` Order IX Rule 13 and the offset where r.13 begins; `_1154` -> Order IX Rule 13.

## 2. Official comparison

* Source: Pakistan Code, "Code of Civil Procedure (CPC), 1908" -- listed as **(Under Review)**; PDF
  `https://pakistancode.gov.pk/pdffiles/administrator6598dabbad120033d4d42d717dcf9755.pdf`, 318 pages, sha256
  `c51d194bfc14f076769f266db7efabc1901f1de2182da89c8f0ef82d92844b33`, retrieved 2026-10-15. The site says the Gazette is
  the original source: this is the best available official copy, not a certified one.
* Method: each `ident_v1` Order/Rule chunk is placed in the official text by unique 50-character fragments of its BODY
  text, sampled across the chunk; matches inside the official page-bottom footnote zones are dropped (local chunks carry
  footnotes inline). The rule headings at those positions give the rules the chunk spans. Labels come from the official
  text; a chunk not placed uniquely is left unchanged (never guessed).
* Every change in v3 additionally passes, in the build script's checks: the chunk's current ident_v1 label is the one the
  diff expects; the planned labels equal the official span; for multi-rule chunks, each later rule's heading is found in
  the chunk's own text, the cut pieces rebuild the chunk exactly, and each piece opens with its rule's heading.

## 3. A chunk holding two rules -- only the rule's own text supports a claim

Implemented in code (dev, uncommitted) and active with ident_v1 today through in-text headings; `rule_spans` in ident_v2
makes the cut points explicit and checked:

1. `cpc_provisions.split_rules` cuts a chunk at each rule boundary (recorded offsets first, otherwise a later rule's
   heading in the text); a short group heading before the next rule ("Setting aside Decree ex parte") moves with it.
2. The catalogue gives each rule only its slice (O.IX r.12 = text up to "...who do not appear."; O.IX r.13 = from
   "Setting aside Decree ex parte 2 [13. ..." plus its continuation chunk). Heading, text, mixed-clause and Order-scope
   checks all read that slice.
3. The drafter's law context shows a multi-rule chunk as separate `[STATUTE]` blocks, each under its own rule.
4. Tests (tests/test_draft_guard_v2.py): r.12's slice holds no "ex parte"/"decree"; a r.12 claim for setting aside is
   not supported and a r.13 claim is; recorded offsets cut where the text shows no heading; a malformed record is ignored.

## 4. Build safety (scripts/build_ident_v2.py; tests/test_build_ident_v2.py)

* Applies only a diff whose sha256 and class counts equal its `.lock.json`.
* Refuses -- before reading anything else -- if `ident_v2` already exists; never overwrites or removes it.
* Creates `ident_v2` with a random `build_run_id`; may delete ONLY a collection it created in the same run carrying that
  id (on an error mid-build or a failed verification). ident_v1 / any other collection is never a deletion target.
* After writing: every id, document and embedding equals ident_v1; metadata equals the plan for the 233 and is unchanged
  elsewhere; ident_v1's fingerprint is unchanged.
* 8 tests on an in-memory fake client; 4 mutations of the safety lines (run-id check, existing-target refusal,
  hash check, created-in-this-run check) each caught.

## 5. Rollback

`ident_v2` is separate. Until a separately approved switch, nothing reads it. After a switch, rollback is one constant
(`cpc_provisions.IDENT_COLLECTION` / the research variant) back to ident_v1, then deleting ident_v2.

## 6. Approval requested

1. Build `ident_v2` from diff v3 (sha256 `eda16e32...0462`): `python scripts/build_ident_v2.py --build`, backend stopped.
2. Later and separately: switch the drafter to ident_v2, then a dev-only measurement run.

Earlier drafts (the 272- and 237-change diffs) failed their checks and are superseded -- see
`ident_v2_dryrun/SUPERSEDED.md`. They must not be applied.

## 7. Measured embedding tolerance and the pre-switch retrieval gate (2026-10-15, isolated copies only)

The first live build failed only on "embedding byte-identical" (see `ident_v2_dryrun/EMBEDDING_ROUNDTRIP_FINDINGS.md`).
The build now checks, instead: every component within 1 float32 ULP; EXACT top-10 neighbours unchanged for every
vector; the new HNSW index at least as close to exact search as the source's. `--build` on the live store is refused
without `--live-approved`; `--store <copy>` works on an isolated copy and writes its own `.isolated` report.

* Build on a fresh isolated copy of the pre-build backup (diff v3): **post_checks_passed true**; 4,648 chunks, 233
  metadata changes; 4,414 vectors byte-identical, 234 within 1 ULP, 0 over; exact top-10 identical 4,648 / 4,648; HNSW
  agreement 4,595 (new) vs 4,594 (source); ident_v1 fingerprint unchanged. Report:
  `ident_v2_dryrun/build_checks.v3.isolated.json`.
* Retrieval gate (`scripts/ident_v2_retrieval_gate.py`, the drafter's real law-context path, 18 representative civil
  requests + dev V01-V08, holdout v3 topics excluded): expected provision present 17 -> **18 of 25**, **0 lost**,
  0 blocks under a wrong rule label, "rule not shown" blocks shown to the model 26 -> **0**. `gate_passed: true`
  (`ident_v2_dryrun/retrieval_gate.json`). Expectations are developer labels from the official headings (provisional).
* Live store: byte-identical before and after both runs. Earlier read-only client opens (diagnosis, replays) had changed
  `chroma.sqlite3` bookkeeping only: 19 of 20 collections are content-identical to the pre-build backup (ids, text,
  metadata, embeddings); the 20th, `judgments_collection_broken_2026_08_27`, cannot be read in either copy (pre-existing).
  All corpus reads now run on isolated copies.

Still needs separate approval: a live build (`--live-approved`), then the switch, then a dev-only model run.

## 8. Approved live build 2026-10-15 -- FAILED one check, own collection removed, NOT switched

Pre-build: no Python/uvicorn/Chroma process; live path backend/chroma_data (the app's PersistentClient path); 59 GB free;
original backup verified; fresh backup `chroma_data_backup_pre_live_build2` (91 files, byte-identical to live).
Result (`build_checks.v3.json`): pre-checks passed; 4,648 written; 233 metadata changes; vectors 4,414 identical +
234 within 1 ULP, 0 over; exact top-10 identical 4,648 / 4,648; **HNSW agreement new 4,586 < source 4,591 -> FAILED**;
own collection removed (run abf44650...); ident_v1 fingerprint 987f36c7... unchanged. Left behind: a second orphan HNSW
folder `f3dbf4e5-...` and chroma.sqlite3 bookkeeping (as the first failed build).
Why: HNSW agreement is noisy even for the UNCHANGED source (4,591 / 4,592 / 4,594 on identical files), so "new >=
source" compares two noisy numbers; it passed by 1 on the isolated copy and failed by 5 here. The criterion is flawed as
written. Proposal (not applied): measure the source's own run-to-run spread on an isolated copy and require the new
index to fall within it -- exact-kNN identity and the retrieval gate stay the hard checks. No retry without approval.

## 9. Live build #3 under the pre-registered gate -- PASSED and SWITCHED (2026-10-15, user-approved)

Pre-build: no Python/uvicorn/Chroma process (port 3000 = EonVPNRoutingService, unrelated); path backend/chroma_data;
58.6 GB free; fresh backup 3 `chroma_data_backup_pre_live_build3` (96 files, byte-identical to live); backups 1-2 intact.
Build (run 646c85cd...): gate 04806e18, diff eda16e32; 4,648 written; 233 metadata changes; 4,414 identical + 234 within
1 ULP, 0 over; exact top-10 4,648 / 4,648; HNSW 4,573 >= floor 4,569 (NOTE: below all 10 measured rebuilds, 4,579-4,595
-- passes the locked rule at its low edge); ident_v1 fingerprint 987f36c7... unchanged; post_checks_passed true.
Gate C on a BYTE COPY of live: 19 / 25 (ident_v1 18), 0 lost, 0 mislabelled, rule-not-shown 26 -> 0: passed.
Switch: corpus_index._DRAFTER_COLLECTIONS, cpc_provisions.IDENT_COLLECTION, exact_provision._RESEARCH_VARIANTS,
retriever._RESEARCH_IDENT -> ident_v2 (drafter AND lawyer research share it). Rollback: those four lines back to
ident_v1 (ident_v1 is untouched). Live orphans 9cd66922-... and f3dbf4e5-... untouched.
