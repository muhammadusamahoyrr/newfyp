'use client';
/* Documents (client).
 *
 * Three screens: the home (templates, the AI drafting prompt and My
 * Documents), the drafting workspace (DocsDrafts) and the Vault.
 *
 * ONE WORKSPACE FOR EVERY DRAFT (2026-10-19). A template used to open its own
 * four-step guided flow (Draft details, Review, Send to lawyer, Final &
 * export) beside the AI drafting workspace, so the same document had two
 * editors, two review screens and two ways to a lawyer. The flow is gone. A
 * template's details are filled on its own text in the template editor;
 * "Create draft" makes the V2 document and its first revision and opens it
 * in the drafting workspace -- where an AI draft opens, where the Vault and
 * My Documents open a document, and where it is sent to a lawyer.
 */
import React, { useState, useEffect, useRef } from "react";
import { useT, ThemeCtx } from "./theme.js";
import { useToast } from "@/components/shared/Toast.jsx";
import { useCase } from "./CaseContext.jsx";
import { confirmedCases } from "@/lib/caseStatus.js";
import MyDocumentsPanel from "./MyDocumentsPanel.jsx";
import DocumentsHome from "./DocumentsHome.jsx";
import DocsDrafts from "./documents/DocsDrafts.jsx";
import DocsVault from "./documents/DocsVault.jsx";
import { readReviewRequestLink } from "@/lib/reviewRequests.js";
import { docsTheme, DOCS_FONT_CSS } from "./documents/ui.jsx";
import { useIsMobile } from "@/lib/i18n.jsx";
import {
    DOCUMENTS_VIEW_EVENT, peekPendingDocumentsView, takePendingDocumentsView,
    announceDocumentsView, DOCUMENT_OPEN_EVENT, takePendingDocument,
    readOpenDocumentLink, unlinkOpenDocument,
} from "@/lib/documentsNav.js";
import {
    createDocumentV2, generateRevisionV2, listTemplates,
    getDocumentWorkspaceV2, saveDocumentWorkspaceV2,
    idempotencyKey, errorCode,
} from "@/lib/api.js";

/* The client's edited wording (from the template editor, as `[[FIELD]]`
 * tokens) filled with the details. A detail left blank prints as a line to
 * complete by hand, as the builders print it, never as a raw token. */
export function fillWordingTokens(html, fields = {}) {
    const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return String(html || "").replace(/\[\[([A-Z0-9_]+)\]\]/g, (_, name) => {
        const v = fields[name.toLowerCase()];
        return v === undefined || v === null || String(v).trim() === "" ? "______" : esc(v);
    });
}
const apiErrorText = e => e?.message || e?.detail?.message
    || (typeof e?.detail === "string" ? e.detail : "") || "the request failed";

function draftingMode(spec) {
    if (spec?.drafting_mode) return spec.drafting_mode;
    if (spec?.structured_fields?.length) return "dedicated";
    // Compatibility with a backend deployed just before this catalogue field:
    // its old entries were exactly the AI-assisted set used by this screen.
    return "ai";
}

// Structured templates are produced by deterministic tools, not by the generic
// free-text drafter. Keep this small routing map next to that boundary so every
// catalogue card opens the tool that can actually create its document.
const DEDICATED_TOOL_TABS = {
    inheritance_settlement: "calc",
    wasiyyat_nama: "wasiyyat",
    labour_demand: "calculators",
};

function dedicatedToolHref(spec) {
    const tab = DEDICATED_TOOL_TABS[spec?.template_type];
    return tab ? `/tools?tab=${encodeURIComponent(tab)}` : "/tools";
}

const ModDocuments = () => {
    // The Documents screens use the approved mockup's palette in dark mode
    // (see documents/ui.jsx), and hand it down so every child — including
    // shared panels — draws in the same colours.
    const t = docsTheme(useT());
    const toast = useToast();
    const isMobile = useIsMobile();
    const { cases: allCases } = useCase();
    // A draft has not been confirmed by the client, so it must not be offered
    // as something to generate a legal document against.
    const cases = confirmedCases(allCases);

    // What the server can actually render, fetched rather than hardcoded: the
    // catalogue is derived from the builder map itself (template_registry).
    const [templates, setTemplates] = useState(null);   // null = still loading
    const [templateIssue, setTemplateIssue] = useState(null);
    useEffect(() => {
        let live = true;
        listTemplates().then(({ data, error }) => {
            if (!live) return;
            if (error) {
                // No silent fallback to a hardcoded list: an empty picker that
                // says why is recoverable, a wrong one that looks right is not.
                setTemplates([]);
                setTemplateIssue(error.message
                    || "Could not load the list of documents. Reload to try again.");
                return;
            }
            setTemplates(Array.isArray(data) ? data : []);
            setTemplateIssue(null);
        });
        return () => { live = false; };
    }, []);

    /* The sidebar's Documents menu. A request made before this mounted is read
     * on the first render. */
    const [initialView] = useState(peekPendingDocumentsView);
    // Which screen the module shows: the home, or a whole screen of its own.
    const [view, setView] = useState("home");
    // A notification deep link (/documents?tab=review-requests&request=…):
    // read once from the address, it opens the Vault on its Review requests tab.
    const [reviewLink] = useState(() => (typeof window === "undefined"
        ? { open: false, requestId: null, invalid: false }
        : readReviewRequestLink(window.location.search)));
    useEffect(() => { if (reviewLink.open) setView("vault"); }, [reviewLink]);
    const [draftsSeed, setDraftsSeed] = useState(null);
    // The document the address names (`?doc=<id>`), read once: a refresh of an
    // open document reopens it -- see lib/documentsNav.js.
    const [linkedDoc] = useState(() => (typeof window === "undefined" ? null
        : readOpenDocumentLink(window.location.search)));
    const [vaultPreviewId, setVaultPreviewId] = useState(null);
    const [draftsOpen, setDraftsOpen] = useState(null);       // { id, at } — open in the workspace
    useEffect(() => { announceDocumentsView(view === "home" ? "new" : view); }, [view]);

    const openInWorkspace = id => {
        if (!id) return;
        setDraftsOpen({ id, at: Date.now() });
        setView("drafts");
    };
    const showView = next => {
        unlinkOpenDocument();
        setVaultPreviewId(null);
        if (next === "drafts" || next === "vault") {
            if (next === "drafts") setDraftsOpen(null);
            setView(next);
            return;
        }
        if (next === "new" || next === "mine") setView("home");
        if (next === "mine" && typeof document !== "undefined") {
            // After the home renders, bring the user's documents into view.
            setTimeout(() => document.getElementById("my-documents")
                ?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
        }
    };
    useEffect(() => {
        if (initialView) showView(initialView);
        const onView = e => {
            takePendingDocumentsView();
            showView(e?.detail?.view);
        };
        // A notification's request wins; otherwise the address's document
        // (a refresh). A sidebar request made before mount wins over both.
        const asked = takePendingDocument();
        if (asked) openInWorkspace(asked);
        else if (!initialView && linkedDoc) {
            if (linkedDoc.preview) { setVaultPreviewId(linkedDoc.id); setView("vault"); }
            else openInWorkspace(linkedDoc.id);
        }
        const onOpen = e => { takePendingDocument(); openInWorkspace(e?.detail?.id); };
        window.addEventListener(DOCUMENTS_VIEW_EVENT, onView);
        window.addEventListener(DOCUMENT_OPEN_EVENT, onOpen);
        return () => {
            window.removeEventListener(DOCUMENTS_VIEW_EVENT, onView);
            window.removeEventListener(DOCUMENT_OPEN_EVENT, onOpen);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /* Save the client's edited wording as the document's next revision: the
     * "edited document" revision the workspace makes when its text is edited. */
    const applyEditedWording = async (documentId, html, fields) => {
        const ws = await getDocumentWorkspaceV2(documentId);
        if (ws?.error || !ws?.data) return { ok: false, message: apiErrorText(ws?.error) };
        const w = ws.data;
        const saved = await saveDocumentWorkspaceV2(documentId, {
            bodyHtml: fillWordingTokens(html, fields), title: w.title,
            expectedRevisionId: w.base_revision_id, expectedVersion: w.base_version,
            expectedContentEpoch: w.content_epoch,
        }, idempotencyKey());
        if (saved?.error || !saved?.data) return { ok: false, message: apiErrorText(saved?.error) };
        return { ok: true, rev: saved.data };
    };

    // One create key per template until a draft of it is made, so a retry
    // after a failed generate reuses the SAME document instead of a new one.
    const templateCreateRef = useRef(null);

    /* A template becomes a draft in the drafting workspace.
     *
     * The template editor collects the details on the template's own text;
     * this makes the V2 document and its first revision from them and opens
     * it in the workspace. Wording the client changed in the editor becomes
     * the next revision, filled with the same details. Resolves to
     * { ok, message } so the editor can stay open, saying why, on a failure. */
    const createFromTemplate = async (spec, prefill = null, edited = null, caseId = null) => {
        if (!spec) return { ok: false, message: "Select a template first." };
        if (draftingMode(spec) === "dedicated") return { ok: false, message: "This document is built in its calculator." };
        takePendingDocumentsView();
        const own = new Set((spec.fields || []).filter(f => !(spec.structured_fields || []).includes(f)));
        const fields = Object.fromEntries(Object.entries(prefill || {})
            .map(([k, v]) => [k, typeof v === "string" ? v.trim() : v])
            .filter(([k, v]) => own.has(k) && v));
        if (!Object.keys(fields).length) return { ok: false, message: "Fill at least one detail first." };

        const intent = JSON.stringify([spec.template_type, caseId || null]);
        if (templateCreateRef.current?.intent !== intent) templateCreateRef.current = { intent, key: idempotencyKey() };
        const created = await createDocumentV2({
            templateType: spec.template_type, title: `${spec.label || "Document"} draft`, caseId: caseId || null,
        }, templateCreateRef.current.key);
        if (created.error) {
            if (created.status === 404 && errorCode(created.error) === "feature_disabled") {
                return { ok: false, message: "Drafting from a template needs Documents V2, which is switched off." };
            }
            return { ok: false, message: apiErrorText(created.error) };
        }
        const documentId = created.data.id;
        // A new key per attempt: a generate that failed is final under its key.
        const rev = await generateRevisionV2(documentId, { fields, templateType: spec.template_type }, idempotencyKey());
        if (rev.error) return { ok: false, message: apiErrorText(rev.error) };
        templateCreateRef.current = null;

        let warning = null;
        if (edited?.html) {
            const applied = await applyEditedWording(documentId, edited.html, fields);
            if (!applied.ok) warning = `⚠️ The draft uses the template's own wording: your edited wording could not be applied (${applied.message}). You can edit the text in the workspace.`;
        }
        openInWorkspace(documentId);
        if (warning) toast.show(warning, "warn", 9000);
        return { ok: true };
    };

    const backHome = () => { unlinkOpenDocument(); setView("home"); };
    const frame = content => (
        <ThemeCtx.Provider value={t}>
            <div data-docs-font style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", background: t.bg, color: t.text }}>
                <style>{DOCS_FONT_CSS}</style>
                {content}
            </div>
        </ThemeCtx.Provider>
    );
    if (view === "drafts") {
        return frame(<DocsDrafts seed={draftsSeed} templates={templates} cases={cases} onBack={backHome}
            onOpenView={v => setView(v)} openDocument={draftsOpen} />);
    }
    if (view === "vault") {
        // Open from the Vault edits in the drafting workspace -- one editor for
        // a document, wherever it is opened from.
        return frame(<DocsVault onBack={backHome} reviewLink={reviewLink} previewId={vaultPreviewId}
            onEdit={openInWorkspace} />);
    }

    return frame(
        <div data-lenis-prevent style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: isMobile ? "60px 14px 20px" : "30px 40px 32px", boxSizing: "border-box" }}>
            <div style={{ paddingBottom: 8 }} className="aFadeUp">
                <DocumentsHome
                    templates={templates}
                    templateIssue={templateIssue}
                    cases={cases}
                    draftingMode={draftingMode}
                    dedicatedToolHref={dedicatedToolHref}
                    onUse={createFromTemplate}
                    onPlan={seed => { setDraftsSeed({ ...seed, at: Date.now() }); setView("drafts"); }}
                    onOpenView={v => setView(v)}
                    continueSlot={(
                        // EVERY DOCUMENT THIS CLIENT OWNS, on the home. Opening
                        // one goes to the workspace; previewing one, to the
                        // Vault's preview of it.
                        <div id="my-documents" style={{ scrollMarginTop: 12 }}>
                            <MyDocumentsPanel
                                t={t}
                                onOpen={restored => openInWorkspace(restored?.docId)}
                                onPreview={async id => {
                                    setVaultPreviewId(id);
                                    setView("vault");
                                    return { error: null };
                                }} />
                        </div>
                    )} />
            </div>
        </div>
    );
};

export default ModDocuments;
