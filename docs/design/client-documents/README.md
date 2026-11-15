# Client Documents — approved design record

The approved design for the client **Documents** module (Templates, AI
drafting, Vault, Request lawyer review). It was recovered on 2026-10-07 from the
design session of 28–30 Sept 2026, which was never committed. Keep this folder
as the reference: when a client Documents screen changes, compare it with the
files here before merging.

The Document Analyzer is **not** part of the client design. It is a lawyer tool
(see `../lawyer-analyzer/`). `/documents/analyzer` on the client side only
redirects to `/documents`.

## Files

| File | What it shows |
|---|---|
| `mockups/Main.dc.html` | 1 · Documents home (template grid, AI drafting entry, "Continue where you left off") |
| `mockups/Plan.dc.html` | 2 · Drafts: start (prompt → draft plan) |
| `mockups/Workspace.dc.html` | 3 · Drafts: generated document with **Fill placeholders** |
| `mockups/Submit.dc.html` | 4 · Readiness and submit for lawyer review |
| `mockups/ChangesRequested.dc.html` | 5 · Client reviews the lawyer's requested changes |
| `mockups/Vault.dc.html` | 9 · Document vault |
| `attorney-ai-ui-redesign.png` | Draft workspace: start screen (history, prompt, tips) |
| `attorney-ai-editor-redesign.png` | Editor with the right-hand completion panel |

The 2026-10-08 drafting update follows the first editor screenshot: Drafts
history on the left, a saved-version PDF in the centre, and a permanently
visible "Complete document" panel on the right. The plan shown immediately
after a prompt uses the same shell with a labelled outline until the PDF is
generated. The previous slide-over details drawer is no longer used.

The mockups are static HTML. Open them directly in a browser; they make no
network calls except to Google Fonts.

## Design → code

| Screen | Route | Component |
|---|---|---|
| Documents home / Templates | `/documents` | `src/components/client/DocumentsHome.jsx` (inside `ModDocuments.jsx`) |
| Drafts: start | `/documents` → Drafts | `src/components/client/documents/DocsDrafts.jsx` (start view, `PromptCard`; the Drafting tips panel was removed on 2026-10-07) |
| Draft plan | same | `DocsDrafts.jsx` → `DraftPlan` |
| Drafts: workspace | same | `DocsDrafts.jsx` (workspace view, `data-document-workspace`) |
| Template editor (pencil) | `/documents` → template | `TemplateEditor.jsx` |
| "Use template" guided flow | `/documents` → template | `ModDocuments.jsx` steps 1–4, design header with a progress rail |
| Send for lawyer review (mockup 4) | from "Send to lawyer" or the guided flow | `ModDocuments.jsx` step 3 (`data-flow-header="send"`) |
| Vault | `/documents` → Vault | `src/components/client/documents/DocsVault.jsx` |
| Request lawyer review | `/client/review-requests/[id]` | review-request components |

Building blocks: `src/components/shared/ui/primitives.jsx` (role-neutral) plus
the client-only palette `MOCKUP_DARK` / `docsTheme()` in
`src/components/client/documents/ui.jsx`.

## Control status (Drafts)

Status values: **connected** means a real backend call; **hidden** means
intentionally not shown because there is no backend for it; **future** means
planned, not built.

| Control in design | Status | Backend / note |
|---|---|---|
| Prompt card "Describe what you need" | connected | `createDraftPlanV2` |
| "View all templates" link | connected | navigation back to the Templates home |
| Draft plan: answer questions, Save answers | connected | `answerDraftPlanV2` |
| "Choices I made — change if wrong" | connected | edits sent as answers via `answerDraftPlanV2`; Confirm hidden until saved |
| Confirm plan / Generate document / Retry | connected | `confirmDraftPlanV2`, `generateDraftPlanV2` (idempotency key, resumable) |
| History list, search, Load more | connected | `myDocumentsV2` (search is client-side over loaded items) |
| Complete document panel, `x/y filled` | connected | `getDocumentWorkspaceV2` structured `fields`; one selected detail with a remaining-details list |
| Progress ring, Empty / All | connected | computed from the real fields; "Empty" keeps the fields that were empty when chosen |
| Save & next / Save all changes | connected | `saveDocumentWorkspaceV2` with revision/version/content-epoch guards; a successful save creates a new revision |
| Calculated (nested) fields | connected, read-only | calculated server-side, cannot be typed |
| Rich-text editing of a lawyer draft | connected | `freeform_html`, sanitised server-side |
| Checks badge (issues, passed/ran, or "—") | connected | from the revision's `complianceSummary` / `verificationView`; a check that did not run is never counted as a failure |
| Ask for changes (AI assist) | connected | `assistDocumentWorkspaceV2` → proposal; applied locally, saved only on Save |
| PDF | connected | `previewRevisionV2` / `downloadDocumentFile` |
| Send to lawyer | connected | opens "Send for lawyer review" directly; disabled when the draft is frozen |
| Send screen: Approve (in place), Download draft, Choose a lawyer, How soon?, note, Send for review, Back to draft | connected | `submitDocumentV2` (version + PDF hash guards, idempotency key), `downloadDocumentFile`, `listEngagements`; back returns to the same document |
| "Frozen for lawyer review" chip | connected | lock state from the document |
| Risk chip ("Medium risk") | hidden | no risk score exists for drafts |
| DOCX export | hidden | no DOCX endpoint |
| Copy | hidden | not in the approved scope |
| "Saved" tab | hidden | no saved-prompts backend |
| "Analyze a document" | hidden | analyzer is lawyer-only |
| Sample draft | hidden | sample content must not look real |
| Prompt card "Add files" / "Use AI to refine" | hidden | looked clickable, had no backend; replaced by a plain hint |
| Click a placeholder inside the PDF | future | the PDF is rendered server-side; fields are edited in the panel |
| Editor one-field-at-a-time "Save & next" | connected | selected field is edited in the side panel; save creates a new revision before moving on |
| "Use template" opening the AI workspace | not planned | "Use template" feeds the guided flow, as in the approved 30 Sept build; the old "Step x of 4" pill and Back/Continue were replaced by the design header |

Tests that hold this design: `tests/docs_drafts_design.test.mjs`,
`tests/docs_send_from_workspace.test.mjs`,
`tests/docs_drafts_recovery.test.mjs`, `tests/documents_home_dom.test.mjs`,
`tests/documents_nav.test.mjs`, `tests/role_boundaries.test.mjs`.

## Control status (Vault)

| Control in design | Status | Backend / note |
|---|---|---|
| Document list, search, sort, Load more | connected | `myDocumentsV2` |
| View / download | connected | `getDocumentV2`, `downloadDocumentFile` |
| Delete → Recently deleted → Restore | connected | deletion preview, delete, restore |
| Send to lawyer (review request) | connected | review-request API, shown only when the feature is on |
| Create Folder | future, shown disabled ("Soon") | no folders backend |
| Upload File | future, shown disabled ("Soon") | no upload backend |
| Storage used | future | shows "—" until uploads exist |
