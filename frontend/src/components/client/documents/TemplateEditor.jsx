'use client';
/* Customize a template — a full-screen rich-text editor.
 *
 * WHAT IT EDITS. The template's own wording, as its PDF builder writes it
 * (`GET /documents/templates/{type}/text`, 2026-10-19), every detail shown as
 * a [PLACEHOLDER]. It used to open on an outline (title + field names) because
 * the browser had no text, which made every template look empty. The outline
 * is now only the fallback for a PDF-only template, and says so.
 *
 * WHAT IS REAL.
 *   - Formatting (contentEditable + the browser's editing commands).
 *   - Download as Word (.doc, HTML Word opens) and as PDF (the browser's print
 *     dialog, "Save as PDF") — both built from the page, in the browser.
 *   - Save: to THIS BROWSER only (localStorage), and labelled that way. There
 *     is no server store for a client's own template text yet.
 *   - Fill details: values replace their placeholders in the page, and are
 *     carried into the guided template flow by "Use template".
 *
 * Exported HTML is the user's own text, but it is still cleaned (no scripts,
 * no event-handler attributes, no javascript: links) before it leaves the
 * editor, because paste can bring markup from anywhere. */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useT, ThemeCtx } from "../theme.js";
import { useToast } from "@/components/shared/Toast.jsx";
import { humanise } from "@/lib/fieldReview.js";
import { templateText, extractDocumentFields } from "@/lib/api.js";
import { PAPER_FONT, ModalPortal, BACKDROP } from "./ui.jsx";

const STORE_PREFIX = "attorney.templateCopy.";

/* The editor's own light-teal look, in both app themes: a writing surface
 * reads better light, and the dark workspace around it made the whole window
 * feel heavy. Handed down through ThemeCtx so the shared buttons and inputs
 * inside the editor pick it up too. */
export const EDITOR_LIGHT = {
    mode: "light",
    bg: "#eaf7f5", surface: "#f6fcfb", card: "#e3f4f1", cardHi: "#d6efeb",
    border: "#bfe3dd", borderHi: "#9fd3cb", ghostBorder: "#9fd3cb", inputBorder: "#b5ddd6",
    inputBg: "#ffffff", primary: "#139486", primaryGlow: "rgba(19,148,134,0.18)", primaryGlow2: "#d2f0eb",
    text: "#12343a", textDim: "#27525a", textMuted: "#5b7d83", textFaint: "#86a4a9", label: "#0f7f73",
    success: "#1f9d63", warn: "#b07800", danger: "#c8354c", info: "#1d6fa8",
    chipBg: "#e3f4f1", chipBorder: "#bfe3dd", shadowCard: "none",
};

const FONTS = ["Arial", "Times New Roman", "Georgia", "Calibri", "Garamond", "Courier New"];
const SIZES = [10, 11, 12, 14, 16, 18, 20, 24];

const escapeHtml = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function templateFields(spec) {
    return (spec?.fields || []).filter(f => !(spec.structured_fields || []).includes(f));
}

/* The starting page: an outline, never invented clauses. */
export function outlineHtml(spec) {
    const title = escapeHtml((spec?.label || "Document").toUpperCase());
    const rows = templateFields(spec).map(f => {
        const label = humanise(f);
        return `<p><strong>${escapeHtml(label)}:</strong> <span data-field="${escapeHtml(f)}">[${escapeHtml(label.toUpperCase())}]</span></p>`;
    }).join("");
    return `<h1 style="text-align:center">${title}</h1>`
        + (spec?.description ? `<p><em>${escapeHtml(spec.description)}</em></p>` : "")
        + rows
        + "<p><br></p><p>Write the body of your document here…</p>";
}

/* The builder's text, fetched once per template per page load. Resolves to
 * `{ html, failed }`: html null with failed false is a PDF-only template;
 * failed is a request that did not succeed, which must NEVER be presented as
 * "this template has no text" (a stale server showed exactly that). */
const textCache = new Map();
export function resetTemplateTextCache() { textCache.clear(); }   // for tests
export function loadTemplateText(type) {
    if (!type) return Promise.resolve({ html: null, failed: false });
    if (!textCache.has(type)) {
        textCache.set(type, templateText(type).then(res => {
            // Only a real answer is remembered; a failed request is retried
            // the next time this template is opened.
            if (!res || res.error || !res.data) { textCache.delete(type); return { html: null, failed: true }; }
            return { html: res.data.text_html || null, failed: false };
        }).catch(() => { textCache.delete(type); return { html: null, failed: true }; }));
    }
    return textCache.get(type);
}

/* The server's text made ready for the page: cleaned, and each
 * `[[FIELD_NAME]]` turned into the same placeholder the outline uses, so the
 * live fill, the click-to-field and the highlight all work on it. */
export function realTextHtml(html) {
    return cleanHtml(html).replace(/\[\[([A-Z0-9_]+)\]\]/g, (_, name) => {
        const f = name.toLowerCase();
        return `<span data-field="${escapeHtml(f)}">[${escapeHtml(humanise(f).toUpperCase())}]</span>`;
    });
}

/* The page handed on as the client's wording: each detail's placeholder (or
 * the value typed into it) goes back to `[[FIELD_NAME]]`, so the reviewed
 * values fill it later and a value is never frozen into the wording. */
export function tokenHtml(html) {
    if (typeof DOMParser === "undefined") return cleanHtml(html);
    const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    doc.querySelectorAll("[data-field]").forEach(el => {
        const name = (el.getAttribute("data-field") || "").replace(/[^a-z0-9_]/gi, "").toUpperCase();
        el.replaceWith(doc.createTextNode(name ? `[[${name}]]` : el.textContent));
    });
    return cleanHtml(doc.body.firstChild ? doc.body.firstChild.innerHTML : "");
}

/* Remove anything executable before the HTML leaves the editor. */
export function cleanHtml(html) {
    // No parser: never pass markup through unchecked — keep the text only.
    if (typeof DOMParser === "undefined") {
        return escapeHtml(String(html || "").replace(/<(script|style)[\s\S]*?<\/\1>/gi, "").replace(/<[^>]*>/g, ""));
    }
    const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
    doc.querySelectorAll("script, style, iframe, frame, object, embed, link, meta, base, form, input, button, textarea, select").forEach(n => n.remove());
    doc.querySelectorAll("*").forEach(el => {
        for (const attr of [...el.attributes]) {
            const name = attr.name.toLowerCase();
            const value = attr.value.replace(/[\u0000- ]+/g, "").toLowerCase();
            if (name.startsWith("on") || name === "srcdoc" || name === "formaction") { el.removeAttribute(attr.name); continue; }
            if (["href", "src", "xlink:href", "action"].includes(name)
                && (/^(javascript|vbscript):/.test(value) || (/^data:/.test(value) && !/^data:image\//.test(value)))) {
                el.removeAttribute(attr.name);
            }
        }
    });
    return doc.body.firstChild ? doc.body.firstChild.innerHTML : "";
}

export function countWords(text) {
    const trimmed = (text || "").trim();
    return { chars: (text || "").length, words: trimmed ? trimmed.split(/\s+/).length : 0 };
}

function readSaved(type) {
    try {
        const raw = window.localStorage.getItem(STORE_PREFIX + type);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function exportDoc(title, html) {
    return `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>`
        + `<style>body{font-family:'Times New Roman',serif;font-size:12pt;line-height:1.6}h1{font-size:16pt}</style></head><body>${cleanHtml(html)}</body></html>`;
}

const I = {
    undo: <path d="M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3" />,
    redo: <path d="M15 14l5-5-5-5M20 9H9a5 5 0 0 0 0 10h3" />,
    ul: <><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1" /><circle cx="4.5" cy="12" r="1" /><circle cx="4.5" cy="18" r="1" /></>,
    ol: <path d="M10 6h10M10 12h10M10 18h10M4 5h1v4M4 9h2M4 15h2l-2 3h2" />,
    link: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
    hr: <path d="M4 12h16" />,
    doc: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
    panel: <><rect x="3" y="4" width="18" height="16" rx="2.5" /><path d="M15 4v16" /></>,
    close: <path d="M6 6l12 12M18 6L6 18" />,
    save: <><path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z" /><path d="M8 3v5h7V3M8 21v-7h8v7" /></>,
    download: <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />,
    chevron: <path d="M6 9l6 6 6-6" />,
    arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
    file: <><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></>,
};
const Svg = ({ d, s = 17, w = 2 }) => <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>;

const BRAND = "linear-gradient(135deg,#0E8A5F,#0B7A8C)";
const INK = "#12343A", MUTED = "#4F6E73", LINE = "#E1ECE9", SOFT_LINE = "#CFE3DF", ACCENT = "#0B6E62";

/* Page-only marks for the fill-in fields (2026-10-19). Rules, not inline
 * styles, so nothing of them reaches a download: amber = still needs a value,
 * green = filled, ring = the field being typed in the panel. */
const EDITOR_CSS = `
[data-template-editor] .doc-editor-page [data-field]{padding:1px 6px;border-radius:5px;background:#FFF4D6;color:#7A5200;outline:1px dashed #D9A93A;outline-offset:-1px;font-weight:600;cursor:pointer}
[data-template-editor] .doc-editor-page [data-field][data-filled]{background:#E3F4EC;color:#0E5E44;outline:0}
[data-template-editor] .doc-editor-page [data-field][data-active]{background:#FFFFFF;color:${ACCENT};outline:1.5px solid #0E8A5F;box-shadow:0 0 0 3px rgba(14,138,95,.15)}
[data-template-editor] .te-tool{min-width:34px;height:34px;padding:0 8px;border:0;border-radius:8px;background:none;color:#27525A;display:inline-flex;align-items:center;justify-content:center;font:inherit;font-size:14px;cursor:pointer}
[data-template-editor] .te-tool:hover{background:#EEF6F4}
[data-template-editor] .te-tool[aria-pressed="true"]{background:#E3F2EE;color:${ACCENT}}
[data-template-editor] .te-tool:disabled{cursor:not-allowed;opacity:.5}
[data-template-editor] .te-sel{height:34px;border-radius:8px;border:1px solid #DCE8E5;background:#FFFFFF;color:${INK};padding:0 8px;font:inherit;font-size:13.5px;cursor:pointer}
[data-template-editor] .te-btn{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border-radius:10px;border:1px solid ${SOFT_LINE};background:#FFFFFF;color:${INK};font:inherit;font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap}
[data-template-editor] .te-btn:hover{border-color:#9FD3CB}
[data-template-editor] .te-btn:disabled{opacity:.6;cursor:default}
[data-template-editor] .te-btn.primary{border:0;background:${BRAND};color:#FFFFFF;font-weight:700;padding:0 20px;box-shadow:0 10px 22px -12px rgba(11,122,140,.8)}
[data-template-editor] .te-btn.danger{color:#B3261E;border-color:#E8B4B4}
[data-template-editor] .te-menu{position:absolute;z-index:5;padding:6px;display:flex;flex-direction:column;gap:2px;border-radius:12px;background:#FFFFFF;border:1px solid ${SOFT_LINE};box-shadow:0 18px 40px -16px rgba(10,40,50,.4)}
[data-template-editor] .te-menu button{display:flex;align-items:center;gap:12px;padding:9px 12px;border:0;border-radius:8px;background:none;text-align:left;font:inherit;color:${INK};cursor:pointer}
[data-template-editor] .te-menu button:hover{background:#F3FAF8}
[data-template-editor] .te-field{height:40px;box-sizing:border-box;padding:0 12px;border-radius:10px;border:1px solid ${SOFT_LINE};background:#FFFFFF;font:inherit;font-size:14px;color:${INK};outline:none;width:100%}
[data-template-editor] .te-field[data-filled]{background:#F7FBFA}
[data-template-editor] .te-field:focus{border-color:#0E8A5F;box-shadow:0 0 0 3px rgba(14,138,95,.15);background:#FFFFFF}
`;

/* Fields grouped by their first word when two or more share it
 * (accused_name + accused_address -> "Accused"); the rest under "Other details". */
function groupFields(fields) {
    const head = f => String(f).split("_")[0];
    const counts = {};
    fields.forEach(f => { counts[head(f)] = (counts[head(f)] || 0) + 1; });
    const groups = [];
    const byName = {};
    fields.forEach(f => {
        const name = counts[head(f)] > 1 ? humanise(head(f)) : "Other details";
        if (!byName[name]) { byName[name] = { name, fields: [] }; groups.push(byName[name]); }
        byName[name].fields.push(f);
    });
    const other = groups.findIndex(g => g.name === "Other details");
    if (other >= 0) groups.push(groups.splice(other, 1)[0]);
    return groups;
}

const placeholderText = f => `[${humanise(f).toUpperCase()}]`;

export default function TemplateEditor(props) {
    const base = useT();
    const t = useMemo(() => ({ ...base, ...EDITOR_LIGHT }), [base]);
    return (
        <ThemeCtx.Provider value={t}>
            <EditorWindow {...props} />
        </ThemeCtx.Provider>
    );
}

function EditorWindow({ spec, onClose, onUse, cases = [] }) {
    const toast = useToast();
    const editorRef = useRef(null);
    const rangeRef = useRef(null);
    const closeRef = useRef(null);
    const shownRef = useRef({});          // field -> value last written into the page
    const fields = useMemo(() => templateFields(spec), [spec]);
    const groups = useMemo(() => groupFields(fields), [fields]);
    const saved = useMemo(() => (typeof window !== "undefined" ? readSaved(spec.template_type) : null), [spec.template_type]);

    const [values, setValues] = useState(saved?.values || {});
    const [counts, setCounts] = useState({ chars: 0, words: 0 });
    const [dirty, setDirty] = useState(false);
    const [savedAt, setSavedAt] = useState(saved?.savedAt || null);
    const [active, setActive] = useState({});
    const [font, setFont] = useState("Arial");
    const [size, setSize] = useState(12);
    const [block, setBlock] = useState("p");
    const [panelOpen, setPanelOpen] = useState(fields.length > 0);
    const [focusField, setFocusField] = useState(null);
    const [menu, setMenu] = useState(null);   // "download" | "more" | null

    const canEdit = typeof document !== "undefined" && typeof document.execCommand === "function";

    const recount = useCallback(() => {
        setCounts(countWords(editorRef.current?.innerText || ""));
    }, []);

    // The template's own wording; null for a PDF-only one (outline instead).
    const [original, setOriginal] = useState(undefined);   // undefined: loading
    const baseHtml = () => (original?.html ? realTextHtml(original.html) : outlineHtml(spec));

    useEffect(() => {
        let live = true;
        loadTemplateText(spec.template_type).then(res => {
            if (!live) return;
            setOriginal(res);
            if (res.failed) toast.show("Could not load this template's wording, so an outline is shown. Close and open it again to retry.", "warn", 5000);
        });
        return () => { live = false; };
    }, [spec.template_type]);

    // Load the page once: the saved copy on this device, else the template's
    // text when it arrives. Typing before then is not overwritten.
    const loadedRef = useRef(false);
    // What the page started from ("text": the template's own wording;
    // "outline": the fallback) and whether the client changed its WORDING.
    // Filling details from the panel is not a wording change.
    const pageBaseRef = useRef(saved?.base || "outline");
    const wordingRef = useRef(Boolean(saved?.edited));
    useEffect(() => {
        if (!editorRef.current || loadedRef.current) return;
        if (saved?.html) editorRef.current.innerHTML = cleanHtml(saved.html);
        else if (original === undefined) {
            editorRef.current.innerHTML = "<p>Loading the template…</p>";
            return;
        }
        else {
            editorRef.current.innerHTML = baseHtml();
            pageBaseRef.current = original?.html ? "text" : "outline";
        }
        loadedRef.current = true;
        shownRef.current = {};
        setValues(v => ({ ...v }));     // re-run the live fill on the new page
        recount();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [original]);
    useEffect(() => { closeRef.current?.focus(); }, []);

    /* Live fill: a field's value goes into its placeholders as it is typed, and
     * an emptied field puts the placeholder back. Only fields whose value changed
     * are touched, so text typed straight into the page elsewhere is kept. */
    useEffect(() => {
        const page = editorRef.current;
        if (!page) return;
        page.querySelectorAll("[data-field]").forEach(el => {
            const f = el.getAttribute("data-field");
            const v = (values[f] || "").trim();
            const first = !(f in shownRef.current);
            if (!first && shownRef.current[f] === v) return;
            if (!first || v) el.textContent = v || placeholderText(f);
            if (v) el.setAttribute("data-filled", ""); else el.removeAttribute("data-filled");
        });
        fields.forEach(f => { shownRef.current[f] = (values[f] || "").trim(); });
        recount();
    }, [values, fields, recount]);

    // The placeholder of the field being typed in gets a ring on the page.
    useEffect(() => {
        const page = editorRef.current;
        if (!page) return;
        page.querySelectorAll("[data-field]").forEach(el => {
            if (el.getAttribute("data-field") === focusField) el.setAttribute("data-active", "");
            else el.removeAttribute("data-active");
        });
    }, [focusField]);

    useEffect(() => {
        const onKey = e => {
            if (e.key !== "Escape") return;
            if (menu) { setMenu(null); return; }
            onClose();
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [onClose, menu]);

    /* The toolbar steals focus; remember where the cursor was so each command
     * applies to the text the user selected. */
    const remember = () => {
        const sel = typeof window !== "undefined" && window.getSelection ? window.getSelection() : null;
        if (sel && sel.rangeCount && editorRef.current?.contains(sel.anchorNode)) rangeRef.current = sel.getRangeAt(0).cloneRange();
        if (!canEdit || typeof document.queryCommandState !== "function") return;
        const q = c => { try { return document.queryCommandState(c); } catch { return false; } };
        setActive({ bold: q("bold"), italic: q("italic"), underline: q("underline"), strikeThrough: q("strikeThrough"),
            insertUnorderedList: q("insertUnorderedList"), insertOrderedList: q("insertOrderedList") });
    };
    const restore = () => {
        editorRef.current?.focus();
        const sel = window.getSelection?.();
        if (sel && rangeRef.current) { sel.removeAllRanges(); sel.addRange(rangeRef.current); }
    };
    const exec = (cmd, arg = null) => {
        if (!canEdit) return;
        restore();
        try { document.execCommand(cmd, false, arg); } catch { /* unsupported command: no-op */ }
        wordingRef.current = true;
        setDirty(true);
        recount();
        remember();
    };
    const applySize = px => {
        setSize(px);
        exec("fontSize", "7");
        // execCommand only knows sizes 1–7; swap its marker for the real size.
        editorRef.current?.querySelectorAll('font[size="7"]').forEach(el => {
            el.removeAttribute("size");
            el.style.fontSize = `${px}px`;
        });
    };
    const addLink = () => {
        setMenu(null);
        const url = window.prompt("Link address (https://…)", "https://");
        if (!url) return;
        if (!/^(https?:|mailto:)/i.test(url.trim())) { toast.show("Only web (https://) and email (mailto:) links can be added.", "warn", 3500); return; }
        exec("createLink", url.trim());
    };

    // A click on a placeholder in the page opens its field in the panel.
    const onPageClick = e => {
        remember();
        const el = e.target?.closest?.("[data-field]");
        if (!el) return;
        const f = el.getAttribute("data-field");
        if (!fields.includes(f)) return;
        setPanelOpen(true);
        setTimeout(() => document.getElementById(`cz_${f}`)?.focus(), 0);
    };

    const setValue = (f, v) => { setValues(prev => ({ ...prev, [f]: v })); setDirty(true); setCreateIssue(null); };

    const save = () => {
        const html = cleanHtml(editorRef.current?.innerHTML || "");
        try {
            const at = new Date().toISOString();
            window.localStorage.setItem(STORE_PREFIX + spec.template_type, JSON.stringify({ html, values, savedAt: at, base: pageBaseRef.current, edited: wordingRef.current }));
            setSavedAt(at);
            setDirty(false);
            toast.show("Saved on this device.", "success", 2500);
        } catch {
            toast.show("Could not save — this browser is not allowing storage.", "danger", 4000);
        }
    };
    const resetToOutline = () => {
        if (!window.confirm("Replace your copy with the original template? Your changes on this device will be lost.")) return;
        try { window.localStorage.removeItem(STORE_PREFIX + spec.template_type); } catch { /* storage blocked */ }
        editorRef.current.innerHTML = baseHtml();
        pageBaseRef.current = original?.html ? "text" : "outline";
        wordingRef.current = false;
        shownRef.current = {};
        setValues({}); setSavedAt(null); setDirty(false); recount();
    };

    /* Create draft (2026-10-19). The parent makes the document from these
     * details and opens it in the drafting workspace; this window stays open,
     * with the reason, if that fails. Changed wording on the template's own
     * text travels on and becomes the document's text; wording changed on an
     * outline cannot (it is not the document's text, and saying it was carried
     * would be untrue). `onUse` resolves to { ok, message }. */
    const [creating, setCreating] = useState(false);
    const [createIssue, setCreateIssue] = useState(null);
    const [caseId, setCaseId] = useState("");
    const [caseFill, setCaseFill] = useState(null);   // { busy } | { text, tone }
    const canFillFromCase = spec.drafting_mode === "ai" && cases.length > 0;
    const fillFromCase = async () => {
        if (!caseId) return;
        setCaseFill({ busy: true });
        const r = await extractDocumentFields(caseId, spec.template_type);
        const found = r?.error ? null : (r?.data?.fields || null);
        if (!found) { setCaseFill({ text: "Could not read details from that case. Fill them in yourself.", tone: "warn" }); return; }
        // Only empty details are filled: what the client typed stays theirs.
        const taken = fields.filter(f => typeof found[f] === "string" && found[f].trim() && !(values[f] || "").trim());
        if (taken.length) { setValues(v => ({ ...v, ...Object.fromEntries(taken.map(f => [f, found[f].trim()])) })); setDirty(true); setCreateIssue(null); }
        setCaseFill(taken.length
            ? { text: `Filled ${taken.length} detail${taken.length === 1 ? "" : "s"} from the case. Check each one.`, tone: "ok" }
            : { text: "The case had nothing new for the empty details.", tone: "muted" });
    };
    const useTemplate = async () => {
        if (creating) return;
        if (fields.length && filled === 0) {
            setCreateIssue("Fill at least one detail first — the draft is made from them.");
            setPanelOpen(true);
            setTimeout(() => document.getElementById(`cz_${fields[0]}`)?.focus(), 0);
            return;
        }
        let edited = null;
        if (wordingRef.current) {
            if (pageBaseRef.current === "text") edited = { html: tokenHtml(editorRef.current?.innerHTML || "") };
            else toast.show("Only your details are carried on: this template is drafted from its details, so wording changes here cannot be used.", "warn", 6000);
        }
        setCreating(true); setCreateIssue(null);
        let r;
        try { r = await onUse(spec, values, edited, caseId || null); }
        catch (e) { r = { ok: false, message: e?.message || "Could not create the draft." }; }
        setCreating(false);
        if (!r?.ok) setCreateIssue(r?.message || "Could not create the draft.");
    };

    const fileName = (spec.label || "document").replace(/[\\/:*?"<>|]+/g, " ").trim();
    const downloadWord = () => {
        setMenu(null);
        const blob = new Blob(["﻿", exportDoc(spec.label, editorRef.current?.innerHTML || "")], { type: "application/msword" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `${fileName}.doc`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    const downloadPdf = () => {
        setMenu(null);
        // The browser's own print dialog, where "Save as PDF" is the destination.
        const frame = document.createElement("iframe");
        frame.setAttribute("aria-hidden", "true");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
        document.body.appendChild(frame);
        const doc = frame.contentDocument;
        doc.open();
        doc.write(exportDoc(spec.label, editorRef.current?.innerHTML || ""));
        doc.close();
        setTimeout(() => {
            try { frame.contentWindow.focus(); frame.contentWindow.print(); }
            finally { setTimeout(() => frame.remove(), 1000); }
        }, 150);
    };

    const Tool = ({ label, cmd, arg, on, children, style }) => (
        <button type="button" className="te-tool" aria-label={label} title={label} aria-pressed={on || undefined} disabled={!canEdit}
            onMouseDown={e => e.preventDefault()} onClick={() => exec(cmd, arg)} style={style}>{children}</button>
    );
    const sep = <span aria-hidden="true" style={{ width: 1, height: 22, background: "#DCE8E5", margin: "0 4px" }} />;
    const filled = fields.filter(f => (values[f] || "").trim()).length;
    const pct = fields.length ? Math.round((filled / fields.length) * 100) : 0;
    const status = dirty
        ? { text: "Unsaved changes", bg: "#FFF4D6", fg: "#7A5200", dot: "#C98A00" }
        : savedAt
            ? { text: `Saved on this device · ${new Date(savedAt).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}`, bg: "#E3F4EC", fg: "#0E5E44", dot: "#1F9D63" }
            : { text: "Not saved yet", bg: "#EEF3F1", fg: MUTED, dot: "#93A9AD" };

    return (
        <ModalPortal>
        <div data-lenis-prevent data-docs-font onClick={onClose} style={{ ...BACKDROP, background: "rgba(12,40,44,.35)", display: "flex", alignItems: "center", justifyContent: "center", padding: "clamp(6px, 1.5vw, 20px)" }}>
            <style>{EDITOR_CSS}</style>
            <div data-template-editor role="dialog" aria-modal="true" aria-label="Customize template" onClick={e => { e.stopPropagation(); if (menu && !e.target.closest?.("[data-menu-root]")) setMenu(null); }}
                style={{ width: "min(1680px, 100%)", height: "100%", maxHeight: "calc(100vh - 12px)", background: EDITOR_LIGHT.surface, borderRadius: 20, display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 30px 80px rgba(8,40,44,.35)", color: INK, fontFamily: "'Hanken Grotesk', 'Inter', system-ui, sans-serif" }}>

                {/* Header: what this is, whether it is saved, the details toggle. */}
                <header style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", padding: "14px 20px", borderBottom: `1px solid ${LINE}` }}>
                    <span style={{ width: 40, height: 40, flex: "none", borderRadius: 12, display: "grid", placeItems: "center", background: BRAND, color: "#FFFFFF" }}><Svg d={I.doc} s={20} /></span>
                    <div style={{ flex: 1, minWidth: 220, display: "flex", flexDirection: "column", gap: 2 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                            <h2 style={{ margin: 0, fontSize: 19, lineHeight: "24px", fontWeight: 700 }}>{spec.label}</h2>
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, height: 22, padding: "0 9px", borderRadius: 999, background: status.bg, color: status.fg, fontSize: 12, fontWeight: 700 }}>
                                <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: "50%", background: status.dot }} />{status.text}
                            </span>
                        </div>
                        <p style={{ margin: 0, fontSize: 13, color: MUTED }}>Your own copy. The official template stays unchanged.</p>
                    </div>
                    {fields.length > 0 && (
                        <button type="button" className="te-btn" onClick={() => setPanelOpen(o => !o)} aria-pressed={panelOpen}
                            title={panelOpen ? "Hide the details panel" : "Show the details panel"} style={{ height: 38, padding: "0 14px", background: "#F3FAF8" }}>
                            <Svg d={I.panel} s={16} />Details <span style={{ color: ACCENT, fontWeight: 700 }}>{filled} / {fields.length}</span>
                        </button>
                    )}
                    <button type="button" ref={closeRef} aria-label="Close editor" onClick={onClose} className="te-btn" style={{ width: 38, height: 38, padding: 0, justifyContent: "center" }}><Svg d={I.close} s={16} w={2.2} /></button>
                </header>

                {/* Toolbar: the everyday commands; the rest under "More". */}
                <div role="toolbar" aria-label="Formatting" style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap", padding: "8px 20px", borderBottom: `1px solid ${LINE}`, background: "#FAFDFC" }}>
                    <Tool label="Undo" cmd="undo"><Svg d={I.undo} /></Tool>
                    <Tool label="Redo" cmd="redo"><Svg d={I.redo} /></Tool>
                    {sep}
                    <label htmlFor="te-block" style={{ position: "absolute", left: -9999 }}>Text style</label>
                    <select id="te-block" className="te-sel" value={block} disabled={!canEdit} onMouseDown={remember}
                        onChange={e => { setBlock(e.target.value); exec("formatBlock", `<${e.target.value}>`); }} style={{ width: 128 }}>
                        <option value="p">Paragraph</option>
                        <option value="h1">Heading 1</option>
                        <option value="h2">Heading 2</option>
                        <option value="h3">Heading 3</option>
                        <option value="blockquote">Quote</option>
                    </select>
                    <label htmlFor="te-font" style={{ position: "absolute", left: -9999 }}>Font</label>
                    <select id="te-font" className="te-sel" value={font} disabled={!canEdit} onMouseDown={remember}
                        onChange={e => { setFont(e.target.value); exec("fontName", e.target.value); }} style={{ width: 150 }}>
                        {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                    <label htmlFor="te-size" style={{ position: "absolute", left: -9999 }}>Font size</label>
                    <select id="te-size" className="te-sel" value={size} disabled={!canEdit} onMouseDown={remember}
                        onChange={e => applySize(Number(e.target.value))} style={{ width: 64 }}>
                        {SIZES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    {sep}
                    <Tool label="Bold" cmd="bold" on={active.bold} style={{ fontWeight: 800 }}>B</Tool>
                    <Tool label="Italic" cmd="italic" on={active.italic} style={{ fontStyle: "italic", fontFamily: "Georgia, serif", fontSize: 16 }}>I</Tool>
                    <Tool label="Underline" cmd="underline" on={active.underline} style={{ textDecoration: "underline" }}>U</Tool>
                    <Tool label="Strikethrough" cmd="strikeThrough" on={active.strikeThrough} style={{ textDecoration: "line-through" }}>S</Tool>
                    {sep}
                    <label htmlFor="te-align" style={{ position: "absolute", left: -9999 }}>Alignment</label>
                    <select id="te-align" className="te-sel" defaultValue="" disabled={!canEdit} onMouseDown={remember}
                        onChange={e => { const v = e.target.value; e.target.value = ""; if (v) exec(v); }} style={{ width: 108 }}>
                        <option value="" disabled>Align…</option>
                        <option value="justifyLeft">Left</option>
                        <option value="justifyCenter">Centre</option>
                        <option value="justifyRight">Right</option>
                        <option value="justifyFull">Justify</option>
                    </select>
                    <Tool label="Bulleted list" cmd="insertUnorderedList" on={active.insertUnorderedList}><Svg d={I.ul} /></Tool>
                    <Tool label="Numbered list" cmd="insertOrderedList" on={active.insertOrderedList}><Svg d={I.ol} /></Tool>
                    <span data-menu-root style={{ position: "relative" }}>
                        <button type="button" className="te-tool" aria-label="More formatting" title="More formatting" aria-haspopup="menu" aria-expanded={menu === "more"}
                            disabled={!canEdit} onMouseDown={e => { e.preventDefault(); remember(); }} onClick={() => setMenu(m => (m === "more" ? null : "more"))}>
                            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
                        </button>
                        {menu === "more" && (
                            <div role="menu" className="te-menu" style={{ top: 40, left: 0, width: 200 }}>
                                <button type="button" role="menuitem" onMouseDown={e => e.preventDefault()} onClick={addLink}><Svg d={I.link} s={16} />Insert link</button>
                                <button type="button" role="menuitem" onMouseDown={e => e.preventDefault()} onClick={() => { setMenu(null); exec("insertHorizontalRule"); }}><Svg d={I.hr} s={16} />Horizontal line</button>
                            </div>
                        )}
                    </span>
                    <span style={{ flex: 1 }} />
                    {fields.length > 0 && (
                        <span style={{ fontSize: 12.5, color: MUTED }}>Placeholders in <span style={{ padding: "1px 6px", borderRadius: 5, background: "#FFF4D6", color: "#7A5200", border: "1px dashed #D9A93A", fontWeight: 600 }}>amber</span> still need a value</span>
                    )}
                </div>

                {/* Page + details */}
                <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
                    {/* Thin edge and thin scrollbar: the grey gutter beside the
                        paper was wasted width (2026-11-22). */}
                    <div data-lenis-prevent className="thin-scrollbar" style={{ flex: 1, minWidth: 0, overflowY: "auto", background: "#EEF3F1", padding: "14px 10px" }}>
                        <div
                            ref={editorRef}
                            contentEditable={canEdit}
                            suppressContentEditableWarning
                            role="textbox"
                            aria-multiline="true"
                            aria-label="Document text"
                            spellCheck
                            onInput={() => { wordingRef.current = true; setDirty(true); recount(); }}
                            onKeyUp={remember}
                            onMouseUp={remember}
                            onBlur={remember}
                            onClick={onPageClick}
                            className="doc-editor-page"
                            style={{
                                minHeight: "100%", margin: "0 auto", background: "#fff", color: "#1d2a2e",
                                borderRadius: 6, boxShadow: "0 1px 2px rgba(10,40,50,.06), 0 12px 32px -14px rgba(10,40,50,.25)", boxSizing: "border-box",
                                padding: "clamp(24px, 6vw, 72px) clamp(20px, 7vw, 80px)", outline: "none",
                                fontFamily: `Arial, ${PAPER_FONT}`, fontSize: 15, lineHeight: 1.75,
                            }}
                        />
                    </div>

                    {panelOpen && fields.length > 0 && (
                        <aside aria-label="Fill the details" style={{ flex: "0 0 360px", borderLeft: `1px solid ${LINE}`, display: "flex", flexDirection: "column", minHeight: 0, background: "#FFFFFF" }}>
                            <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid #EEF3F1", display: "flex", flexDirection: "column", gap: 10 }}>
                                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Fill the details</h3>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT }}>{filled} of {fields.length} filled</span>
                                </div>
                                <div aria-hidden="true" style={{ height: 6, borderRadius: 6, background: "#E6EFED", overflow: "hidden" }}>
                                    <div style={{ width: `${pct}%`, height: "100%", borderRadius: 6, background: BRAND, transition: "width .25s" }} />
                                </div>
                                <p style={{ margin: 0, fontSize: 12.5, color: MUTED }}>The page updates as you type. Click an amber placeholder on the page to jump to its field.</p>
                                {canFillFromCase && (
                                    <div data-case-fill style={{ display: "flex", flexDirection: "column", gap: 6, paddingTop: 4 }}>
                                        <label htmlFor="te-case" style={{ fontSize: 12.5, fontWeight: 600 }}>Fill from a case</label>
                                        <div style={{ display: "flex", gap: 6 }}>
                                            <select id="te-case" className="te-field" value={caseId} onChange={e => { setCaseId(e.target.value); setCaseFill(null); }} style={{ flex: 1, minWidth: 0 }}>
                                                <option value="">No case (standalone)</option>
                                                {cases.map(c => <option key={c._id || c.id} value={c._id || c.id}>{c.title || c.case_type || "Case"}</option>)}
                                            </select>
                                            <button type="button" className="te-btn" onClick={fillFromCase} disabled={!caseId || Boolean(caseFill?.busy)}>{caseFill?.busy ? "Reading…" : "Fill"}</button>
                                        </div>
                                        {caseFill?.text && <span role="status" style={{ fontSize: 12, color: caseFill.tone === "warn" ? "#9A6200" : caseFill.tone === "ok" ? "#0E7A55" : MUTED }}>{caseFill.text}</span>}
                                    </div>
                                )}
                            </div>
                            <div data-lenis-prevent style={{ flex: 1, overflowY: "auto", padding: "14px 20px 18px", display: "flex", flexDirection: "column", gap: 18 }}>
                                {groups.map(g => (
                                    <section key={g.name} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                        <h4 style={{ margin: 0, fontSize: 11.5, letterSpacing: ".1em", textTransform: "uppercase", color: MUTED, fontWeight: 700 }}>{g.name}</h4>
                                        {g.fields.map(f => {
                                            const has = Boolean((values[f] || "").trim());
                                            return (
                                                <div key={f} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                                                    <label htmlFor={`cz_${f}`} style={{ display: "flex", justifyContent: "space-between", fontSize: 13, fontWeight: 600 }}>
                                                        {humanise(f)}{has && <span style={{ color: "#0E7A55", fontWeight: 700 }}>✓ Filled</span>}
                                                    </label>
                                                    <input id={`cz_${f}`} className="te-field" value={values[f] || ""} data-filled={has ? "" : undefined}
                                                        onChange={e => setValue(f, e.target.value)}
                                                        onFocus={() => setFocusField(f)} onBlur={() => setFocusField(cur => (cur === f ? null : cur))}
                                                        placeholder={`Enter ${humanise(f).toLowerCase()}…`} />
                                                </div>
                                            );
                                        })}
                                    </section>
                                ))}
                            </div>
                        </aside>
                    )}
                </div>

                {/* Footer: one main step; save and download beside it. */}
                <footer style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "12px 20px", borderTop: `1px solid ${LINE}`, background: "#FAFDFC" }}>
                    {/* A create problem takes the counts' place on the same row, so
                        the footer never grows a second line (2026-11-22). */}
                    {createIssue ? (
                        <span role="alert" style={{ fontSize: 13, color: "#B42318", marginRight: "auto" }}>{createIssue}</span>
                    ) : (
                        <span style={{ fontSize: 12.5, color: MUTED, marginRight: "auto" }}>
                            {counts.chars.toLocaleString()} characters · {counts.words.toLocaleString()} words · Saves in this browser only
                            {!canEdit && " · editing isn't supported in this browser"}
                        </span>
                    )}
                    {savedAt && <button type="button" className="te-btn danger" onClick={resetToOutline}>Reset to original</button>}
                    <button type="button" className="te-btn" onClick={save} disabled={!dirty && Boolean(savedAt)}>
                        <Svg d={I.save} s={16} />{dirty || !savedAt ? "Save changes" : "Saved ✓"}
                    </button>
                    <span data-menu-root style={{ position: "relative" }}>
                        <button type="button" className="te-btn" aria-haspopup="menu" aria-expanded={menu === "download"}
                            onClick={() => setMenu(m => (m === "download" ? null : "download"))}
                            style={menu === "download" ? { borderColor: "#0E8A5F" } : undefined}>
                            <Svg d={I.download} s={16} />Download<Svg d={I.chevron} s={14} w={2.4} />
                        </button>
                        {menu === "download" && (
                            <div role="menu" aria-label="Download as" className="te-menu" style={{ bottom: 48, right: 0, width: 290 }}>
                                <button type="button" role="menuitem" onClick={downloadWord}>
                                    <span style={{ width: 34, height: 34, flex: "none", borderRadius: 8, display: "grid", placeItems: "center", background: "#E1ECF8", color: "#1D4F8C" }}><Svg d={I.file} s={16} /></span>
                                    <span style={{ display: "flex", flexDirection: "column" }}><b style={{ fontSize: 14 }}>Word document</b><span style={{ fontSize: 12.5, color: MUTED }}>Opens in Microsoft Word</span></span>
                                </button>
                                <button type="button" role="menuitem" onClick={downloadPdf}>
                                    <span style={{ width: 34, height: 34, flex: "none", borderRadius: 8, display: "grid", placeItems: "center", background: "#F8E3E3", color: "#9B2C2C" }}><Svg d={I.file} s={16} /></span>
                                    <span style={{ display: "flex", flexDirection: "column" }}><b style={{ fontSize: 14 }}>PDF</b><span style={{ fontSize: 12.5, color: MUTED }}>Through the print dialog, “Save as PDF”</span></span>
                                </button>
                            </div>
                        )}
                    </span>
                    <button type="button" className="te-btn primary" data-create-draft onClick={useTemplate} disabled={creating}
                        title="Create the draft and open it in your drafting workspace">
                        {creating ? "Creating draft…" : "Create draft"}<Svg d={I.arrow} s={16} w={2.4} />
                    </button>
                </footer>
            </div>
        </div>
        </ModalPortal>
    );
}
