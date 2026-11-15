# Batch 7: legacy lawyer case summaries and the CPC-influenced risk rating (2026-10-17)

**Scope:** code and tests only.
- **Not done:** commit, live Chroma access, model call, snapshot, ingestion, index relabel or switch.
- **Kept as is:** Batch 6 work was not repeated; the dirty worktree is preserved.
- **Status:** passing tests do not make any output legally verified.

## 1. Trace: who reads a case's AI summary

| Reader | Field read | Path | Visible to whom | Before this batch |
|---|---|---|---|---|
| `GET /cases/{id}`, `GET /cases` (lawyer, client, admin) | `ai_summary`, `ai_summary_localized.ur`, `ai_actions_localized.ur` (pass through `CaseOut`, `extra="allow"`) | `case_service.get_case` / `list_cases` → `_public_case`; admin via `admin_service` → `_public_case` | Any API consumer. **No current lawyer or client screen renders these fields** (searched the frontend for `ai_summary`, `aiSummary`, `ai_summary_localized`, `ai_actions_localized`: no hits). | Legacy summaries were served as written, with no jurisdiction caveat. |
| Lawyer Draft Assistant (case-bound) | `ai_summary` → `case_context.build_case_context` → prompt "CASE CONTEXT" block (capped at 1,500 chars) | `ai_draft_stream` → `get_case` → `_public_case` | Goes into the model's prompt; the draft's legal check then runs (batch 5). | A legacy CPC summary was fed in uncaveated. |
| Lawyer Research (case-bound) | `title` / `description` (whitelist `_CASE_CONTEXT_FIELDS`), **not** `ai_summary` | `_approved_case_context` | — | not affected |
| Lawyer matching | `description` or else `ai_summary`, as a search query | `lawyer_service.match_lawyers_for_case` (raw repository read) | Ranking only; not shown | Unchanged (§4) |
| Document field extraction | `description` or else `ai_summary`, model input | `document_service` (raw repository read) | Extracted fields | Unchanged (§4) |

**Who reads the risk rating:** it exists only on the intake analysis (`ai_structured_case.risk_level`), never on the case. Its readers are:
- the client intake screen ("Risk (AI estimate)" tile);
- the print view;
- the text export.

All three are skipped when `risk_level` is null. There is no lawyer-side reader.

## 2. Fixes

### 2a. Legacy case summaries: a read-time view (no record is rewritten)

`case_service._public_case` (every case leaving the API, and the drafter's case context) now applies `source_currency.case_cpc_view` to the copy it already makes:

| Case | Shown as |
|---|---|
| Province confirmed **Punjab** | unchanged |
| Written after the CPC step: `ai_summary_cpc_checked` set (new conversions **and** retry-analysis now record it), or the summary already carries the batch-6 notice | unchanged, `ai_summary_jurisdiction: {"status": "checked"}` |
| **Legacy**, non-Punjab or unknown | 1. CPC citations cut from `ai_summary`, its Urdu copy and the Urdu actions (same clause rules as batch 5/6).<br>2. **The warning is put FIRST**, so the drafter's 1,500-char cap can never cut it: "Jurisdiction warning: this summary was written before the Code of Civil Procedure jurisdiction check was added. It may rely on the Punjab version of the CPC, which is not verified for Sindh. CPC citations found in it were taken out, but its other wording may still reflect that text. Treat it as unverified." (Urdu too.)<br>3. `ai_summary_jurisdiction: {"status": "legacy_unverified", "cpc_citations_removed": N, "warning": {en, ur}}`. |

A legacy summary is **never presented as fully cleaned**:
- a paraphrase with no CPC citation still gets the warning, with `cpc_citations_removed: 0`;
- the stored document is never written back (verified against a real MongoDB in the integration test, §4).

### 2b. A risk rating made with the CPC in view: "not assessed, needs review"

**When this applies:** in `apply_intake_cpc` (version bumped to **v2**, so stored v1 analyses are re-viewed when read), whenever the CPC step touched a non-Punjab analysis.

**What changes:**
- `risk_level` → **null**. Every existing reader (screen, print, export, older clients) already treats null as "no rating", so nothing shows a rating.
- `risk_level_basis` → **`not_assessed_cpc_jurisdiction`**. The field already existed (it was "model_judgment"); the new value says why.
- `risk_level_withheld` → the model's value, kept for audit and **never displayed**.

**What the client sees:**
- **Screen:** "Risk (AI estimate): **Not assessed — needs review**" (Urdu: "اندازہ نہیں لگایا گیا — جائزہ ضروری"), with a tooltip saying the estimate relied in part on law not verified for the province.
- **Print view:** "Risk Assessment: Not assessed — needs review (…)".
- **Text export:** "RISK LEVEL: NOT ASSESSED — NEEDS REVIEW".

**What is kept:** independent, supported non-CPC content (the actions, claims and citations on the Specific Relief Act, …) is unchanged.

**Unchanged cases:**
- confirmed Punjab;
- non-Punjab analyses with no CPC involvement;
- analyses whose rating was already null for another reason. Their basis is set only when the CPC step touched them.

**Paths covered:**
- **Fresh conversion and retry-analysis:** both run `_run_intake_ai`, so both store the null rating.
- **Reopened intake:** `get_intake`'s read-time view re-applies v2 to a copy, so a stored batch-6 (v1) record shows "not assessed". The stored record is unchanged.

## 3. Files changed (this batch; uncommitted)

| File | Change |
|---|---|
| `backend/app/ai/source_currency.py` | `INTAKE_CPC_VERSION` v2, `RISK_NOT_ASSESSED`, the risk rule in `apply_intake_cpc`; `CASE_CPC_MARK`, `legacy_case_warning`, `case_cpc_view` |
| `backend/app/services/case_service.py` | `_public_case` applies `case_cpc_view` (fail-safe: an error is logged and the case is still served) |
| `backend/app/services/intake_service.py` | Both case-summary writes add `ai_summary_cpc_checked`; `_cpc_version()` |
| `frontend/src/components/client/ModIntake.jsx` | **Client wording:**<br>• the "Not assessed — needs review" risk tile (EN/UR);<br>• the same in the print view and the text export;<br>• the `RISK_NOT_ASSESSED` constant.<br><br>No lawyer-UI change: no lawyer screen renders these fields. |
| `backend/tests/test_case_cpc_view.py` (new) | 25 tests |
| `backend/tests/test_case_cpc_view_integration.py` (new) | 3 integration tests (real `/cases` HTTP and MongoDB) |
| `backend/tests/test_intake_cpc_jurisdiction.py` | one assertion updated: the risk is now withheld when the CPC is involved |
| `frontend/tests/mod_intake_dom.test.mjs`, `frontend/tests/intake_export_safety.test.mjs` | +2 and +1 tests |

## 4. Tests

**Backend unit and regression**
- **How it was run:** 97 files, one at a time, under the temporary-Chroma guard (`AAI_ALLOW_LIVE_CHROMA` not set), with `-m "not integration and not llm and not network"`. Run window: 2026-10-17 00:45–01:17 UTC. The list is every test touching `case_service`, `_public_case`, `intake_service`, `source_currency`, `case_context`, `get_case` or `list_cases`.
- **Results:** **1,334 passed, 2 failed**, 1,106 deselected (integration, run separately below).
- **The 2 failures are pre-existing and unrelated:** `test_lawyer_case_id_contract.py` expects `frontend/src/components/lawyer/CasesPage.jsx` to call `aiResearch(`. Neither the committed (HEAD) version nor the current worktree version contains that call, so the test fails without this batch. `CasesPage.jsx` carries uncommitted edits from earlier lawyer-UI work; it was not touched here.

**New `test_case_cpc_view.py` (25 tests).**
- **Legacy summary through the real `get_case`** (repositories stubbed), for Sindh, KP, Balochistan, federal and unknown:
  - the warning comes first and the CPC citation is cut;
  - the facts are kept;
  - `legacy_unverified` is recorded, with 1 citation removed;
  - the Urdu summary is warned and edited, and the Urdu actions edited;
  - **the stored dict is unchanged**.
- **Other cases:**
  - a paraphrase gets the warning, with 0 citations removed and no "cleaned" claim;
  - Punjab is shown as written;
  - a checked conversion (marker) or a batch-6 notice reads `checked`;
  - the client view and `list_cases` show the same;
  - the **drafter's case context keeps the warning even after the 1,500-char cap**;
  - both case writes (conversion and retry-analysis) record the marker.
- **Risk:**
  - **Non-Punjab (5 provinces) with the CPC involved:** `risk_level` null, `risk_level_withheld` "high", basis `not_assessed_cpc_jurisdiction`; the SRA action and its "supported" claim are kept.
  - **Punjab:** keeps its rating. **Non-Punjab without any CPC:** keeps its rating.
  - **Fresh or retried analysis** (`_run_intake_ai`): Sindh stores null, Punjab stores "high".
  - **Stored batch-6 (v1) record:** re-viewed by `get_intake` with the rating withheld; the stored record is unchanged.
- **Mutation tests (5), each caught:**
  - case view removed;
  - a paraphrase claimed clean;
  - warning moved last;
  - risk rule removed;
  - conversion marker ignored.

**Updated:** in `test_intake_cpc_jurisdiction.py` (38 passed), one assertion now expects the withheld risk.

**MongoDB integration (real replica set)**
- **How it was run:** `AAI_TEST_MONGO_URL=mongodb://localhost:27018/?replicaSet=rs0`, `-m integration`. The conftest only uses throwaway `_test` databases. 19 files, one at a time, 01:18–01:29 UTC.
- **Results:** **316 passed, 0 failed, 0 skipped.**
- **What was covered:**
  - The new `test_case_cpc_view_integration.py` (3): a legacy Sindh case is read over the **real `/cases/{id}` HTTP API** by the lawyer and the client, with the warning first and the CPC removed; **the MongoDB document is unchanged**. `/cases` lists show the same; Punjab and checked cases are served as written.
  - Intake: `test_intake_analysis_retry` 12, `test_intake_routes_http` 23, `test_intake_resumable` 14, crash recovery 6, evidence lifecycle 23, legacy doc upload 5, retention/deletion 33, intake→appointment journey 10.
  - Cases: booking/engagement 23, draft lifecycle 35, case files 8, intake uniqueness 7, integrity 40, retention trigger 20, threads privacy and closure 6, validation 32, status filter 5, walk-in 11.

**Frontend** (each file run directly)
- **Results:** `mod_intake_dom` 67 (+2: a withheld estimate reads "Not assessed — needs review" with no rating badge; an ordinary estimate is still shown), `intake_export_safety` 13 (+1: print view and text export handle the withheld case, using the backend's own key), `intake_grounding_notes` 5, `intake_storage` 10, `case_status_draft` 12. **107 passed, 0 failed.**
- **Isolation:** 0 accesses to the live Chroma path in any run, apart from the guard test's 15 deliberate probes.

## 5. What remains

1. **No lawyer screen shows the case summary today.** The corrected view reaches the API and the drafter. If a lawyer screen later renders `ai_summary`, it should render `ai_summary_jurisdiction.status` beside it; the warning text is already inside the summary.
2. **Raw-repository readers are not covered:**
   - Lawyer matching's query text and document field extraction read the stored `ai_summary` directly, as model or search input. They are not shown as verified law. Matching only ranks lawyers. Extraction reads `description` first and uses `ai_summary` only when the description is empty.
   - Covering them would mean routing both through the view; this was not done, to keep matching behaviour unchanged.
3. **A legacy summary can only be warned about, not corrected:** paraphrased CPC content can't be detected in free text. Proper correction would mean re-running the analysis (retry), which needs a model call.
4. **The risk rating is withheld, not re-estimated.** A rating from the non-CPC law alone would need a model call.
5. **Index relabel (BATCH5 §6) and the live-store snapshot (BATCH3 §1d rev 2)** remain separate approval steps.
