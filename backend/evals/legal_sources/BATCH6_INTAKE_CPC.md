# Batch 6: Client Legal Intake and the Punjab-only CPC; mixed claims; CPC citation forms (2026-10-16)

**Scope:** code and tests only. **Not done:** commit, external model calls, ingestion, index rebuild or switch, live `backend/chroma_data`, live-store snapshot. The dirty worktree is preserved.

**Status:** passing tests do **not** make any output legally verified. The CPC text on file remains the Punjab version only.

## 1. Intake trace (before this batch)

| Stage | Where | Province | Could CPC become "supported"? |
|---|---|---|---|
| Province chosen | Step 1 (`IntakeStep1.province: Province`, required enum punjab/sindh/kpk/balochistan/federal) | the client's choice | — |
| Analysis run | `intake_service._run_intake_ai(province=step1.province or "federal")`; retry: `case.province or "federal"` | passed in, `province_inferred: False` | — (a missing value defaults to **"federal"**, i.e. *not* Punjab) |
| Retrieval | `build_retriever(case_type, province)`: filter `province IN (asked, "federal")` | as passed | **Yes.** The Punjab CPC is indexed as `federal`, so it is retrieved for every province. |
| Evidence gate | `intake_evidence_gate_node.decide`: `status = supported / partially_supported` from admissible chunks | rejects only chunks of *another* province (CPC passes as "federal") | **Yes.** A CPC-only matter is gated "supported". |
| Judge | `intake_hallucination_node`: per-claim `support` | — | **Yes.** CPC claims "supported" |
| Output contract | `intake_output_guard.enforce` keeps bound legal actions | — | **Yes.** CPC actions kept, CPC citations bound → "Applicable laws" |
| Stored | `intake_repo.save_ai_structured_case` (raw dict); case `ai_summary` = summary | — | **Yes.** Also in the lawyer's case summary and the drafter's case context |
| Client UI | `ModIntake`: summary, Applicable laws, actions, risk, `GROUNDING_NOTE[status]` (no note for "grounded") | — | **Yes.** Shown as applicable law with no caution |
| Reopened | `get_intake` returns the stored analysis unchanged | — | **Yes.** Older analyses stay as stored |

**Can the schema represent a limited result?** Yes, without migration:
- the repository stores `ai_structured_case` as a raw dict, and existing records already carry many fields not in `AIStructuredCase`;
- the response schema returns it as `dict`;
- `grounding_status` is a free string, and an unknown value falls back to the generic "not verified" note.

All new fields are **additive**; no existing record is rewritten.

## 2. Behaviour now

**Intake, outside a confirmed-Punjab matter** (Sindh, KP, Balochistan, federal, unknown):

| Output | Change |
|---|---|
| Applicable laws (`law_citations`, `applicable_laws`) | CPC citations move to `withheld_citations` with `withheld_reason: "cpc_jurisdiction_unverified"`. **Other statutes stay.** |
| Claims (`claim_assessments`) | Any claim with a CPC source, **alone or beside another statute**, or naming a CPC citation: "supported"/"partial" → "unassessed", with the reason ("…; this claim also rests on it" when mixed). Claims resting only on other statutes are unchanged. |
| Recommended actions | A **legal** action resting only on CPC sources is removed (recorded in `output_guard.removed_actions`), and the existing "Ask a qualified Pakistani lawyer which legal provision applies…" step is added. In every other action, only the CPC citation clause is removed (or replaced by "[the relevant CPC provision, not verified for Sindh]"). |
| Summary | Only the CPC citation clause is edited; **the client's facts are unchanged**. |
| Status / risk | With **no law left**, `grounding_status` becomes `cpc_jurisdiction_unverified`, with `grounded: false` and `risk_level: null`. Otherwise the status stands for the law that remains. |
| Notice | `jurisdiction_notice {scope, province, en, ur}`: "Note on the Code of Civil Procedure: our law library holds only the Punjab version of the CPC, so CPC provisions are not shown here as the law that applies in Sindh. A lawyer practising in Sindh should confirm the civil procedure that applies." Urdu text provided. **Asks for the province only when none is recorded.** |
| Urdu rendering (`localized.ur`) | The same actions and citation notes are removed (positions kept aligned), and the same clauses edited; the Urdu lawyer-review step is added. |
| Lawyer case summary (`case.ai_summary`) | summary + notice (fresh conversion **and** retry-analysis), so it reaches the lawyer and the drafter's case context. |
| Reopened intake (`get_intake`) | The same step is applied to a **copy** at read time. Analyses saved before this batch are shown corrected; **stored records are not rewritten**. |
| Client screen, print, text export (`ModIntake`) | The notice is shown (`data-jurisdiction-notice`, in the viewed language) and included in the print view and text export. There is a new status note in English and Urdu. |
| Confirmed Punjab | unchanged |
| Unrelated statutes (PPC s.186, …) | unchanged |

**Chat and Research: mixed claims.** A claim with *any* CPC source is now "unassessed" (batch 5 left a CPC + PPC claim "supported"). Other claims in the same answer are untouched. Claims are not split; the mixed claim alone is downgraded.

**Shared citation forms** (drafter, chat/research tools, intake, CPC rule catalogue):

| Form | Before | Now |
|---|---|---|
| "O VII R 11 CPC", "o vii r 11" | **no parser recognised it** (escaped every check) | Order VII Rule 11. Requires the whole Order…Rule shape, so "go to 7 r 11" is not matched |
| "Order XXXIX Rules 1 **and 2** CPC" | `tool_contract.provision_refs` invented **Section 2 CPC**, and the drafter withheld the whole sentence when s.2 was absent | Rule 1 and Rule 2; no section invented |
| Urdu "آرڈر 7 رول 11 ضابطہ دیوانی" | `provision_refs` invented **Section 11 CPC** | Order 7 Rule 11; no section invented; detected as a CPC citation |
| "Section 42 SRA and Section 9 CPC" (drafter / intake) | the CPC part replaced by a placeholder | " and Section 9 CPC" dropped, and SRA kept |
| "the said section", PPC 186, Supreme Court Rules | not CPC | not CPC (unchanged; tested) |

## 3. Files changed (this batch; all uncommitted)

| File | Change |
|---|---|
| `backend/app/ai/source_currency.py` | **New functions:** `apply_intake_cpc`, `intake_notice`, `intake_placeholder`, `case_summary_with_notice`.<br><br>**Constants:** `INTAKE_CPC_STATUS`, `LAWYER_REVIEW_STEP_UR`.<br><br>**Behaviour changes:**<br>• per-source mixed-claim downgrade in `apply_cpc_jurisdiction`;<br>• the `_ORD` "O … R …" form and the Urdu `_ORD_UR`;<br>• the `_LIST_JOIN` drop. |
| `backend/app/services/intake_service.py` | `apply_intake_cpc` after the output contract in `_run_intake_ai` (fresh + retry). `_case_summary` for both `ai_summary` writes. `_jurisdiction_view` (copy) in `get_intake`. `case = None` initialisation. |
| `backend/app/ai/tool_contract.py` | `_NOT_A_SECTION` gains the Urdu Order/Rule words; new `_LIST_OF_NOT_SECTIONS` ("Rules 1 and 2"). |
| `backend/app/ai/cpc_provisions.py` | `_ORDER_RULE` accepts "O" without a dot, only before an Order…Rule shape. |
| `backend/app/models/intake.py` | Comment only: the new status and fields documented. |
| `frontend/src/components/client/ModIntake.jsx` | **Client UI wording:**<br>• the jurisdiction notice callout (EN/UR);<br>• the notice in the print view and the text export;<br>• `GROUNDING_NOTE` / `GROUNDING_NOTE_UR` gain `cpc_jurisdiction_unverified`.<br><br>No lawyer-UI change. |
| `backend/tests/test_intake_cpc_jurisdiction.py` (new) | 38 tests |
| `backend/tests/test_cpc_jurisdiction.py` | The mixed-claim test now expects the downgrade. New drafter cases: O VII R 11, list-join, Urdu Order/Rule, "Rules 1 and 2" (fake s.2 removed), "the said section". The fixture gains `canonical()` and the SRA. |
| `frontend/tests/mod_intake_dom.test.mjs`, `frontend/tests/intake_grounding_notes.test.mjs` | +2 and +1 tests |

## 4. Tests

**Backend: how it was run**
- 78 files, one at a time, under the temporary-Chroma guard (`AAI_ALLOW_LIVE_CHROMA` not set), with `-m "not integration and not llm and not network"`. Run window: 17:20–17:57 UTC.
- The list covers the batch-5 set plus every test touching `intake_service`, `intake_output_guard`, `source_currency`, `tool_contract`, `cpc_provisions` or the intake finalizer.

**Backend results:**
- **Results:** **1,930 passed, 0 failed**, 18 skipped, 235 deselected.
- **Isolation:** 0 accesses to the live path, apart from the guard test's 15 deliberate probes. Persistent clients were opened only on the **temporary** store, by `test_live_chroma_guard` and the `test_retrieval_scope` fixture.

**Skipped (not passes):**
- 17 analyzer tests need a **replica-set MongoDB** (standalone found).
- **1 `corpus` test needs the live Chroma corpus, NOT run.**

**Deselected (235):** MongoDB `integration` tests. Many intake-service flows backed by a real database are among them, so **the database-backed intake conversion was not exercised**. The new intake behaviour is tested by driving `_run_intake_ai` and `get_intake` with the graph, provenance, localization and repositories stubbed.

**New `test_intake_cpc_jurisdiction.py` (38 tests).**

**Intake output:**
- **Sindh, KP, Balochistan and federal:**
  - CPC is not in Applicable laws, and SRA is kept;
  - the CPC-only action is removed and the lawyer step added;
  - the mixed action is clause-edited, and the SRA action and the general action are kept;
  - the facts in the summary are kept;
  - per-claim, the SRA claim stays "supported" and the CPC and mixed claims are "unassessed";
  - the status stands on the SRA; the notice is in EN and UR.
- **Punjab:** unchanged.
- **Unknown, empty or inferred Punjab:** the notice asks for the province.
- **CPC-only analysis:** `cpc_jurisdiction_unverified`, not grounded, no risk reading.
- **Other cases:**
  - applying the step twice changes nothing;
  - the **Urdu rendering stays aligned**;
  - a mixed claim that does not *name* the CPC is still "unassessed";
  - a **PPC s.186 analysis is untouched**.

**Stored analysis** (`_run_intake_ai`, graph stubbed): limited for all four non-Punjab provinces; Punjab keeps the CPC. The **lawyer `ai_summary` carries the notice**, on both the conversion and retry-analysis writes.

**Reopened intake** (`get_intake`, repositories stubbed): an analysis saved before this batch is shown limited for Sindh, while **the stored record is unchanged**. A Punjab one is shown as stored.

**Citation forms:**
- "O VII R 11", lowercase, Urdu Order/Rule and "Rules 1 and 2" are CPC citations;
- PPC 186, Supreme Court Rules, "go to 7 r 11", "the said section" and a historical "Order VII" are not;
- "Rules 1 and 2" and the Urdu Order/Rule never become a section, while "Section 2 CPC" still does;
- "O VII R 11" parses as Order VII Rule 11.

**Mutation tests (6), each caught:**
- intake step removed;
- a valid source laundering a mixed claim;
- read-time view removed;
- federal treated as Punjab;
- the "Rules 1 and 2" fix reverted;
- the "O"-without-dot fix reverted.

**`test_cpc_jurisdiction.py`: now 56** (was 51):
- the mixed chat claim is downgraded while an unrelated PPC claim in the same answer stays "supported";
- drafter: O VII R 11, "…SRA and Section 9 CPC" → "…SRA", Urdu Order/Rule removed, "Rules 1 and 2" keeps its Punjab sentence (the fake s.2 is removed), "the said section" is never supported.

**Frontend** (each file run directly; see the batch-5 note on `--test-force-exit`):
- **Results:** `mod_intake_dom` 65 (+2: Sindh notice shown in the screen, no CPC law listed; Punjab shows no notice), `intake_grounding_notes` 5 (+1: the new status has EN and UR notes, read from the backend source), `intake_export_safety` 12, `intake_storage` 10, `case_status_draft` 12, `lawyer_draft_assist` 46. **150 passed, 0 failed.**

## 5. Remaining bypasses (not fixed)

1. **Retrieval and the evidence gate still treat the Punjab CPC as federal.**
   - The gate can say "supported" for a non-Punjab matter. The *visible and stored* outputs are corrected after it, but `evidence_gate.status` inside the stored record still reads "supported".
   - The real fix is the data relabel in BATCH5 §6, which needs approval.
2. **`risk_level` stays** when other law remains. It is the model's overall reading, which may have weighed the CPC, and is not recomputed.
3. **Mixed claims are not split.** The whole mixed claim is downgraded; its non-CPC half is not separately marked "supported".
4. **Citation forms still unrecognised** in free text:
   - a CPC section named only by its heading ("the inherent powers of the Court");
   - "the said section" (never shown as supported, but not flagged either);
   - "XXXIX(1)" with no "Order";
   - Urdu "حکم/قاعدہ" written with Roman numerals in Urdu digits.
5. **Older lawyer case summaries:** cases converted before this batch keep their stored `ai_summary` (no rewrite, no read-time step on the case APIs). Only the client intake view is corrected at read time. A compatible fix would be a read-time view on the lawyer case endpoints, or a backfill, which needs approval.
6. **The stored Urdu summary of older intakes** is edited only by clause pattern. Urdu prose that paraphrases a CPC rule without citing it is not detectable.
7. **Document Analyzer and court-Urdu pleading translation** are not audited.

## 6. Separate approval steps (unchanged; NOT executed)

- **Live-store snapshot:** BATCH3 §1d revision 2, with its approval sentence.
- **New-source ingestion:** BATCH5 §6 (CPC relabel to Punjab, then federal / other-province CPC), each scratch-first and separately approved.
