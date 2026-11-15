# Batch 3: trustworthy-baseline preflight and removal of unsafe silent index fallback (2026-10-16)

**Scope:** code-only safeguards with tests, plus plans.
- **Nothing executed against the live store.** No backend was stopped, no snapshot taken, no data changed, no collection created, no index switched, no model or provider called, nothing ingested, nothing committed.
- Parser v3 stays opt-in.
- **Unchanged from batch 2:** the live Chroma store must still **not be assumed unchanged** (BATCH2 §0).

## 1. Preflight (read-only)

### 1a. Route-by-route: required index, fallback before, behaviour now

| Route / output the user sees | Required index | Before (2026-10-15 tree) | Now |
|---|---|---|---|
| **Lawyer Draft Assistant**: `/ai/draft/stream` proposal card | criminal `__sec_v2` **and** civil `__ident_v2` | **Retrieval** (`build_retriever(..,"research_ident")`), **exact text** (`exact_provision.fetch(..,True)`) and the **legal check**'s index (`corpus_index.get_drafter_index`) each fell back to the base collection, and only the first logged a warning. The proposal could be checked against the base CPC labels (e.g. "Section 17 CPC" read as Order XI Rule 17) and still be marked supported. The CPC catalogue (`cpc_provisions.catalogue`) had no fallback; it raised a raw Chroma error. | A precheck runs before any retrieval or model call. If either index is missing, unreadable or not the verified build, the panel gets `guard {ran:false, reason:"corpus_unavailable", index:{status:"identity_index_unavailable", collection, problem}}` and `[DONE]`. There is no text, no model call, and no audit "answer". The panel's existing message for that reason reads: "The statute library could not be read, so the legal check could not run. This reply is not shown and nothing was added to the draft." **No frontend change.** |
| Lawyer research `/ai/research`, flag `RESEARCH_ANSWER_SAFEGUARDS` **on** | same two | Retriever → base civil, logged as a warning. Exact-provision lookup → base, **silent**. | The retriever raises `IdentityIndexUnavailable`. `retrieval_node` already turns that into `retrieval_error: True`, so the decision engine's "try again" outcome is a system fault, not "no law found". The research exact lookup no longer reads base: strict mode raises, non-strict returns "not found". |
| Lawyer research, flag **off** (the default) | base by design | base | **unchanged** |
| Client chat (`surface=client`) | base retrieval; exact lookup prefers `sec_v2` | Exact lookup: base where `sec_v2` was absent, silently | **Behaviour unchanged** (established policy). A missing criminal `sec_v2` is now **logged**. |
| Client intake | base (`retrieval_index_variant="base"`) | — | **unchanged** |
| Other `exact_provision.fetch` callers (`issue_lookup`, `tool_contract`, `legal_tools`, `visible_authority`) | as their `research` argument says | as above | Research mode follows the new rule. Client mode is unchanged. |

**What the fallback could affect, concretely:**
- **Drafter:** CPC Order/Rule citations judged against base labels, a "supported" mark on an authority that was never identity-checked, and exact text pulled from a mislabelled chunk.
- **Research (flag on):** the same base text presented as identity-retrieved.

### 1b. Review of the test-isolation guard (`tests/conftest.py`)

- **Order:** it is installed when pytest loads the conftest, **before any test module is imported**.
- **Redirect:** it points `app.db.chroma._CHROMA_PATH` at `%TEMP%/aai-test-chroma-*`, removed at session end.
- **Python file access:** an audit hook refuses open, sqlite3 connect, mkdir, listdir, scandir, remove, rename, replace, copy, rmtree, chmod and utime on any path with a `chroma_data*` component. Both source and destination are checked, and the check runs **before** the OS call. It is string-only; `realpath` would open the path on Windows.
- **Rust I/O:** `chromadb.config.System.__init__` refuses a persistent directory on such a path. chromadb 1.5.9 does its file I/O in Rust, which the audit hook cannot see.
- **Corpus tests:** the `corpus` tier is skipped.
- **Reporting:** each run prints the test store, every refused access, and how many persistent clients were opened.
- **Proof:** `tests/test_live_chroma_guard.py` proves the guard: decoy first, then probes of the live path that could not create anything.

**Escape hatch:** `AAI_ALLOW_LIVE_CHROMA=1` turns *all* of the above off.
- It is read from the **process environment only**, before any `app` import, so a value in `backend/.env` (read later by pydantic-settings) cannot switch it on.
- **I did not set it.**
- Weakness: it is one variable. A stricter version would also require a pytest option such as `--allow-live-chroma`, and refuse when the backend port is listening. Proposed, not done.

**Limits of the guard (stated, not hidden):**
- **Subprocesses:** a test that launches a subprocess is not covered, because audit hooks do not cross processes. I reviewed the 9 test files that spawn processes. None launches a Chroma-touching script; `analyzer_browser_smoke` refuses before it starts, and `build_analyzer_authorities --check` is network-tier.
- **Other native libraries:** any native library other than chromadb that opened store files directly would not be seen. `hnswlib` is not imported anywhere in `app/`, `scripts/` or `tests/`.

### 1c. Processes and ports (checked 2026-10-16, about 14:30 UTC; nothing stopped)
- **Listening:** 27017 (`mongod`, pid 5936) and 27018 (`mongod` replica set, pid 16604, the local dev DB).
- **Not listening:** 8000/8001 (no backend), 3000/3001 (no frontend), 11434 (no Ollama).
- **Processes:** no `python`, `uvicorn` or `chroma` process. `node` processes are the Playwright MCP server only.
- **Conclusion:** no backend or Chroma process appears to be running. Open file handles were **not** inspected (that needs Resource Monitor or Sysinternals `handle.exe`), so "nothing holds the store" is an inference, not a verified fact.

### 1d. Maintenance-window snapshot plan, **revision 2 (batch 4)**: NOT executed; needs your separate approval

**What changed from revision 1:**
- **Failed copies:** a failed or mismatched copy is **kept and reported**, never deleted.
- **Unverifiable handles:** if file handles cannot be verified, the plan **stops**; it is never inferred from ports or process names.
- **WAL/SHM:** handling for these files is specified.
- **Conclusions:** the limits are stated (no "bookkeeping only" claim is possible).
- **Restart:** removed from this plan; it is a separate decision.

**Scope:**
- **Covered:** snapshot and read-only inspection of the **copy**.
- **Excluded:** restore, swap, deletion, rebuild, backend restart, opening the live store as a database.
- **The live store is only ever read as files, by the copy tool.**

**Paths:**

| What | Exact path |
|---|---|
| Source (whole directory) | `C:\Users\The Laptop Hut\Desktop\attorney-ai\backend\chroma_data\` |
| Destination (new, outside the repository) | `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\chroma_data_<YYYYMMDDTHHMMSSZ>\` |
| Copy log | `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\chroma_data_<stamp>.robocopy.log` |
| Hash manifest | `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\chroma_data_<stamp>.manifest.json` |
| Inspection report | `C:\Users\The Laptop Hut\Desktop\chroma_snapshots\chroma_data_<stamp>.inspection.json` |

**Destination and permissions:**
- The destination is **outside the repository** (`Desktop\attorney-ai\…`) and outside the session scratchpad.
- Writing there is a filesystem action **you will be asked to approve** at the prompt, in addition to the approval below.
- The two orphan folders and any backups inside or beside `chroma_data` are copied byte-for-byte as part of the directory (if inside it) and **never opened, examined or changed**.

**Disk space:**
- **Known:** `chroma.sqlite3` = 642,129,920 bytes, read at about 13:46 UTC on 2026-10-16. The size of the segment folders is **not known**, because the directory has not been listed.
- **Required:** free space on the Desktop drive of at least **2.5 × the total measured in step 2**. Otherwise stop.

| Step | Action | Pass → next | Fail → (nothing deleted; reported to you) |
|---|---|---|---|
| 0 | Your approval (sentence below). | — | No action. |
| 1. Freeze | Stop the backend (`serve.py` window, Ctrl+C), the frontend dev server, any eval/ingest/build script and any Python REPL. MongoDB may keep running; it does not open Chroma. | — | — |
| 2. Verify nothing holds the store | **(a)** `Get-NetTCPConnection -State Listen` shows nothing on 8000/8001. **(b)** `Get-CimInstance Win32_Process` shows no python/uvicorn. **(c) File handles:** you open Resource Monitor → CPU → Associated Handles, search `chroma_data`, and confirm **zero** results to me. (Sysinternals `handle.exe` is not installed; downloading it would need separate approval.) Then measure the file count and total bytes (`Get-ChildItem -Recurse -File`, metadata only) and check free space. | All three are clean, and space ≥ 2.5×. | **Stop** if any handle is listed, **if handles cannot be verified at all**, or if space is short. Ports and process names alone are **not** enough. |
| 3. WAL/SHM check | List `chroma.sqlite3-wal` and `chroma.sqlite3-shm` (names and sizes only). | None present, **or** present with handles verified free in step 2: they are copied **together** with `chroma.sqlite3` and their presence is recorded as "WAL not checkpointed at shutdown". | If WAL/SHM exist **and** step 2(c) could not be verified: **stop** (a live writer may exist). |
| 4. Copy | `robocopy "<source>" "<destination>" /E /COPY:DAT /DCOPY:T /R:0 /W:0 /NP /LOG:"<copy log>"`. The source is only read. | robocopy exit code < 8 and "Failed: 0". | **Keep the partial copy and the log**, mark the manifest `"result": "copy_failed"`, report, stop. Cleanup only on your separate approval. |
| 5. Hash manifest | SHA-256 of every file in source **and** copy (`Get-FileHash -Algorithm SHA256`), written to the manifest (format below). | Every relative path present in both, with equal size and equal SHA-256. | `"result": "mismatch"`, keep everything, report the differing files, stop. |
| 6. Inspect the COPY only | **(a)** SQLite on the copy: `file:<dest>/chroma.sqlite3?mode=ro&immutable=1`, then `PRAGMA integrity_check`, the `migrations` rows, the collections list, and per-collection counts and metadata. **(b)** If a WAL was copied: make a **second** throwaway copy of the three files inside the destination, open it normally so the WAL is replayed, and repeat (a), so committed but not-yet-checkpointed changes are seen. **(c)** Compare with the build reports: `ident_v2` 4,648 / `ident-v2` / run `646c85cd…`; `sec_v2` 3,305 / `sec-v2` / `section-split-v2`; ident_v1 fingerprint `987f36c7…` (the `build_ident_v2.py` function, pointed at the copy). **(d)** Rows and files time-stamped 13:25–13:58 UTC 2026-10-16 (Run A): `embeddings.created_at`, `max_seq_id`, segment-file mtimes. | An inspection report is written. | Integrity failure or a mismatch is **reported as possible damage. Nothing is restored, swapped or restarted automatically.** |
| 7. Stop and report | I report the results and the limits below. **The backend is NOT restarted by this plan.** | — | — |

**Manifest format (`chroma-snapshot-manifest-v1`):**
```json
{"schema": "chroma-snapshot-manifest-v1",
 "source": "C:\\Users\\The Laptop Hut\\Desktop\\attorney-ai\\backend\\chroma_data",
 "destination": "C:\\Users\\The Laptop Hut\\Desktop\\chroma_snapshots\\chroma_data_<stamp>",
 "started_utc": "...", "finished_utc": "...",
 "preconditions": {"port_8000_listening": false, "python_processes": [], "handles_verified_by": "user, Resource Monitor",
                   "handles_found": 0, "wal_present": false, "shm_present": false, "free_bytes": 0},
 "files": [{"path": "chroma.sqlite3", "bytes": 0, "mtime_utc": "...", "sha256_source": "...", "sha256_copy": "..."}],
 "totals": {"files": 0, "bytes": 0},
 "result": "verified | copy_failed | mismatch"}
```

**What the inspection CAN and CANNOT conclude.** No pre-incident, same-time hash of the whole store exists. So:
- **Can show:**
  - the store's state **now** (integrity, counts, metadata);
  - whether the identity indexes equal their **verified builds** on the recorded markers and counts;
  - whether the ident_v1 fingerprint (which covers what `build_ident_v2.py` hashes) is unchanged;
  - whether any row or segment file carries a timestamp inside the Run A window. A timestamp there **proves a write happened**; it does not show what changed.
- **Cannot show:**
  - that "only bookkeeping changed" during Run A;
  - that embeddings, HNSW files or collections **not covered by a recorded fingerprint** are byte-identical to before;
  - what `chroma.sqlite3` contained before 13:34:03 UTC.
- Matching counts, markers and one fingerprint are **consistent with** no data change. They are **not proof** of it.
- The only stronger comparison is against an older backup whose own manifest verifies, and reading a backup needs your **separate** approval.

**Rollback choices (yours, after the report; none is part of this plan):**
1. Keep the store as is.
2. Compare against, or restore from, a verified backup. Each of these is a separate approval.
3. Rebuild an affected collection on a copy with the existing build scripts, then swap. This is a separate, approved change.

**Restarting the backend** is also yours to decide after the report, and never automatic after a failed integrity or collection check.

**Approval needed (one message, nothing broader implied):**
> "Approved: I have stopped the backend and frontend. Run BATCH3 §1d revision 2, steps 2–7: verify handles with me, copy backend/chroma_data to C:\Users\The Laptop Hut\Desktop\chroma_snapshots, write the SHA-256 manifest, and inspect the COPY only. Keep any failed or partial copy. No restore, swap, delete, rebuild or restart."

## 2. Code changes (uncommitted)

| File | Change |
|---|---|
| `app/ai/index_health.py` (new) | `check`/`require`/`require_all` give **ok, missing, unreadable or unverified** for an identity collection. The build marker and chunk count are pinned to the build reports (`sec_v2`: 3,305, `sec-v2`, `section-split-v2`; `ident_v2`: 4,648, `ident-v2`, run `646c85cd…`). `IdentityIndexUnavailable` is a subclass of `CorpusUnavailable`. Results are cached for 5 min when ok and 30 s when failed. **Limit:** cannot see damage inside HNSW files that a count and a one-row read do not touch. |
| `app/api/v1/routes/ai.py` | `/ai/draft/stream` prechecks `DRAFTER_IDENTITY_INDEXES` before retrieval and the model, giving the fail-closed `guard` event (§1a). It also adds `source_currency.drafting_rider` to the prompt. The comment that promised base fallback is corrected. |
| `app/ai/pipelines/retriever.py` | The `research_ident` variant requires the identity index (raises). Family and constitutional stay on base, which is their policy. Other variants are unchanged. |
| `app/ai/exact_provision.py` | Research lookups require the identity index; strict mode re-raises it unchanged. The client lookup is unchanged, but a missing criminal `sec_v2` is logged. |
| `app/ai/corpus_index.py` | `get_drafter_index` requires both identity indexes; no base substitution. |
| `app/ai/cpc_provisions.py` | `catalogue()` requires the verified `ident_v2` before reading it. |
| `app/ai/source_currency.py` (new) | CPC jurisdiction gate and Constitution as-of gate (§2a). |
| `app/ai/draft_guard.py` | Applies both gates to the panel's supported / not-checked / withheld lists. |
| `app/ai/nodes/generation_node.py` | Research only (flag on): the Constitution as-of rider when the question needs post-2012 constitutional law. |
| `tests/test_identity_index_safety.py` (new) | 21 tests (§3). |
| `tests/test_source_currency.py` (new) | 29 tests (§3). |
| `tests/test_draft_guard_v2.py`, `test_draft_assist_modes.py`, `test_draft_stream_verification.py`, `test_research_safeguards.py` | adjusted for the new behaviour (§3), and one wrong-province test added |

### 2a. Jurisdiction and currency gates (smallest safe versions)

**CPC, Punjab-sourced text.**
- **In Punjab:** unchanged.
- **Outside Punjab** (Sindh, KP, Balochistan, federal/ICT, or neutral):
  - **Legal check:** a CPC citation is never "supported". It is listed as *not checked: "the CPC text on file is the Punjab version; the Sindh text has not been verified"*, and the draft text stays for the lawyer to verify.
  - **Prompt:** the drafting prompt says the CPC text is Punjab's, and asks for a `[CPC provision as applicable in this jurisdiction]` placeholder instead of quoting it as local law.
- **Deliberately not done:** no claim that any provision's wording is identical elsewhere. There is no per-provision "safe" list, because the other jurisdictions' texts are not in the corpus to compare.
- **Next:** extract the Punjab-amended provisions from the Punjab Code PDF's footnotes; the Act XIV of 2018 citations are the start. That would let those few be *withheld* outside Punjab rather than merely marked unverified. It needs the federal text first.

**Constitution, text as of 28 Feb 2012.**
- **Never "supported" as current**, anywhere. Articles the 27th Amendment amended say "amended after 28 February 2012; the current text is not on file".
- **Omitted articles:** ~~a draft unit relying on Article 184, 186A or 191A ... is withheld~~. **Corrected in batch 4:** the Gazette also omits **Article 186** (s.31, PDF p.13), which batch 3 missed. The gate is now built from the full evidence table in BATCH4_CONSTITUTION_GATE.md §1: Articles 184, 186, 186A and 191A are withheld, while clause-level omissions are not.
- **Prompt notes:** drafting prompts, and research prompts (flag on) whose question needs post-2012 constitutional law, carry an as-of note. That covers the Federal Constitutional Court/FCCP, the 26th/27th Amendment, constitutional benches, Art. 175B+, Art. 191A and Art. 184(3). The note tells the model not to state current provisions from the old text, and to say the current text is unverified.
- **Not done:** no current consolidated text is invented or assembled. The 26th Amendment's article list is not verified, so it is not used.

**Client chat and intake: proposal only, not changed** (their retrieval policy was to stay untouched). The same two notes should reach client answers:
- a CPC answer to a non-Punjab client should carry "Punjab text; your province's version not verified";
- a question about the FCCP or the new courts should abstain with "current constitutional text not available".

This needs your decision, because it changes client-visible wording.

## 3. Tests

**How the tests were run**
- One file at a time, under the Chroma isolation guard. `AAI_ALLOW_LIVE_CHROMA` was not set.
- `-m "not integration and not llm and not network"`: no MongoDB, model or provider calls.
- First pass 14:48–15:26 UTC over 65 files: every test module that imports a changed module, plus the batch-2 set.
- Logs and JUnit XML per file are in the session scratchpad (`iso/b3`, `iso/b3fix`).

**First pass: 4 files failed, all caused by this batch's changes and all understood.**

| File | Failures | Cause | Resolution |
|---|---|---|---|
| `test_draft_assist_modes` | 23 | The fixture had no store, so the new precheck refused, as designed. | The fixture now states a healthy store (`index_health.require_all` stub). The unhealthy cases live in `test_identity_index_safety`. |
| `test_draft_guard_v2` | 17 | The helper defaulted to `province="sindh"`, so the new CPC gate (correctly) stopped marking CPC rules "supported". | The default is now `punjab`, the jurisdiction of the text on file, because these tests are about Order/Rule matching. A **new wrong-province test** pins that the same sentence in a Sindh draft is "not checked: Punjab version" and its text is kept. |
| `test_draft_stream_verification` | 1 | A source check assumed the only `[DONE]` comes after verification; the refusal stream has its own. | The check now uses the last `[DONE]`. |
| `test_research_safeguards` | 1 | A fake client returned `object()` for every collection, which `index_health` reports as unreadable. | The test now pins only the mapping, with health stubbed; health is tested separately. |

**After the fixes**, the 4 files were rerun at 15:28–15:30 UTC: 128, 28, 13 and 45 passed, 0 failed.

**Final, 65 files:**
- **Results:** **2,151 passed, 0 failed**, 123 skipped, 3 xfailed, 3 deselected.
- **New tests:** `test_identity_index_safety` 21 passed (4 of them mutation checks); `test_source_currency` 29 passed; `test_live_chroma_guard` 6 passed.

**Skipped:**
- **31 `corpus`-tier tests that need the real corpus, NOT run:**
  - `test_corpus_health` 22;
  - `test_dlite_fixture` 4;
  - `test_jurisdiction_handling` 3;
  - `test_document_verification` 1;
  - `test_retrieval_scope` 1.
- **92** templates that print no provision in that variant (by design).

**Expected failures (xfail, 3):**
- the wrapped-number heading (a known parser limitation);
- two gloss-list citations (unreadable by design).

**Deselected (3):** MongoDB `integration` tests in `test_v2_stage5`.

**Isolation:**
- **0** accesses to the live path refused, apart from the guard test's own 15 deliberate probes.
- A persistent client was opened only by `test_live_chroma_guard`, `test_retrieval_scope` and `test_corpus_health`, each on the **temporary** store.

**Mutation evidence:**
- `require()` / `require_all()` were replaced by the old "return the base collection" behaviour.
- Each of the 4 regression tests then **fails**: drafter stream, research retriever, research exact lookup, drafter index + CPC catalogue.
- The mutation tests assert those failures.

**Missing-index demonstration:** with `civil_collection__ident_v2` or `criminal_collection__sec_v2` absent from a fake store, the draft-assist stream emits only the `guard` event (`ran:false`, `reason:corpus_unavailable`, `index.problem:"missing"`) and `[DONE]`. Retrieval and the model are never called, and no audit row is written. The research retrieval step returns `retrieval_error: true` with zero chunks.

## 4. Proposed experiment (NOT run): current baseline vs parser-v3 scratch index

1. **Preconditions:**
   - your approval;
   - the §1d (revision 2) snapshot with a verified manifest and a clean inspection, or an approved alternative;
   - parser tests green (they are);
   - for each selected document, either its legal-status and licence blockers resolved, **or** the experiment explicitly labelled non-production research (Court-Fees and PECA are both still `commencement`/currency-blocked).
2. **Indexes:**
   - **(A) baseline:** read-only queries against a **copy** of the live store from the snapshot, never the live store.
   - **(B) candidate:** a scratch collection in `%TEMP%`, built from the same official PDFs (hashes in the registry) with `section-split-v3`, using the same local embedding model. No provider call and no live write.
3. **Questions:** `evals/legal_sources/pilot_questions_v0.jsonl` (dev split only). The **holdout stays locked** (sha256 22968604…) until the method is frozen.
4. **Labels:** provisional developer labels, marked so. Any accuracy number is reported **only** once a Pakistani lawyer has reviewed the labels it rests on.
5. **Measures, all per question:**
   - right provision @1 and @5;
   - omitted provisions returned as operative (target 0);
   - an operative section returned under a Schedule label (the Court-Fees "Schedule III" failure);
   - abstention when the needed text is not in the index.
6. **Output:** a JSON report with the index hashes, question-set hash, label provenance and per-question results. No aggregate "accuracy" headline unless lawyer-reviewed.

## 5. What remains unknown

- **Live store:** whether Run A (BATCH2 §0) changed anything beyond SQLite bookkeeping. Also unknown: whether `sec_v2` and `ident_v2` are present, readable and equal to their verified builds. The new `index_health` check will say so **at backend start-up / first drafter request**, but nobody has run it against the live store, and I have not.
- **Legal currency:**
  - the CPC text for every jurisdiction except Punjab;
  - Punjab amendments after 2018;
  - the Constitution after 28 Feb 2012 (the 26th Amendment in detail, and anything after the 27th);
  - Court-Fees rates;
  - PECA after the 2025 amendment and its pending challenges;
  - the Banking Mohtasib 30 vs 45 days;
  - when the Punjab Labour Code commenced.
- **Answer accuracy:** **not measured.** Nothing in this batch shows that answers or drafts are correct, only that unverified indexes and texts are no longer presented as verified. Any accuracy claim needs the §4 experiment and lawyer-reviewed labels.

## 6. Stop points (I will ask before any of these)
Stopping the backend; a live-store snapshot; changing live data; creating a scratch embedding collection; switching indexes; running a model; deleting anything material; committing.
