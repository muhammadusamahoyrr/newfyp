# Lawyer Document Analyzer — design reference

The Document Analyzer is a **lawyer-only** tool (decided 2026-10-03, confirmed
2026-10-07). The screens below were first designed for the client side
(28–30 Sept 2026). They are kept here **only as a visual reference** for the
lawyer analyzer. They are not a client feature to restore.

## Files

| File | What it shows |
|---|---|
| `mockups/Analyzer.dc.html` | 7 · Upload → live read → results |
| `mockups/AnalyzerReport.dc.html` | 8 · Full report opened from history |
| `mockups/LawyerReview.dc.html` | 6 · Lawyer review of a client draft (Review Queue) |

## Design → code

| Screen | Route | Component |
|---|---|---|
| Analyzer (upload, history, report) | `/lawyer/documents/analyzer` (lawyer nav "Document Analyzer") | `src/components/lawyer/DocAnalyzerPage.jsx` → `src/components/analyzer/AnalyzerWorkspace.jsx`, `AnalyzerLive.jsx` |
| PII confirmation, processing receipt | same | `analyzer/PiiConfirmation.jsx`, `analyzer/ProcessingReceipt.jsx` |
| Drafting review | same | `analyzer/DraftingReview.jsx` |
| Review Queue | `/lawyer/documents/review-queue` | `src/components/lawyer/ReviewQueuePage.jsx` |

`components/analyzer` belongs to the lawyer side. `tests/role_boundaries.test.mjs`
stops it from importing client code, and stops client code from importing it.

## Control status

| Control in reference design | Status | Note |
|---|---|---|
| History rail (show/hide, options) | connected | lawyer's own analyses |
| Section tabs: Summary, Risks, Obligations, Key clauses, Compliance | connected | analyzer report |
| Aggregated dashboard / executive summary | connected | analyzer report |
| Your side, review depth / scan depth | connected | analysis options |
| Document type, province | connected | analysis options |
| Upload / synthetic document picker | connected | synthetic documents only (`ANALYZER_AI_SYNTHETIC_ONLY`) |
| PII masking confirmation, processing receipt | connected | must stay in the flow |
| Sample review | connected, labelled | marked "Demo version" / fictional text |
| Precedents tab | hidden | no verified precedent source for analyses |
| "Ask about this document" chat | hidden | no backend; would be fake |
| "Fix in a new draft" | hidden | no analyzer → drafting hand-off |
| "Send to lawyer" | hidden | the user already is the lawyer |
| Language switch | hidden | English only |
| Drag & drop multi-document upload | future | one document per analysis |

Rules that do not change with the visuals: lawyer login is required; documents
are synthetic only; AI output never records lawyer approval
(`lawyer_reviewed` / `legal_pack_approved` stay false); and no finding,
precedent or chat answer may be invented.

On 2026-10-07 one visual change was made: the live upload block
(`AnalyzerLive.jsx`, `data-upload-card`) now follows the reference "Upload a
Legal Document" card, with a "Select file" button, a themed side select (it was
unreadable before) and the real limits. The attestation gate, accepted types and
upload call are unchanged. The rest of the screen already followed this layout,
and the differences above are the deliberate ones.
