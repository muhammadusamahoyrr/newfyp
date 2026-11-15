# Batch 5: the Punjab-only CPC, on every surface, by province (2026-10-16)

**Scope:** code and tests only. **Not done:** commit, ingestion, live `backend/chroma_data`, model or provider calls, snapshot.

**Status:** passing tests do **not** make any output "legally verified". The CPC text on file is still only Punjab's, and the gate only stops it being presented as the law elsewhere.

## 1. Audit: how the province travels, before this batch

| Surface | Province source | Reaches the CPC check as | Gap found (before) |
|---|---|---|---|
| **Draft Assistant** `/ai/draft/stream` | Case record (`build_case_context`) or the lawyer's explicit choice (`draft_jurisdiction.is_valid_choice`/`resolve`). Empty / "unknown" = neutral. | `eff_province` → `draft_guard.check(province=…)` | **Batch 4:** outside Punjab the CPC was "Not checked" but **insertable** ("Insert at cursor", primary), with no marker in the document. Unknown/neutral drafts were treated like other provinces (good), but still insertable. |
| **Lawyer Research** `/ai/research` | Case record when case-bound, else `body.province`. Triage `jurisdiction.resolve`: a stated value wins; otherwise the model may **infer** a province from the question (`jurisdiction_basis = inferred_from_query`). | `state.province` + `jurisdiction_basis` → hallucination node → finalizer | **Batch 4** downgraded CPC claims only for a *known* non-Punjab province. So: (a) an **unknown** province kept "supported"; (b) a Punjab **inferred** from the question text counted as Punjab; (c) the downgrade ran before `grounding_veto`, so a CPC-only answer was marked ungrounded and regenerated, while the visible answer never said *why*. |
| **Client Chat** (WebSocket) | `data.province` or session province (`jurisdiction.resolve`), usually `null` → unknown. Triage may infer. | same as research | Same (a)–(c). Most client turns are "unknown", so the batch-4 downgrade almost never applied. |
| Chat / research **cache hit** | Key = query + case type + province + language + variant. A hit skips hallucination_node and returns the **stored** claims. | `cache_lookup_node` → finalizer | Entries written before the downgrade still carry "supported" CPC claims, and nothing re-checked them on a hit. |
| Chat / research **follow-up** ("make it short") | Re-answers through the same graph. | finalizer | Same as fresh answers. |
| Retrieval (all surfaces) | The province filter is `province IN (asked, "federal")`. | — | The Punjab CPC is labelled `province: federal` in the index, so it is returned for **every** province. Retrieval is unchanged here; this batch handles it at the output (index relabelling needs separate approval). |
| Intake, Document Analyzer, Urdu-pleading translation | — | — | **Not audited / not changed in this batch** (see §5). |

"Supported" displays: the drafter panel's `supported` list (`CheckScope`), the chat (`ModChatbot`) and research (`AILegalPage`) claim badges, and citation `currency`. There is no "verified" citation label anywhere (`frontend/src/lib/trust.js`).

## 2. Behaviour now, by surface and province

A province counts as **confirmed Punjab** only when it is `punjab` **and** came from the user's selection or the case record. Inferred from the question is not confirmation; unknown is unknown.

| Surface | Confirmed Punjab | Sindh / KP / Balochistan / federal | Unknown, neutral, or inferred Punjab |
|---|---|---|---|
| **Draft Assistant: insertable text** | unchanged | **Only the CPC authority clause** leaves the text (see the clause table below). Facts and everything else in the sentence stay. | same, with "your province" |
| Draft Assistant: Withheld list | — | each removed citation, with "the CPC text on file is the Punjab version and this matter is not confirmed as Punjab (Sindh)…" | same |
| Draft Assistant: placeholder version | none | a **separate proposal**, labelled by the server "With a [Verify ...] placeholder for the CPC provision" (or combined with invented-fact placeholders), with **"[Verify the applicable CPC provision for Sindh]"** in place of each citation. It is **re-run through the same `draft_guard.check`** before it is offered. | "…for your province]" |
| Draft Assistant: lawyer's own text | unchanged | **never rewritten** (a sentence found in the lawyer's document/selection); listed "CPC citation in your own text, not changed … not verified for Sindh" | same |
| Draft Assistant: historical sentence (no reliance) | unchanged | kept; listed "CPC reference in a historical sentence, kept … not checked" | same |
| Draft Assistant: Supported | CPC may be supported | **never** a CPC entry (main or alternative) | never |
| Chat / Research: claim badge | unchanged | a claim resting **only** on the CPC: "supported/partial" → **"Not assessed"**, with the reason "the CPC text on file is the Punjab version; not verified for Sindh". Mixed CPC + other-statute claims are not downgraded. | "…not verified for your province (not known)" |
| Chat / Research: citation currency | unchanged | CPC citations → `currency: unknown` ("Current status not verified") + `jurisdiction_note` | same |
| Chat / Research: answer text | unchanged | **one notice** when the answer cites the CPC: "Note on the Code of Civil Procedure: the CPC text this answer was checked against is the Punjab version. The CPC provisions above are not verified for Sindh; check them against the Sindh text before relying on them." Urdu answers get it in Urdu. | the notice also **asks for the province**: "…tell me your province, or check the CPC as it applies there…". It is not a blocking clarification: an answer that does not cite the CPC gets no notice and no question. |
| Chat / Research: grounding | unchanged | **unchanged**: the downgrade now runs in `finalizer_node` *after* `grounding_veto`, so jurisdiction doubt no longer forces a regenerate | same |
| Cache hits, follow-ups | unchanged | the finalizer applies the same step on hits (correcting entries written before this rule) and on follow-ups. The notice is never added twice; the cache write stores the corrected answer. | same |
| Unrelated statutes (PPC s.186, s.420, …) | unchanged | unchanged | unchanged |

**Drafter clause handling** (only the citation is touched):

| AI sentence | Main proposal | Placeholder version |
|---|---|---|
| "…liable to be rejected **under Order VII Rule 11 CPC** as it discloses no cause of action." | "…liable to be rejected as it discloses no cause of action." | "…rejected under [Verify the applicable CPC provision for Sindh] as it…" |
| "…sought **under Section 151 read with Order XXXIX Rules 1 and 2 CPC** pending the suit." | "…sought pending the suit." | placeholder in place of the chain |
| "…properly valued **(Section 7 CPC)** and…" | "…properly valued and…" | "…valued ([Verify …]) and…" |
| "**Section 9 CPC** gives civil courts jurisdiction…" (citation is the subject; removing it would break the sentence) | "[Verify the applicable CPC provision for Sindh] gives civil courts jurisdiction…" | same |
| "یہ عدالت **ضابطہ دیوانی کی دفعہ 20 کے تحت** مجاز ہے۔" / "Yeh adalat **CPC ki dafa 20 ke tehat** mujaz hai." | "یہ عدالت مجاز ہے۔" / "Yeh adalat mujaz hai." | placeholder |

## 3. Files changed (this batch; all uncommitted)

| File | Change |
|---|---|
| `backend/app/ai/source_currency.py` | **Scope and placeholder:** `cpc_scope` (confirmed Punjab / other / unknown, where inferred counts as unknown), `cpc_placeholder`.<br><br>**Finding citations:** `cpc_citations` covers Section…CPC, CPC Section…, Order…Rule…, "read with" chains, brackets, Urdu script, the normalised "CPC کی Sec. 9", and Roman Urdu "CPC ki dafa 9".<br><br>**Drafter edits:**<br>• `cpc_clause_edits` (main / alt / withheld / notes);<br>• `apply_edits`, which tidies only at the edited boundaries.<br><br>**Chat and research:** `apply_cpc_jurisdiction` (claims, citations, notice), `cpc_notice` (English / Urdu).<br><br>**Pattern fix:** the "ke tehat" pattern is fixed (it did not match "tehat"), in both the CPC and the Constitution gate. |
| `backend/app/ai/draft_guard.py` | `check(..., own_text=)`. Applies the CPC clause edits after other withholding. Lists removed citations under Withheld. Drops CPC "not checked" entries that are no longer in the text. Adds the own-text and history notes. The placeholder alternative now covers invented facts and/or CPC, carries a `label`, and is re-checked in full. |
| `backend/app/api/v1/routes/ai.py` | The drafter passes the lawyer's document + selection as `own_text`. |
| `backend/app/ai/nodes/finalizer_node.py` | Applies `apply_cpc_jurisdiction` to fresh and cached answers, before the cache write. |
| `backend/app/ai/nodes/hallucination_node.py` | The batch-4 CPC downgrade is removed from here (moved to the finalizer, after the grounding verdict). |
| `frontend/src/components/lawyer/DocAutomationPage.jsx` | **One line (lawyer UI):** the placeholder card's label comes from the server (`alt.label`), falling back to the old "facts you did not give" wording. Without this, a CPC placeholder version would be mislabelled. |
| `backend/tests/test_cpc_jurisdiction.py` (new) | 51 tests (§4) |
| `backend/tests/test_constitution_gate.py`, `test_draft_guard_v2.py`, `test_source_currency.py` | Assertions moved to the new policy (the batch-4 "insertable" pin is replaced). The grounding node is now pinned to leave jurisdiction to the finalizer. |
| `frontend/tests/lawyer_draft_assist.test.mjs` | +2 UI tests: Sindh CPC card text, label and Insert result; fallback label. |

## 4. Tests

**Backend: how it was run**
- 51 files, one at a time, under the temporary-Chroma guard (`AAI_ALLOW_LIVE_CHROMA` not set), with `-m "not integration and not llm and not network"`. Run window: 16:29–16:58 UTC.
- The list is every test module touching `finalizer_node`, `cache_node`, `hallucination_node`, `source_currency`, `draft_guard`, the draft-stream route, `index_health` or the graph.

**Backend results:**
- **Results:** **1,449 passed, 0 failed**, 18 skipped, 25 deselected.
- **Rerun after a change:** the "Civil Procedure Code" form was added afterwards, and the 8 directly affected files were rerun (17:00 UTC): `cpc_jurisdiction` 51, `source_currency` 29, `constitution_gate` 50, `draft_guard_v2` 128, `draft_guard` 38, `draft_assist_modes` 28, `visible_authority` 48, `template_citation_binding` 410 + 92 skipped + 2 xfailed. **All passed.**

**Skipped (not passes):**
- 17 analyzer tests need a MongoDB replica set and found a standalone server (environment).
- **1 `corpus` test needs the real Chroma corpus, NOT run** (`test_retrieval_scope.py:65`). No test was run against live Chroma.
- 92 template variants print no provision (by design, in the rerun).

**Deselected:** 25 `integration` (MongoDB) tests.

**Isolation:**
- 0 accesses to the live path, apart from the guard test's own 15 deliberate probes.
- Persistent clients were opened only by `test_live_chroma_guard` and `test_retrieval_scope` (its fixture), both on the **temporary** store.
- No test opened the live store at import.

**New `test_cpc_jurisdiction.py` (51 tests).**

**Drafter**, through the real `/ai/draft/stream` route with a stubbed model:
- **Punjab:** unchanged.
- **Sindh, KP, Balochistan, federal, "" and "unknown":**
  - only the clause is removed;
  - the Karachi fact is kept;
  - Withheld names the province;
  - the placeholder version carries the exact text and label, has nothing left to remove (re-checked), and has no CPC entry in Supported;
  - verification and audit read the checked text.
- **Citation forms:** Order/Rule, O.7 r.11, the "read with" chain, brackets, a subject-position citation (placeholder), and "Civil Procedure Code".
- **Urdu and Roman Urdu**, including "Ke Tahat".
- **Other cases:**
  - a historical sentence is kept as not checked;
  - the **lawyer's own CPC sentence is unchanged** while the AI's new one is removed;
  - **PPC s.186 and s.420 are untouched**;
  - an invented fact plus a CPC citation produce one combined, re-checked alternative.

**Chat and research**, through the real `finalizer_node`:
- **Confirmed Punjab** (selected or case record) is unchanged on both surfaces.
- **Sindh, KP, Balochistan, federal, unknown, None and inferred Punjab**, on both surfaces:
  - "Not assessed" with the reason;
  - exactly one notice, naming the province or asking for it;
  - CPC citations shown as `currency: unknown`.
- **Other cases:**
  - an Urdu answer gets the Urdu notice;
  - a PPC-only answer is untouched;
  - a mixed CPC + PPC claim is not downgraded, but the notice is shown;
  - an Order/Rule answer is noted;
  - a **cache hit written before this rule** is corrected, and its notice is never stacked;
  - a **follow-up** is corrected;
  - the **stored cache entry** carries the correction.

**Mutation tests (7), each caught:**
- inferred Punjab treated as confirmed;
- unknown treated as Punjab;
- drafter clause edits removed;
- "under …" replaced instead of dropped;
- the lawyer's own text ignored;
- the chat/research correction removed;
- a CPC pattern that also matches the PPC.

Plus, in `test_constitution_gate.py`: the grounding node leaves jurisdiction to the finalizer (the verdict stays "supported", grounded).

**Frontend, `lawyer_draft_assist.test.mjs`:**
- **Results:** 46 passed, including 2 new tests. A Sindh CPC card shows only the clause-free text and the Withheld reason, with no "found … consistent" wording. The placeholder card carries the server's CPC label, and **Insert puts in "[Verify the applicable CPC provision for Sindh]"**, never "Section 20…". A placeholder version with no server label keeps the old wording.
- **Other affected files** (`documents_v2` 101, `draft_case_binding` 12, `draft_citation_check` 11, `lawyer_dead_controls` 12, `lawyer_download_errors` 3, `lawyer_requirements_checklist` 3, `one_click_idempotency` 14): **202 passed, 0 failed** across the 8 files.
- **Harness quirk (pre-existing, not fixed):** with the `npm test` flags (`--test --test-force-exit`), `lawyer_draft_assist.test.mjs` reports only its first 4 synchronous tests; the UI tests after its top-level `await import(...)` are not counted. Each file was therefore run directly (`node --import ./tests/support/register.mjs tests/<file>.test.mjs`), which runs all of them.

## 5. Remaining ways an unverified CPC claim could still appear as Supported or insertable

1. **Citation forms the detector does not know:**
   - "O VII R 11" without dots;
   - "XXXIX(1)" with no "Order";
   - a CPC section named only by its heading ("the inherent powers of the Court");
   - a cross-reference such as "the said section";
   - Urdu Order/Rule forms.

   In the drafter, those stay insertable. They are still never "Supported", because `gate_supported` moves any CPC-labelled entry, but a citation the authority parser also misses would just be absent from every list.
2. **Lawyer-authored text is deliberately untouched.** If the lawyer pastes Punjab CPC wording, it stays. It is listed as not verified, not supported.
3. **Intake (client case analysis) is not covered.** `intake_evidence_gate` can still report a CPC-grounded analysis as `supported` for a non-Punjab client. Not audited this batch; it needs its own change.
4. **Document Analyzer and court-Urdu pleading translation** are not covered (they translate or review existing text; not audited).
5. **Retrieval still returns the Punjab CPC for every province** (indexed as `federal`). The fix is a source relabel (`province: punjab`) plus a federal/other-province CPC ingest: data changes needing approval (§6).
6. **Pre-existing parser quirk (not fixed, reported):** the authority check reads "Rules 1 and 2 CPC" as "Section 2 CPC". In a library without s.2, that withholds the whole sentence; the real CPC has s.2.
7. **The badge reason is shown only in Research.**
   - Lawyer Research (`AILegalPage.jsx:1732`) shows `support_reason` beside "Not assessed".
   - Client chat (`ModChatbot`) shows only "Not assessed", without the reason. There, the jurisdiction limitation reaches the client through the **notice in the answer text**.
   - No client-UI change was made.

## 6. Proposal (NOT executed): snapshot, then data changes

1. **Snapshot first:** BATCH3 §1d **revision 2** (unchanged), with its own approval sentence.
2. **Then, each as a separately approved, scratch-first change:**
   - **(a) Relabel**, in a *new* collection version, the indexed CPC chunks from `province: federal` to `province: punjab`, with `source: punjabcode` and sha256 `528384…`. The live constant is switched only after a gate run, as `ident_v2` was.
   - **(b) Source the federal CPC** (Pakistan Code consolidation; Gazette authority recorded separately), plus any Sindh/KP/Balochistan CPC amendments as their own registry records. Licence, status and commencement must be verified first.
   - **(c) Build and evaluate in a scratch index**, with lawyer-reviewed labels for "same wording in province X" before any jurisdiction gate is relaxed.
   - **(d) Relax the gate per jurisdiction** only where a verified text for that jurisdiction exists in the corpus.
3. **Not done:** none of these were done or started.
