# Batch 8: fail-closed AI summary, safe extraction input, lawyer-matching evidence (2026-10-17)

**Scope:** a focused safety fix; code and tests only.
- **Not done:** commit, live Chroma access, model or provider calls, snapshot, ingestion, index switch, deletion.
- **Kept as is:** existing uncommitted work.
- **Status:** passing tests do not make any output legally verified.

## 1. `case_service._public_case`: fail-open → fail-closed

**Before (batch 7):** if `case_cpc_view` raised, the error was logged and the **raw legacy `ai_summary`, Urdu summary and Urdu actions were returned unchanged**, looking exactly like a checked case.

**Now:**
- The case is still served. Every other field, including the client's own `description`, is unchanged.
- **No AI summary text leaves:** `ai_summary: null`; `ai_summary_localized` and `ai_actions_localized` are removed.
- `ai_summary_jurisdiction` is set to `{"status": "review_unavailable", "warning": {"en": "AI summary withheld: the jurisdiction check for this case's AI summary could not run, so the summary is not shown. The case's own description is not affected.", "ur": "…"}}`.
- The fallback (`source_currency.case_summary_unavailable`) uses plain dict operations only, so it cannot fail in turn. It also covers a view that failed *half way*.
- **This applies whatever the province, Punjab included.** If the check didn't run, nothing is known.

**Downstream:** the drafter's case context then uses the client's own `description` (`build_case_context` reads `ai_summary or description`), never the raw summary.

## 2. Document field extraction (`document_service.extract_fields`, `POST /documents/extract`)

**Before:** `description = case.description or case.ai_summary` meant that a case with an empty description fed the **raw stored `ai_summary`**, including an uncaveated Punjab-CPC legacy summary, to the extraction model as the case facts.

**Now:** the client's own description is always used first. Without one, the AI summary goes through `source_currency.summary_for_model_input`:

| Case (description empty) | Extraction |
|---|---|
| Legacy summary, non-Punjab or unknown province | **Stops**: 422 "This case has no description of its own, and its AI summary was written before the Code of Civil Procedure jurisdiction check, so it cannot be used to fill in a document. Add the case facts to the case description, then extract the fields again." **No model call.** |
| Jurisdiction check fails | **Stops**: 422 "…the jurisdiction check for its AI summary could not run just now… Add the case facts to the case description, or try again later." **No model call.** |
| Confirmed Punjab | the summary is used |
| Summary written after the CPC step (`ai_summary_cpc_checked`, or carrying the batch-6 notice) | the summary is used **without** its jurisdiction notice (a caveat, not a fact) |
| No description and no summary | unchanged: "Case has no description to extract fields from" |

## 3. Lawyer matching (`lawyer_service.match_lawyers_for_case`): evidence, behaviour unchanged

**What reads the summary:** `query_text = description or ai_summary or "<type> legal matter in <province>"`, so the summary is read only when the description is empty.

**How eligibility is decided:**
- Both candidate pools are filtered on the **case record's** `province` and `case_type`. The vector pool uses `_semantic_candidates(query_text, province, …)`; the database pool uses `user_repo.find_lawyers(province=, case_type=)`.
- The summary is used only as **similarity text**, which affects ranking and the semantic-fit evidence within those filters. A Punjab CPC citation in it cannot widen or move the province filter.
- Pinned by a test: a legacy summary that even names "the Punjab CPC" still produces province `sindh` and type `civil` in both pools.

**Assessment (corrected 2026-10-17):** the province and case-type filters are not affected. But the raw summary **can change lawyer RANKING**, which the client sees as the order and selection of suggested lawyers. Through the semantic score it can also change whether a candidate qualifies as "matched" or the result falls back to a general listing. This applies only to cases with an empty description.

So this **is** a user-visible effect, though not a jurisdiction-filter one. It is lower priority for the demo; **left unchanged and recorded as a limitation** (§6).

## 4. Files changed (this batch; uncommitted)

| File | Change |
|---|---|
| `backend/app/ai/source_currency.py` | `REVIEW_UNAVAILABLE`, `case_summary_unavailable`, `SummaryUnusable`, `summary_for_model_input` |
| `backend/app/services/case_service.py` | `_public_case` now fails closed |
| `backend/app/services/document_service.py` | `extract_fields` uses `summary_for_model_input` when the description is empty |
| `backend/tests/test_case_summary_fail_closed.py` (new) | 21 tests (unit, through the real read paths, the model stubbed) |
| `backend/tests/test_case_summary_fail_closed_integration.py` (new) | 3 tests (real HTTP API, test MongoDB) |

No frontend change.

## 5. Tests

**Unit and regression**
- **How it was run:** 123 files, one at a time, under the temporary-Chroma guard (`AAI_ALLOW_LIVE_CHROMA` not set), with `-m "not integration and not llm and not network"`. Run window: 2026-10-17 01:38–02:18 UTC.
- **Results:** **1,702 passed, 2 failed, 1 skipped**, 1,213 deselected (integration, run below).
- **Skipped:** `test_document_verification.py:45` needs the live Chroma corpus, so it was **not run**.

**New tests in this batch: 21 passed.**
- **Failed view:** for Sindh, Punjab and unknown, no raw summary, Urdu summary or Urdu actions are released; the status is `review_unavailable` with English and Urdu warnings; the case stays accessible; the stored dict is unchanged.
- **Half-way failure:** nothing is released.
- **Other paths:** the case list fails closed too, and the drafter's case context falls back to the client's description. A case with no AI summary is untouched by a failure, and the batch-7 view is unchanged when nothing fails.
- **Extraction:** for five legacy non-Punjab or unknown-province cases, the model is **never called**. A failed check also stops with no model call. Punjab is used. A checked summary is used without its notice. The description is preferred. The old empty-case message is unchanged.
- **Matching evidence:** the province and type filters come from the case record.
- **Mutation tests (3), each caught:** fail-open restored; the raw summary fed to extraction; a failed check ignored in extraction.

**The two failures: pre-existing, reported separately, not touched in this batch.** (Updated on 2026-10-17, after this batch, by your decision; see the note below.) `test_lawyer_case_id_contract.py`, case `"case workspace AI tab"`, expects `frontend/src/components/lawyer/CasesPage.jsx` to call `aiResearch(`. That call was removed by commit **`1ba40e7`** ("delete never-rendered components (WorkspaceAI, Documents/Timeline tabs, …)"). The test still lists the deleted tab, so it is stale; it fails at HEAD as well.
- **Lawyer Research is not affected:** the test's other surface, `AILegalPage.jsx`, passes.
- The test was **not** weakened or edited. Fixing it means either removing that surface from the test, if the tab is gone by design, or restoring a case-workspace research entry. That is a product decision.

**MongoDB integration (local replica set, throwaway `_test` databases)**
- **How it was run:** `AAI_TEST_MONGO_URL=mongodb://localhost:27018/?replicaSet=rs0`, `-m integration`. 32 files, 02:18–02:38 UTC.
- **Results:** **490 passed, 0 failed, 0 skipped.**
- **New, `test_case_summary_fail_closed_integration.py` (3):**
  - `GET /cases/{id}` with the view forced to fail returns 200, `ai_summary` null, status `review_unavailable`, no "Order VII" anywhere in the response, and the MongoDB document unchanged;
  - `POST /documents/extract` for a legacy Sindh case with no description returns **422** with the actionable message, and the stubbed model is **never called**;
  - with a description, the model receives the client's description and no CPC summary.
- **Also covered:** the batch-7 legacy-case integration test, intake (retry, routes, resume, recovery, evidence, retention, journey), cases (booking, draft lifecycle, files, uniqueness, integrity, retention, threads, validation, status filter, walk-in), and document integration files.

**Isolation:** 0 accesses to the live Chroma path, apart from the guard test's 15 deliberate probes.

## 6. What remains after this batch

1. **Lawyer matching** still uses the raw stored summary as similarity text when a case has no description. This **can change the suggested lawyers' order and which candidates qualify as "matched"**, which is user-visible, while never changing the province or type filter.
2. **A legacy summary is warned about, not corrected:** paraphrased CPC content can't be removed from free text. Re-running the analysis would need a model call.
3. **The risk rating is withheld, not re-estimated** (batch 7).
4. **The index still stores the Punjab CPC as `federal`.** The relabel (BATCH5 §6) and the live-store snapshot (BATCH3 §1d rev 2) remain separate approval steps.
5. **The stale `CasesPage.jsx` contract test** needs a product decision (above).
6. **No lawyer screen renders `ai_summary` or `ai_summary_jurisdiction` today.** A future screen must show the status, including `review_unavailable`.

---
**Follow-up (2026-10-17, your decision): the stale test was updated to the current contract.**
- **Research surface:** `tests/test_lawyer_case_id_contract.py` now declares the AI Legal page as the one research surface, keeping every check on it: `case_id`, the database `_id`, no case facts.
- **New discovery test:** **any** component that calls `aiResearch(` must be declared. A restored case-workspace tab therefore cannot skip the contract. A mutation check confirmed it catches an undeclared caller.
- **Case workspace:** still checked to send no case facts.
- **Results:** 6 passed; the test was not weakened.

