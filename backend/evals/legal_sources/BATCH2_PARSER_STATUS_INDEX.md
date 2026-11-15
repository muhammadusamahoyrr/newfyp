# Legal sources, batch 2: parser correctness, source status, index-state reconciliation (2026-10-16)

Scope: parser code, pure registry code, fixtures, tests, audit docs. **No data was
ingested, no index switched, no flag changed, no provider/model called, nothing
committed.** Unguarded regression runs DID open the live Chroma store; §0 records it, and the
store must not be assumed unchanged.

## 0. Incident: unguarded test runs opened the live Chroma store

**Do not read this report as saying the live store is unchanged. It may have changed.**

### What ran, and when (UTC, 2026-10-16)

**Run A (unguarded), 13:25:15 → 13:45:09.**
- **Files:** 30 files, sequential; per-file times were not recorded. Order: section_split_v3, section_repair, statute_omissions, exact_provision, answer_citations, citation_verification, citation_contract, citation_contract_chat, citation_currency, citation_grounding, template_citation_binding, **retrieval_scope**, retrieval_grader, statute_affinity, statute_affinity_deterministic, bail_statute_binding, **corpus_health**, corpus_as_of, corpus_ceiling, draft_guard, draft_guard_v2, visible_authority, build_ident_v2, draft_assist_modes, research_safeguards, eval_drafter_v2, petition_drafter, legal_sources_identity, legal_sources_registry, legal_sources_pilot.
- **Opened the live store:** `test_corpus_health.py` (connects at module import) and `test_retrieval_scope.py` (autouse module fixture). Each called `connect_chroma()`, which ran `mkdir(exist_ok)` and then `chromadb.PersistentClient(backend/chroma_data)`.
- **What those tests do with the client:** `get_collection` reads on the four statute collections; a BM25 build that reads `criminal_collection`; prune-stub checks. The single `add()` in `test_retrieval_scope.py` goes to `chromadb.EphemeralClient()` (in memory).
- **Not captured:** pass/fail totals. `pytest.ini` already sets `-q`, and my extra `-q` suppressed the summary.

**Run B (unguarded, the two files excluded), 13:49:31 → stopped by me at ~13:58.**
- **Completed (10 files):** section_split_v3 (71 passed, 1 xfailed), section_repair 41, statute_omissions 46, exact_provision 18, answer_citations 35, citation_verification 89, citation_contract 31, citation_contract_chat 3, citation_currency 29, citation_grounding 18. All passed.
- **Interrupted:** template_citation_binding, as the 11th file.
- **Live-store contact:** no file in this run connects at import. A runtime read cannot be ruled out, for example `retrieval_node.expand` → `law_graph.get_graph()` reads `chroma_data/law_graph.json`. Run C below shows whether any of these tests reach such a path.

**Run C (guarded, after isolation was proven), 14:03:31 → 14:15:04:**
- **Results:** all 30 files plus the guard test, 0 failed, with per-file times in §4.
- **Live store:** 0 accesses to the live path refused.
- **Client opens:** counting shows that only `test_retrieval_scope` and `test_corpus_health` open a persistent client at all. So in Run A, **those two files and no others** opened the live store.

### Evidence about the live store
- `chroma_data/chroma.sqlite3`: **LastWriteTimeUtc 13:34:03**, inside Run A; 642,129,920 bytes. Read once by `Get-Item` (metadata only) at about 13:46. **Not re-checked since**, and the file content was never opened.
- Whether the backend was running during Run A is **unknown**. Port 8000 was not listening at about 13:46.
- **Most likely cause:** client initialisation, meaning Chroma's migration check, a WAL checkpoint, or the Rust core's own bookkeeping. It is **not established** that no row, segment or HNSW file changed. Assessing it needs the procedure in §7.
- **Not touched:** the orphans and backups were not touched by these tests. `connect_chroma` opens only `chroma_data`, though chromadb itself may read the segment folders it owns inside it.

### Isolation now in place (`tests/conftest.py`, installed before any test module is imported)
1. `app.db.chroma._CHROMA_PATH` is pointed at a fresh `%TEMP%/aai-test-chroma-*`, which is removed at session end.
2. An audit hook refuses, *before* the OS call, any Python open, sqlite3 connect, mkdir, listdir, scandir, remove, rename, replace, copy or rmtree on a path with a `chroma_data*` component. For rename and copy, the source and the destination are both checked.
3. `chromadb.config.System.__init__`, which every chromadb client goes through, refuses a persistent directory with such a component. This covers chromadb's Rust I/O, which the audit hook cannot see.
4. `corpus` tests are skipped. `AAI_ALLOW_LIVE_CHROMA=1` is the only way to turn all of this off.
5. The terminal summary prints the test store and every refused access.

`tests/test_live_chroma_guard.py` (6 tests) proves the isolation:
- **Decoy first:** every refusal is proven on a decoy `tmp_path/chroma_data`, which is never created.
- **Then the real path:** read-only probes of names that do not exist (open, sqlite `mode=ro`, listdir) plus `law_graph.json`. If the guard were absent these could only raise FileNotFoundError or read; they could not write.
- **Result:** 6 passed, 14:00:18, with 15 refusals listed.

**Import audit:** `--collect-only` was run for all 30 files under the guard, 14:00:40 → 14:03:00. Result: **0 refused accesses, 0 collection errors**. That includes `test_corpus_health`, whose import-time connect now lands in the temporary store.

**Static audit:** the tests load these scripts: ingest_statutes, build_sec_v2_index, build_ident_v2, eval_drafter_v2, pilot_legal_sources, citation_grounding_report (text only), build_law_graph (text only), eval_statute_affinity, prune_toc_stubs (name only) and build_ident_index. Every one of them calls `connect_chroma` only inside functions, never at module level.

`app/ai/pipelines/law_graph.GRAPH_PATH` is the one other live-store path in `app/`. It is read lazily and is now refused under the guard.

## 1. Phase 1: the ident_v1 / ident_v2 discrepancy

| Claim | Where | True? |
|---|---|---|
| "ident_v1 remains active" | `INDEX_REPAIR_PROPOSAL.md` lines 3-4 (header written before build #3); memory `drafter-eval-v2.md` lines 34-35 | **Stale.** Written before the 2026-10-15 build |
| "civil ident_v2 (active for drafter/research)" | batch-1 README §2 | **Overstated.** Code-referenced, not verified healthy; research only with a flag |

**What actually happened**, from `INDEX_REPAIR_PROPOSAL.md` §9 and `build_checks.v3.json`:
- **Build:** on 2026-10-15, build #3 was approved and run (run 646c85cd; gate 04806e18; diff eda16e32). It wrote 4,648 chunks and changed metadata on 233; HNSW 4,573 vs floor 4,569, at the low edge; ident_v1 fingerprint 987f36c7 unchanged; `post_checks_passed: true`.
- **Switch:** four constants were then switched to `civil__ident_v2`, **in the working tree only (uncommitted)**:
  - `corpus_index._DRAFTER_COLLECTIONS` (M vs HEAD);
  - `retriever._RESEARCH_IDENT` (M);
  - `cpc_provisions.IDENT_COLLECTION` (file untracked);
  - `exact_provision._RESEARCH_VARIANTS` (file untracked).

**Which module reads what (code paths, today):**

| Module | Criminal | Civil | Condition |
|---|---|---|---|
| Drafter (`corpus_index.get_drafter_index`) | `sec_v2` | `ident_v2` | always |
| Lawyer research | `sec_v2` | `ident_v2` | only `RESEARCH_ANSWER_SAFEGUARDS=on` (default **off** → base) |
| Intake, client chat | base | base | `retrieval_index_variant="base"` |
| Exact-provision lookup | prefers `sec_v2` | base / ident per variant | — |
| `cpc_provisions.catalogue()` | — | `ident_v2` | **no fallback, raises if missing** |

**Separating "points to" from "healthy":**
- **Points to:** the code points to ident_v2 for the drafter.
- **Healthy:** **not verified in this batch.** The only health evidence is the 2026-10-15 post-build checks. The store was deliberately not opened (and see §0).
- **Fallback:** if ident_v2 were missing, the retriever, `exact_provision` and `corpus_index` fall back silently to the **base** civil collection, **not to ident_v1**. Only the retriever logs a warning.

**Correction to the batch-1 audit:** README §2 now reads "code-referenced by the drafter (research only with flag), health unverified". There is no second contradiction about ident_v1 being a live fallback, because it is not one.

## 2. Phase 2: the statute splitter, versioned

**Versioning:**
- `split_provisions(text, version="section-split-v2")`: v2 is unchanged and remains the default. Every indexed chunk was built with it.
- `"section-split-v3"` is opt-in:
  - `scripts/ingest_statutes.py --split-version section-split-v3`; the default stays v2;
  - in v3, the contents region is never chunked;
  - `build_sec_v2_index.py` is pinned to v2 explicitly.

**v3 rules**, each admitted only if its number fits between its neighbours:

| Rule | Recognises | Guarded by |
|---|---|---|
| bracketed insertion | `3[26A. Title` at line start | strictly in order |
| parenthesised lettered | `(2E) Title.—` / `,__` | heading dash required; strictly in order |
| underscore heading | `11.___Procedure` | in order |
| footnote artifact | drops a v2 head `1S. 153B was ins. by …` | footnote shape only |
| omission marker | body is only `[* * *]`, `[Repealed]`, `Rep./Omitted by…`, or title + asterisks | title must end at its dash; trailing CHAPTER/ALL-CAPS/`D.—` lines ignored |
| contents page | text before the Act restarts at `1. Short title` after a SCHEDULE line | region `contents`, never read as provisions |

**Rejected:** dropping backward-numbered heads after a lowercase line (the `5. Thousand` wrap). The full audit showed it deleted 32 real CPC Order "Rule 1" headings and CrPC ss.94, 126 and 165. It is kept as a strict-xfail known limitation.

### 2a. Before/after: Court-Fees Act 1870 (Pakistan Code PDF, sha256 a5cdc51c…)

**v2 was wrong for the whole Act.**
- v2 read the 50 **contents-page lines** as the provisions (median 54 chars each).
- It read a SCHEDULE line inside the contents as the start of the schedules, so **the entire operative text was filed as "Schedule III"**.
- (Ingestion's `_drop_toc_stubs` then removes the stubs, which leaves the Act's text indexed only under a schedule label.)

| Provision | v2 | v3 |
|---|---|---|
| contents page | 50 "provisions" (stubs) | 1 `contents` block, not chunked |
| 1, 1-A, 3–14, 17–19, 19-A, 19-C, 19-E–19-J, 20–23, 25–30, 32, 34–36, 35-A | text inside **Schedule III** | own body provision |
| 15, 19-B, 19-D, 19-K, 33 | stub; text inside Schedule III | own body provision |
| 2 (appears twice), 16, 24, 31 | inside Schedule III, status not recorded | **omitted** (body is an omission marker only) |
| Schedules I, II | v2: 2+2 blocks starting in the contents | 2 schedule blocks from the real schedules |

### 2b. Before/after: PECA 2016 (Pakistan Code PDF, sha256 b096696f…)

| v3 provision | Previously misfiled inside (v2) | Rule |
|---|---|---|
| 22-A | 22 | bracketed |
| 24-A | 24 | bracketed |
| 26-A (false/fake information) | 26 | bracketed |
| 29, 30, 30-A | 28 | bracketed |
| 43-A, 45-A, 50-A, 51-A | 43, 45, 50, 51 | bracketed |
| 2-E, 2-F, 2-G, 2-H, 2-I, 2-J, 2-K | 2-D | parenthesised |
| 2-S, 2-T | 2-R | parenthesised |
| 2-W | 2-V | parenthesised |

- **Totals:** +20 provisions, 0 lost, 0 newly omitted. The v2 blocks shortened were 22, 24, 26, 28, 43, 45, 50, 51, 2-D, 2-R and 2-V.
- **Fix to batch 1:** batch-1 listed "8 inserted provisions"; the audit finds 20.

### 2c. Other Acts (whole-document audit, `scripts/audit_split_versions.py`)

| Act | Added | Lost (all footnote artifacts) | Newly omitted |
|---|---|---|---|
| CPC (Punjab Code) | +5 | 1-S | 7 (4, 6, 7, 9-A, 17, 22, 63) |
| PPC | +47 (incl. 489-F, previously inside 489-D) | 1-S, 3-S, 14-S (7 blocks) | 15 |
| CrPC | +84 | 6-S, 7-S, 8-S | 22 |
| Limitation, DMMA | 0 | 0 | 0 |

Every newly omitted block was printed and checked: each is marker-only.

**Known defects not fixed:**
- the wrapped-number heading (xfail);
- a mid-line `7 [8.` in CPC is not split;
- Limitation has a bogus "228" label (from v2, unchanged);
- ingestion's `_strip_contents` misses the Court-Fees contents (v3's contents rule covers it).

### 2d. Label impact on the live index (reported, not applied)

**No indexed chunk was changed.** If a future approved re-ingest used v3:
- Court-Fees chunks would move from "Schedule III" to their sections;
- PECA, PPC and CrPC would gain the provisions above;
- 7 + 15 + 22 + 4 provisions would carry `provision_status=omitted` and be dropped by the evidence gate.

Any such re-ingest needs its own approval, a snapshot (§7) and lawyer-reviewed labels.

## 3. Phase 3: source status (checked 2026-10-16, UTC times)

**How URL status is recorded now:** `url_status` is derived from recorded checks (`registry.url_status_from_checks`).
- A 403 is `blocked` and a timeout is `timeout`.
- A 404 is `not_found_confirmed` only after 2 or more consecutive 404s at least 24 h apart, with no success since.
- `text_authority` separates a Gazette from an official consolidated "information only" text.

| Source | URL | Result | Status | What it does / does not establish |
|---|---|---|---|---|
| KP Code | https://kpcode.kp.gov.pk/homepage/ | 200 text/html 13:35:28 (root 200 13:35:29) | **ok** | Batch-1's "404" came from one failed fetch and is **withdrawn**. Contents and licence not read. |
| Punjab Code CPC PDF | https://punjabcode.punjab.gov.pk/uploads/articles/THE_CODE_OF_CIVIL_PROCEDURE,_1908.pdf | 200 application/pdf 13:35:31 | **ok** | You saw a timeout separately; a timeout ≠ missing. The bytes match the indexed copy (sha256 528384…). |
| Punjab Laws, CPC amendment page | https://punjablaws.gov.pk/laws/2706.html | 404 HEAD 13:35:32, 404 GET 13:35:45, 404 via http:// 13:36:08 | **not_found_unconfirmed** | Same-day repeats are one occasion; you saw a timeout separately. A search engine still indexes this URL as "The Code of Civil Procedure (Punjab Amendment) Act 2018", so it may have moved. |
| PAP bill record | https://www.pap.gov.pk/bills/details/en/20/267 | 200 13:43:51 | ok | Bill No. 7 of 2018 only (`official_bill_record`) |
| 27th Amendment, NA copy | https://www.na.gov.pk/uploads/documents/691ec19a6a212_270.pdf | 200 13:36:10; one GET 13:42:38 | ok | **Gazette read** (see below). sha256 303d09fa… |
| 27th Amendment, Balochistan PA copy | https://pabalochistan.gov.pk/storage/8816/69174fbda0981_Twenty-seventh-Amendment-Act,-2025..pdf | 404 13:36:09 | not_found_unconfirmed | another copy of the same Gazette; not needed |
| PECA (Amendment) Act 2025, NA | https://na.gov.pk/uploads/documents/679b243193585_457.pdf | 200 application/pdf 13:43:49 | ok | reachable; **not downloaded or read**, so identity is unverified |

**Constitution and FCCP.** Verified from the Gazette PDF itself (scanned; poor OCR):
- Constitution (Twenty-seventh Amendment) Act, 2025, **Act No. XXXII of 2025**;
- Gazette of Pakistan, Extraordinary, Part I, Thursday 13 Nov 2025 [2307(2025)/Ex. Gaz.];
- assent 13 Nov 2025; s.1(2) "shall come into force at once";
- 56 amending sections, 23 pages.

Located **by heading only**:
- s.21 inserts a new Chapter (Art.175E "Original jurisdiction of Federal Constitutional Court");
- s.29 omits Art.184;
- s.40 amends Art.199;
- ss.19–20 amend Arts.175 and 175A;
- ss.22–28 amend Arts.176–183.

**Cannot be verified yet:**
- the wording and effect of the FCCP provisions (a lawyer's reading is needed, and the OCR is too poor to index);
- a current official **consolidated** Constitution; the indexed text is "as modified up to 28 Feb 2012";
- whether any amendment after the 27th exists. Secondary sources (mid-2026) describe a 28th as only proposed: [Wikipedia: 28th Amendment](https://en.wikipedia.org/wiki/Twenty-Eighth_Amendment_to_the_Constitution_of_Pakistan), [South Asia, Jul 2026](https://southasia.com.pk/2026/07/04/charter-of-convenience/).

**CPC provenance and territorial scope:**
- The indexed CPC is the **Punjab Code** consolidation, mislabelled federal.
- Its own footnotes cite, 20 times, the **Code of Civil Procedure (Punjab Amendment) Act 2018 (XIV of 2018)**, "published in the Punjab Gazette (Extraordinary), dated: 20 March 2018, pp. 6695-6698". Examples: s.2 substitutes "Court of Small Causes"; s.3 omits a provision.
- It also cites older Punjab and West Pakistan instruments (1934, 1957) and federal amendments up to Ordinance XXXIV of 2002.
- It is therefore Punjab's version: it must not answer for Islamabad, Sindh, KP or Balochistan.
- Now recorded as its own record, `pk.punjab.cpc-1908-punjab-code`.
- The amendment record now carries "Act XIV of 2018". **The Punjab Gazette itself and the Act's commencement clause have not been read.**
- Whether any Punjab amendment exists after 2018 is unverified. The "2020 Ordinance" was seen only on a law-firm site.

**Unresolved: no primary instrument read (unchanged, deliberately):**

| Question | Why it stays open |
|---|---|
| Court-Fees rates (which province, which schedule amendments) | the consolidation states no amended-up-to date; provincial rate instruments are not identified |
| PECA status after the 2025 amendment | NA PDF not read; constitutional petitions reported only by secondary sources ([Khalid Zafar & Associates](https://khalidzafar.com/laws-of-pakistan/prevention-of-electronic-crimes-amendment-act-2025/), [The News](https://www.thenews.pk/print/1412481-free-speech-concerns-rise-over-peca-amendments)) |
| Banking Mohtasib bank-response period, 30 vs 45 days | the amending instrument has not been read from the Gazette; official pages 404/403 |
| Punjab Labour Code 2026 commencement | no Gazette notification number or date found |

## 4. Tests

### 4a. Results

Each file was run alone with `venv/Scripts/python.exe -m pytest tests/<file>.py -p no:cacheprovider -rfEsx --junitxml=…`, under the isolation described in §0.

**Run C (guarded): 14:03:31 → 14:15:04 UTC, one file at a time.** Logs and per-file JUnit XML are in the session scratchpad (`iso/run1`).

| File | UTC | Result | Live-store accesses refused |
|---|---|---|---|
| `test_live_chroma_guard` | 14:03:31–14:03:50 | 6 passed | 15 |
| `test_section_split_v3` | 14:03:51–14:04:11 | 71 passed, 1 xfailed | 0 |
| `test_section_repair` | 14:04:11–14:04:37 | 41 passed | 0 |
| `test_statute_omissions` | 14:04:37–14:04:58 | 46 passed | 0 |
| `test_exact_provision` | 14:04:58–14:05:18 | 18 passed | 0 |
| `test_answer_citations` | 14:05:18–14:05:35 | 35 passed | 0 |
| `test_citation_verification` | 14:05:36–14:05:58 | 89 passed | 0 |
| `test_citation_contract` | 14:05:58–14:06:23 | 31 passed | 0 |
| `test_citation_contract_chat` | 14:06:23–14:06:41 | 3 passed | 0 |
| `test_citation_currency` | 14:06:41–14:06:59 | 29 passed | 0 |
| `test_citation_grounding` | 14:07:00–14:07:35 | 18 passed | 0 |
| `test_template_citation_binding` | 14:07:35–14:08:14 | 410 passed, 92 skipped, 2 xfailed | 0 |
| `test_retrieval_scope` | 14:08:14–14:08:33 | 9 passed, 1 skipped | 0 |
| `test_retrieval_grader` | 14:08:34–14:08:52 | 6 passed | 0 |
| `test_statute_affinity` | 14:08:53–14:09:12 | 46 passed | 0 |
| `test_statute_affinity_deterministic` | 14:09:12–14:09:32 | 6 passed | 0 |
| `test_bail_statute_binding` | 14:09:32–14:09:49 | 22 passed | 0 |
| `test_corpus_health` | 14:09:49–14:09:53 | 22 skipped | 0 |
| `test_corpus_as_of` | 14:09:53–14:10:21 | 29 passed | 0 |
| `test_corpus_ceiling` | 14:10:21–14:10:44 | 12 passed | 0 |
| `test_draft_guard` | 14:10:45–14:11:04 | 38 passed | 0 |
| `test_draft_guard_v2` | 14:11:05–14:11:30 | 127 passed | 0 |
| `test_visible_authority` | 14:11:30–14:12:03 | 48 passed, 1 warning | 0 |
| `test_build_ident_v2` | 14:12:04–14:12:28 | 16 passed | 0 |
| `test_draft_assist_modes` | 14:12:28–14:12:48 | 28 passed | 0 |
| `test_research_safeguards` | 14:12:48–14:13:11 | 45 passed, 1 warning | 0 |
| `test_eval_drafter_v2` | 14:13:12–14:13:54 | 28 passed | 0 |
| `test_petition_drafter` | 14:13:55–14:14:12 | 10 passed | 0 |
| `test_legal_sources_identity` | 14:14:12–14:14:29 | 30 passed | 0 |
| `test_legal_sources_registry` | 14:14:30–14:14:47 | 25 passed | 0 |
| `test_legal_sources_pilot` | 14:14:47–14:15:04 | 5 passed | 0 |

**Totals:** 1,327 passed, **0 failed**, 115 skipped, 3 xfailed.

**Skips and xfails, explained:**
- **92 skipped:** templates that print no provision in that variant (by design).
- **23 skipped:** `corpus` tier tests — `test_corpus_health` 22, `test_retrieval_scope` 1. They need the live store, so **they were not run this batch**.
- **3 xfailed:**
  - the wrapped-number heading (known limitation);
  - two gloss-list citations, unreadable by design.
- **Warnings:** 1 each in `test_visible_authority` and `test_research_safeguards`; neither is a failure.

**Re-runs with persistent-client counting** (14:16–14:19 for the Run B files, 14:19–14:26 for the rest). Only `test_retrieval_scope` and `test_corpus_health` open a persistent client, one each, now on the temp store. **The other 28 files open no client and touch no `chroma_data` path.** The 10 files that completed in Run B therefore did not reach the live store.


### 4b. Mutation tests

`test_section_split_v3.py::test_mutants_are_caught` disables each critical boundary in turn and requires the fixture audit to notice:

| Mutant | Caught |
|---|---|
| bracketed rule never fires | ✓ |
| parenthesised rule never fires | ✓ |
| paren heading without dash allowed | ✓ |
| footnote-artifact rule never fires | ✓ |
| `_marked_omitted` always False | ✓ |
| `_marked_omitted` always True | ✓ |
| `_contents_end` returns 0 | ✓ |
| `_admit_in_order` admits everything | ✓ |

**Fixtures:**
- **What they are:** 18 contiguous, unedited excerpts of official texts (Pakistan Code; Punjab Code for CPC). Each has its URL, source sha256 and character offsets in `tests/fixtures/statute_split/MANIFEST.json`.
- **What they exclude:** no third-party text and no personal data.

## 5. Files changed (this batch; all uncommitted)

| File | Change |
|---|---|
| `backend/app/ai/section_repair.py` | v3 splitter (opt-in); v2 untouched |
| `backend/scripts/ingest_statutes.py` | `--split-version` (default v2); v3 skips the contents region |
| `backend/scripts/build_sec_v2_index.py` | pinned to v2 explicitly (file was already untracked) |
| `backend/scripts/audit_split_versions.py` | new: v2-vs-v3 audit, PDFs to JSON, refuses chroma paths |
| `backend/tests/fixtures/statute_split/*` | new: 18 official excerpts + MANIFEST |
| `backend/tests/test_section_split_v3.py` | new: v3, adversarial, mutation and ingestion-wiring tests |
| `backend/app/ai/legal_sources/registry.py` | `URL_STATUS`, `url_status_from_checks`, `TEXT_AUTHORITY`, `gazette_reference`, `url_checks`; validation |
| `backend/tests/test_legal_sources_registry.py` | URL-status, Gazette vs consolidation, Punjab-CPC separation tests |
| `backend/data/legal_sources/candidate_registry_v0.json` | v0.2: checks, text authority, KP Code ok, 2 new records (27th Amendment Gazette; Punjab Code CPC) |
| `backend/evals/legal_sources/README.md` | corrections: ident_v2 wording, KP Code, CPC amendment |
| `backend/evals/legal_sources/BATCH2_PARSER_STATUS_INDEX.md` | this report |
| `backend/tests/conftest.py` | live-Chroma isolation: temp store before any test import, audit-hook + chromadb System guard, corpus tier skipped, refusals reported, temp store removed |
| `backend/tests/test_live_chroma_guard.py` | new: proves the guard (decoy first, then non-creating probes of the live path) |

**NOT touched:**
- no ingestion, re-embedding, scratch collection, index switch, flag change, model or provider call, bulk download, or commit;
- the orphan folders and both backups were not opened, listed or removed;
- `backend/.env` was not read or modified;
- no frontend file and no lawyer UI.

**Exception:** the live Chroma store *was* opened by two test files during unguarded Run A (§0). Its `chroma.sqlite3` modification time changed and it **must not be assumed unchanged**. It has not been opened, copied, restored or cleaned since.

## 6. Recommended next isolated retrieval experiment (proposal only)

**"Does v3 splitting change exact-provision retrieval for inserted and omitted provisions?"**

1. **Prerequisites:** your approval; the §7 snapshot (or an agreed no-live-store method); parser tests green (they are).
2. **Documents:** PECA and Court-Fees only, both Pakistan Code consolidations with `public_official_information_only` licences. This is **non-production research**: their currency blockers (amended-up-to date, PECA petitions) remain open.
3. **Method:**
   - Build two **scratch** collections from the same PDFs in a fresh scratch directory, one with v2 and one with v3, using the existing local embedding model. No provider call.
   - Query set: exact-provision questions for every provision in §2a–2b, plus omitted-provision traps (Court-Fees ss.2, 16, 24, 31). Write it **before** the run, and have a Pakistani lawyer review the expected labels.
4. **Measures:**
   - right-provision@1 and @5;
   - omitted provisions returned as operative (must be 0);
   - a Schedule label returned for an operative section.
5. **No accuracy claim** until those numbers exist and the labels are lawyer-reviewed.

## 7. Proposed: consistent snapshot to assess the SQLite change (NOT run; needs your separate approval)

Purpose: find out what, if anything, Run A changed in `backend/chroma_data`. The live store is never opened in place. Everything is examined on a verified copy.

**Step 0 — Preconditions (you confirm each):**
- the backend (uvicorn/serve.py), the frontend proxy, any eval or ingest script and any Python REPL are stopped;
- `Get-NetTCPConnection -State Listen` shows nothing on :8000;
- Resource Monitor → CPU → Associated Handles, searching "chroma_data", shows **no handles**;
- 2× free disk space for the store.

**Step 1 — Snapshot (copy only; the live store is read sequentially, not opened as a database):**
- **Source:** `C:\Users\The Laptop Hut\Desktop\attorney-ai\backend\chroma_data\`. It holds `chroma.sqlite3` (642,129,920 bytes at 13:34Z) plus one folder per segment. The orphan folders are copied as part of the directory but are not examined.
- **Destination:** `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\chroma_data_<UTCSTAMP>\`, outside the repo.
- **Command:**
  ```
  robocopy <src> <dst> /E /COPY:DAT /DCOPY:T /R:0 /W:0 /NP /LOG:<dst>.robocopy.log
  ```
  It must report 0 failed files.
- **Manifest:** relative path, size, mtime and sha256 for **every file in source and copy**, computed after the copy while nothing is running. They must match exactly, or the snapshot is void and is deleted (the copy only).
- **Size:** record the total bytes and the file count in the manifest.

**Step 2 — Assess (on the COPY only):**
- **SQLite:** open the copy with `file:<copy>/chroma.sqlite3?mode=ro&immutable=1` (no WAL replay, no writes):
  - `PRAGMA integrity_check`;
  - `migrations` (any `applied_on` dated 2026-10-16 means Run A migrated the schema);
  - `collections` and per-collection row counts from `embeddings`/`segments`, compared with `INDEX_REPAIR_PROPOSAL.md` §9 (sec_v2 3,305; ident_v2 4,648; ident_v1 4,648, fingerprint 987f36c7);
  - `embeddings_queue` / `max_seq_id`, comparing the highest seq_id and any `created_at` between 13:25Z and 13:58Z;
  - whether `chroma.sqlite3-wal` / `-shm` existed in the copy.
- **Segments:** list each segment folder's file mtimes in the copy. Any mtime between 13:25Z and 13:58Z flags an HNSW write.
- **Fingerprint:** recompute the ident_v1 fingerprint with the function `build_ident_v2.py` used, pointed at the copy's path. This is read-only and builds no client on the live path.

**Step 3 — Report:** one of three outcomes:
- **(a)** metadata or bookkeeping only (mtime, WAL), with no row, count or fingerprint change;
- **(b)** rows, seq_ids or segment files changed, listed exactly;
- **(c)** integrity failure.

**No rollback or cleanup without a further decision from you.**

**Step 4 — Rollback options, for your decision, only if (b) or (c):**
1. Keep as is, if the changes are benign bookkeeping.
2. Restore from the newest backup whose own manifest verifies. This needs your approval to *read* the backup, which this batch did not touch.
3. Rebuild the affected collections with the existing build scripts on a copy, then swap. That is a separate approved change.

**Cleanup:** the snapshot stays until you approve deleting it. Nothing is deleted automatically, and the live store, orphans and backups are never cleaned by this procedure.
