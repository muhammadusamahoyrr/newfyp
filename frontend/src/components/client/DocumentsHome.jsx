'use client';
/* Documents home — the prompt card, the template catalogue with its Preview
 * and Customize overlays, and whatever "continue" list the parent passes in.
 *
 * PRESENTATION ONLY. What "use a template" or "plan a draft" does stays in
 * ModDocuments; this component is handed the catalogue and callbacks. The
 * catalogue is the server's (`GET /documents/templates`); nothing here invents
 * an entry, a risk level or a clause.
 *
 * The preview shows the template's own wording, as its PDF builder writes it
 * (`GET /documents/templates/{type}/text`), each detail as a marked blank.
 * Until 2026-10-19 it showed only the field names, which made every template
 * look empty. A PDF-only template still shows that outline, and says why.
 * Since 2026-11-22 (user-approved clean-up) the preview is only the name, the
 * template text and one button: no tags, detail chips or side panel.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useT } from "./theme.js";
import { tint } from "./clientTheme.js";
import { humanise } from "@/lib/fieldReview.js";
import TemplateEditor, { loadTemplateText, realTextHtml } from "./documents/TemplateEditor.jsx";
import { LIcon } from "./documents/icons.jsx";
import {
    Btn, IconBtn, Chip, Card, Paper, Icon, ModalPortal, BACKDROP,
    SERIF, TOKEN_STYLE, VALUE_STYLE, fieldStyle,
} from "./documents/ui.jsx";

const TRY_PROMPTS = [
    "Notice to a tenant for unpaid rent",
    "Employment contract for a sales manager",
    "Affidavit for a lost CNIC",
    "NDA with a freelance designer",
    "Legal notice for a bounced cheque",
    "Rent agreement for a shop in Lahore",
    "Power of attorney for property in Pakistan",
];

/* The examples move as a strip under the heading. Twice the list, shifted by
 * half, loops without a jump; hover (or focus) pauses it; reduced motion
 * stops it and lets it scroll by hand instead. */
const TRY_STRIP_CSS = `@keyframes docsTryStrip{from{transform:translateX(0)}to{transform:translateX(-50%)}}
[data-try-strip] [data-try-track]{display:flex;gap:10px;width:max-content;animation:docsTryStrip 38s linear infinite}
[data-try-strip]:hover [data-try-track],[data-try-strip]:focus-within [data-try-track]{animation-play-state:paused}
@media (prefers-reduced-motion: reduce){[data-try-strip]{overflow-x:auto!important}[data-try-strip] [data-try-track]{animation:none}}`;

export function templateMatches(spec, query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) return true;
    return [spec.label, spec.description, spec.category]
        .some(v => (v || "").toLowerCase().includes(q));
}

function textFields(spec) {
    return (spec.fields || []).filter(f => !(spec.structured_fields || []).includes(f));
}

/* Escape closes, focus starts on the close button. */
function useDialog(onClose) {
    const closeRef = useRef(null);
    useEffect(() => {
        closeRef.current?.focus();
        const onKey = e => { if (e.key === "Escape") onClose(); };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [onClose]);
    return closeRef;
}

function Overlay({ children, onClose, pad = 26 }) {
    return (
        // data-lenis-prevent: the app's smooth scroll takes wheel events for the
        // page, so without it this overlay could not be scrolled with a mouse.
        <ModalPortal>
            <div data-lenis-prevent data-docs-font onClick={onClose} style={{ ...BACKDROP, display: "flex", alignItems: "flex-start", justifyContent: "center", padding: `clamp(8px, 3vw, ${pad}px)`, overflowY: "auto" }}>
                {children}
            </div>
        </ModalPortal>
    );
}

/* The builder's text on the page: its headings, paragraphs and tables, each
 * blank a marked detail (the same look as the editor's placeholders). */
const PAPER_TEXT_CSS = `[data-tpl-text]{font-size:14px;line-height:1.65}
[data-tpl-text] h1{margin:0 0 6px;font-size:16px;font-weight:700;letter-spacing:.04em;text-align:center}
[data-tpl-text] h2{margin:16px 0 6px;font-size:13.5px;font-weight:700;letter-spacing:.03em}
[data-tpl-text] p{margin:0 0 8px}
[data-tpl-text] hr{border:0;border-top:1px solid #d5dfdd;margin:12px 0}
[data-tpl-text] table{border-collapse:collapse;width:100%;margin:6px 0 10px;font-size:13px}
[data-tpl-text] td{border:1px solid #d5dfdd;padding:5px 8px;vertical-align:top}
[data-tpl-text] [data-field]{font-family:'Inter',sans-serif;font-size:12px;font-weight:600;background:#fdf0cf;color:#7a5200;border:1px solid #e9c46a;border-radius:5px;padding:0 5px;white-space:nowrap}`;

/* undefined while loading, then `{ html, failed }` (see loadTemplateText). */
function useTemplateText(type) {
    const [text, setText] = useState(undefined);
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        let live = true;
        setText(undefined);
        loadTemplateText(type).then(res => { if (live) setText(res); });
        return () => { live = false; };
    }, [type, attempt]);
    return [text, () => setAttempt(a => a + 1)];
}

/* The paper for a template: its real wording, or (PDF-only) its outline. */
function TemplatePaper({ spec, values = {} }) {
    const fields = textFields(spec);
    const [text, retry] = useTemplateText(spec.template_type);
    // The paper fills the whole preview window now, so the text sits further in.
    const paperStyle = { padding: "40px 72px", lineHeight: 1.6, minHeight: "100%" };
    if (text === undefined) {
        return <Paper width={2000} style={paperStyle}><p style={{ color: "#5b6b6f", margin: 0 }}>Loading the template…</p></Paper>;
    }
    if (text.html) {
        return (
            <Paper width={2000} style={paperStyle}>
                <style>{PAPER_TEXT_CSS}</style>
                <div data-tpl-text dangerouslySetInnerHTML={{ __html: realTextHtml(text.html) }} />
            </Paper>
        );
    }
    if (text.failed) {
        return (
            <Paper width={2000} style={paperStyle}>
                <div role="alert" data-tpl-text-failed style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 12 }}>
                    <b>Could not load this template's wording.</b>
                    <span style={{ fontSize: 13.5, color: "#5b6b6f" }}>The server did not answer. Its text is not missing; try again.</span>
                    <button type="button" onClick={retry} style={{ height: 36, padding: "0 16px", borderRadius: 9, border: "1px solid #9fd3cb", background: "#eaf7f5", color: "#12343a", fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}>Try again</button>
                </div>
            </Paper>
        );
    }
    return (
        <Paper title={(spec.label || "").toUpperCase()} width={2000} style={paperStyle}>
            <p style={{ margin: "0 0 12px", fontSize: 13, color: "#5b6b6f" }}>
                This document is built straight as a PDF from its details, so its full
                wording appears once they are filled in. Below: what it carries.
            </p>
            <p style={{ margin: "0 0 12px" }}>{spec.description}</p>
            {fields.length > 0 && (
                <>
                    <p style={{ margin: "0 0 8px", fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 700, letterSpacing: ".06em", color: "#5b6b6f" }}>
                        DETAILS THIS DOCUMENT CARRIES
                    </p>
                    {fields.map(f => {
                        const v = (values[f] || "").trim();
                        return (
                            <p key={f} style={{ margin: "0 0 4px" }}>
                                <b>{humanise(f)}: </b>
                                {v ? <span style={VALUE_STYLE}>{v}</span> : <span style={TOKEN_STYLE}>{humanise(f)}</span>}
                            </p>
                        );
                    })}
                </>
            )}
        </Paper>
    );
}

/* The preview header's controls: prev / count / next as one segmented group,
 * and a plain close button. Theme vars, so light and dark both read. */
const PREVIEW_CSS = `[data-tpl-preview] .tp-nav{display:inline-flex;align-items:center;height:34px;border:1px solid;border-radius:10px;overflow:hidden;flex:none}
[data-tpl-preview] .tp-nav span{padding:0 10px;font-size:12.5px;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}
[data-tpl-preview] .tp-nav button,[data-tpl-preview] .tp-close{display:inline-grid;place-items:center;border:0;background:none;color:var(--ink,currentColor);cursor:pointer;transition:background .15s,color .15s}
[data-tpl-preview] .tp-nav button{width:34px;height:100%}
[data-tpl-preview] .tp-close{width:34px;height:34px;border-radius:10px;flex:none}
[data-tpl-preview] .tp-nav button:hover,[data-tpl-preview] .tp-close:hover{background:var(--hover-tint,rgba(255,255,255,.08));color:var(--brand-text,inherit)}
[data-tpl-preview] .tp-nav button:focus-visible,[data-tpl-preview] .tp-close:focus-visible{outline:2px solid var(--brand-text,#3fd6c6);outline-offset:-2px}`;

function PreviewDialog({ t, list, index, onIndex, onClose, onUse, dedicatedHref }) {
    const closeRef = useDialog(onClose);
    const spec = list[index];
    const go = d => onIndex((index + d + list.length) % list.length);
    const dedicated = spec.drafting_mode === "dedicated";
    return (
        <Overlay onClose={onClose} pad={24}>
            {/* Layout (2026-11-22, approved preview): the name, the template
                text and one button. The paper fills the window (a thin edge,
                no empty band) and scrolls inside; the button is a footer. */}
            <style>{PREVIEW_CSS}</style>
            <div role="dialog" aria-modal="true" aria-label="Template preview" data-tpl-preview onClick={e => e.stopPropagation()}
                style={{ width: "min(1080px, 100%)", height: "min(780px, calc(100vh - 48px))", margin: "auto 0", background: t.surface, border: `1px solid ${t.border}`, borderRadius: 18, display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 30px 80px rgba(0,0,0,.5)" }}>
                <header style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 14px 12px 22px", borderBottom: `1px solid ${t.border}` }}>
                    <div style={{ minWidth: 0, flex: 1, display: "flex", alignItems: "center", gap: 10 }}>
                        <h2 style={{ margin: 0, fontFamily: SERIF, fontSize: 20, fontWeight: 600, color: t.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{spec.label}</h2>
                    </div>
                    <div className="tp-nav" style={{ borderColor: t.border }}>
                        <button type="button" aria-label="Previous template" title="Previous template" onClick={() => go(-1)}><LIcon name="chevronLeft" size={18} stroke={2.2} /></button>
                        <span style={{ color: t.textMuted }}>{index + 1} of {list.length}</span>
                        <button type="button" aria-label="Next template" title="Next template" onClick={() => go(1)}><LIcon name="chevronRight" size={18} stroke={2.2} /></button>
                    </div>
                    <button type="button" className="tp-close" aria-label="Close preview" title="Close preview" onClick={onClose} ref={closeRef}><LIcon name="x" size={19} stroke={2.2} /></button>
                </header>
                <div data-lenis-prevent className="hide-scrollbar" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "12px 12px 0" }}>
                    <TemplatePaper spec={spec} />
                </div>
                <footer style={{ flex: "none", padding: "14px 20px", borderTop: `1px solid ${t.border}`, display: "flex", justifyContent: "flex-end" }}>
                    {dedicated ? (
                        <Btn kind="primary" href={dedicatedHref(spec)}>Open dedicated calculator</Btn>
                    ) : (
                        <Btn kind="primary" onClick={() => onUse(spec)}>Use this template <LIcon name="arrowRight" size={16} stroke={2.2} /></Btn>
                    )}
                </footer>
            </div>
        </Overlay>
    );
}

/* The popular documents on the AI drafting start screen. Each fills the
 * description box (it does not send); `law` names the Act the document is
 * written under, shown as a reference, not as a check. */
const POPULAR_DRAFTS = [
    { title: "Non-disclosure agreement", text: "Protect confidential information shared between parties.", law: "Contract Act 1872", prompt: "Draft a non-disclosure agreement" },
    { title: "Employment agreement", text: "Set clear terms for employees or contractors.", law: "Contract Act 1872", prompt: "Draft an employment agreement" },
    { title: "Legal notice", text: "Send a formal notice for breach or payment.", law: "Pre-litigation notice", prompt: "Draft a legal notice" },
    { title: "Affidavit", text: "Create a sworn statement for official or legal use.", law: "Oaths Act 1873", prompt: "Draft an affidavit" },
    { title: "Rent agreement", text: "Tenancy terms for residential or commercial premises.", law: "Punjab Rented Premises Act 2009", prompt: "Draft a rent agreement" },
    { title: "Power of attorney", text: "Authorise someone to act on your behalf.", law: "Powers of Attorney Act 1882", prompt: "Draft a power of attorney" },
];

/* A native select drawn as the composer's pill: icon, value, chevron. Native,
 * so keyboard and screen readers work as they do for any select. */
/* A compact pill that opens the app's own menu (2026-10-10). The browser's
 * native dropdown looked different in every browser and filled the screen; the
 * menu is now drawn here, in the theme: rounded, the choice ticked, hover and
 * arrow-key highlight, Enter to choose, Escape to close. It renders in a portal
 * at a fixed position (the composer clips overflow) and opens upward when there
 * is no room below. The real <select> stays, visually hidden, as the value's
 * source of truth: `onChange` receives the same event shape as before. */
const PILL_CSS = `[data-client-theme] .pill-menu{position:fixed;z-index:9999;max-height:300px;overflow:auto;min-width:200px;max-width:320px;padding:4px;border-radius:11px;border:1px solid var(--line-strong);background:var(--surface);box-shadow:0 18px 36px -12px rgba(0,0,0,.6);scrollbar-width:none;-ms-overflow-style:none}
[data-client-theme] .pill-menu::-webkit-scrollbar{display:none}
[data-client-theme] .pill-menu button{display:flex;align-items:center;gap:8px;width:100%;padding:6px 9px;border:0;border-radius:7px;background:none;color:var(--ink);font-family:inherit;font-size:13px;font-weight:500;line-height:1.35;text-align:left;cursor:pointer}
[data-client-theme] .pill-menu button[data-hot]{background:var(--hover-tint);color:var(--hover-ink)}
[data-client-theme] .pill-menu button[aria-selected="true"]{color:var(--brand-text);font-weight:600}
[data-client-theme] .pill-menu button .tick{margin-left:auto;flex:none}
[data-client-theme] [data-pill]{transition:border-color .15s,background .15s}
[data-client-theme] [data-pill]:hover,[data-client-theme] [data-pill][data-open]{border-color:var(--hover-line)!important;background:var(--hover-tint)!important}`;

function PillSelect({ t, id, label, icon, value, onChange, shown = "", warn = false, title, children, ...rest }) {
    const selectRef = useRef(null);
    const pillRef = useRef(null);
    const [open, setOpen] = useState(false);
    const [hot, setHot] = useState(0);
    const [pos, setPos] = useState(null);
    // The choices, read from the <option> children.
    const options = React.Children.toArray(children).filter(Boolean).map(o => ({ value: o.props.value ?? "", label: o.props.children }));
    const choose = v => {
        const el = selectRef.current;
        if (el && v !== value) {
            // Through the real select, so onChange gets the event it always got.
            Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value").set.call(el, v);
            el.dispatchEvent(new Event("change", { bubbles: true }));
        }
        setOpen(false);
        pillRef.current?.focus();
    };
    const place = () => {
        const r = pillRef.current?.getBoundingClientRect();
        if (!r) return;
        const below = window.innerHeight - r.bottom;
        const up = below < 320 && r.top > below;
        setPos({ left: Math.min(r.left, window.innerWidth - 350), ...(up ? { bottom: window.innerHeight - r.top + 6 } : { top: r.bottom + 6 }) });
    };
    const openMenu = () => { place(); setHot(Math.max(0, options.findIndex(o => o.value === value))); setOpen(true); };
    useEffect(() => {
        if (!open) return undefined;
        const out = e => { if (!pillRef.current?.contains(e.target) && !e.target.closest?.("[data-pill-menu]")) setOpen(false); };
        const close = () => setOpen(false);
        document.addEventListener("mousedown", out);
        window.addEventListener("resize", close);
        window.addEventListener("scroll", close, true);
        return () => { document.removeEventListener("mousedown", out); window.removeEventListener("resize", close); window.removeEventListener("scroll", close, true); };
    }, [open]);
    const onKey = e => {
        if (!open && ["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); openMenu(); return; }
        if (!open) return;
        if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
        else if (e.key === "ArrowDown") { e.preventDefault(); setHot(h => Math.min(options.length - 1, h + 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setHot(h => Math.max(0, h - 1)); }
        else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (options[hot]) choose(options[hot].value); }
        else if (e.key === "Tab") setOpen(false);
    };
    const menuId = `${id}-menu`;
    return (
        <span style={{ position: "relative", display: "inline-flex", flexShrink: 0 }}>
            <style>{PILL_CSS}</style>
            <button type="button" ref={pillRef} data-pill data-open={open ? "true" : undefined} title={title || shown}
                aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? menuId : undefined} aria-label={`${label}: ${shown}`}
                onClick={() => (open ? setOpen(false) : openMenu())} onKeyDown={onKey}
                style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 6, height: 34, padding: "0 26px 0 10px", borderRadius: 10, boxSizing: "border-box",
                    border: `1px solid ${warn ? t.warn : t.border}`, boxShadow: warn ? `0 0 0 2px ${t.warn}33` : "none", background: t.bg, color: t.text, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>
                {icon && <LIcon name={icon} size={14} style={{ color: t.textMuted }} />}
                <span data-pill-value style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 170 }}>{shown}</span>
                <LIcon name="chevronDown" size={13} style={{ position: "absolute", right: 9, pointerEvents: "none", color: t.textMuted, transform: open ? "rotate(180deg)" : "none", transition: "transform .15s" }} />
            </button>
            {/* The value's source of truth (and what assistive tech and tests read). */}
            <label htmlFor={id} style={{ position: "absolute", left: -9999 }}>{label}</label>
            <select id={id} ref={selectRef} value={value} onChange={onChange} tabIndex={-1} aria-hidden="true" {...rest}
                style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none", overflow: "hidden", clip: "rect(0 0 0 0)" }}>
                {children}
            </select>
            {open && pos && createPortal(
                <div id={menuId} role="listbox" aria-label={label} className="pill-menu" data-pill-menu data-lenis-prevent style={pos}>
                    {options.map((o, i) => (
                        <button key={o.value || "none"} type="button" role="option" aria-selected={o.value === value}
                            data-hot={i === hot ? "true" : undefined} onMouseEnter={() => setHot(i)}
                            onMouseDown={e => e.preventDefault()} onClick={() => choose(o.value)}>
                            <span style={{ minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{o.label}</span>
                            {o.value === value && <span className="tick" style={{ display: "flex" }}><LIcon name="check" size={14} stroke={2.4} /></span>}
                        </button>
                    ))}
                </div>,
                document.body,
            )}
        </span>
    );
}

export function PromptCard({ t, templates, cases, onPlan, workspace = false, onViewTemplates = null, typeRequired = false }) {
    const [text, setText] = useState("");
    const [type, setType] = useState("");
    const [caseId, setCaseId] = useState("");
    const boxRef = useRef(null);
    const ready = text.trim().length > 0;
    const plan = () => ready && onPlan({ prompt: text.trim(), templateType: type || null, caseId: caseId || null });
    const fill = value => { setText(value); boxRef.current?.focus(); };
    const needType = typeRequired && !type;
    const optionStyle = { background: t.card, color: t.text };

    const composer = (
        /* The composer (approved design, 2026-10-08): the description, "Try"
         * examples while it is empty, and one toolbar of choices. */
        <div data-prompt-card style={{ borderRadius: 16, border: `1.5px solid ${t.primary}88`, background: t.mode === "dark" ? "#0b2228" : (t.cardHi || t.card), boxShadow: `0 0 0 3px ${t.primary}10`, overflow: "hidden" }}>
            <div style={{ padding: "16px 18px 10px", display: "flex", flexDirection: "column", gap: 10 }}>
                <label htmlFor="docs-need" style={{ position: "absolute", left: -9999 }}>Describe the document you need</label>
                <textarea id="docs-need" ref={boxRef} rows={3} value={text} onChange={e => setText(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); plan(); } }}
                    placeholder="e.g. 6-month NDA between ABC Pvt Ltd and a freelance designer in Karachi"
                    style={{ width: "100%", boxSizing: "border-box", resize: "vertical", minHeight: 84, outline: "none", border: "none", background: "transparent", color: t.text, fontSize: 16.5, lineHeight: 1.55, padding: 0 }} />
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", padding: "10px 14px", borderTop: `1px solid ${t.border}` }}>
                {/* When the description did not say which document it is, the
                    type is asked HERE -- there is no separate page for it. */}
                <PillSelect t={t} id="docs-dtype" label="Document type" icon="fileText" value={type} onChange={e => setType(e.target.value)}
                    shown={type ? ((templates || []).find(s => s.template_type === type)?.label || type) : "Detect from description"}
                    warn={needType} data-type-required={needType ? "true" : undefined}>
                    <option value="" style={optionStyle}>Detect from description</option>
                    {(templates || []).filter(s => s.drafting_mode === "ai").map(s => <option key={s.template_type} value={s.template_type} style={optionStyle}>{s.label}</option>)}
                </PillSelect>
                <PillSelect t={t} id="docs-dcase" label="Linked case" icon="scale" value={caseId} onChange={e => setCaseId(e.target.value)}
                    shown={caseId ? (() => { const c = (cases || []).find(x => (x._id || x.id) === caseId); return c?.title || c?.case_type || caseId; })() : "Standalone"}>
                    <option value="" style={optionStyle}>Standalone</option>
                    {(cases || []).map(c => <option key={c._id || c.id} value={c._id || c.id} style={optionStyle}>{c.title || c.case_type || (c._id || c.id)}</option>)}
                </PillSelect>
                {/* No upload behind it yet: shown, labelled, not clickable. */}
                <button type="button" disabled data-attach-soon title="Attaching files isn't connected yet — coming soon."
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, minHeight: 38, padding: "0 6px", border: "none", background: "transparent", color: t.textMuted, fontSize: 13.5, fontWeight: 600, cursor: "not-allowed", opacity: 0.75 }}>
                    <LIcon name="paperclip" size={15} />Attach
                </button>
                <button type="button" disabled={!ready} onClick={plan} data-plan-draft title="Plan my draft (Ctrl + Enter)"
                    style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, height: 38, padding: "0 14px", marginLeft: "auto", borderRadius: 999, border: "none",
                        // The app's main-button gradient, as on Overview (2026-11-23).
                        background: "linear-gradient(135deg,#12897f,#1c9c66)", color: "#fff",
                        fontSize: 14, fontWeight: 700, lineHeight: 1, whiteSpace: "nowrap", cursor: ready ? "pointer" : "not-allowed", opacity: ready ? 1 : 0.6, boxShadow: ready ? "0 8px 20px -10px rgba(28,156,102,.8)" : "none", flexShrink: 0 }}>
                    <LIcon name="sparkles" size={15} />Plan my draft
                </button>
            </div>
            {needType && (
                <div role="alert" data-type-hint style={{ padding: "0 16px 12px", fontSize: 13, color: t.warn }}>
                    We couldn't tell which document this is — choose it under "Detect from description", then press Plan my draft.
                </div>
            )}
        </div>
    );

    if (!workspace) return composer;

    return (
        <div style={{ width: "100%", maxWidth: 1240, margin: "0 auto", display: "flex", flexDirection: "column", gap: 30 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 15 }}>
                <nav aria-label="Breadcrumb" style={{ display: "flex", alignItems: "center", gap: 10, color: t.textMuted }}>
                    {onViewTemplates
                        ? <button type="button" onClick={onViewTemplates} style={{ background: "none", border: "none", padding: 0, color: t.textMuted, fontSize: 15, cursor: "pointer" }}>Documents</button>
                        : <span>Documents</span>}
                    <span aria-hidden="true">/</span>
                    <span style={{ color: t.text, fontWeight: 600 }}>New draft</span>
                </nav>
                <span style={{ flex: 1 }} />
                {/* True of every draft: owner-only until the owner sends it. */}
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8, color: t.textMuted, fontSize: 14.5 }}>
                    <LIcon name="shield" size={17} style={{ color: t.warn }} />Private to your workspace
                </span>
            </div>

            <div>
                <h1 style={{ margin: 0, fontSize: 34, fontWeight: 600, color: t.text }}>What do you need to draft?</h1>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16 }}>
                    <style>{TRY_STRIP_CSS}</style>
                    <div data-try-strip aria-label="Example requests" style={{ flex: 1, minWidth: 0, overflow: "hidden",
                        maskImage: "linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent)", WebkitMaskImage: "linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent)" }}>
                        <div data-try-track>
                            {[...TRY_PROMPTS, ...TRY_PROMPTS].map((p, i) => (
                                <button key={`${p}-${i}`} type="button" onClick={() => fill(p)}
                                    // The second copy is only for the loop: one tab stop and one announcement per example.
                                    tabIndex={i < TRY_PROMPTS.length ? 0 : -1} aria-hidden={i < TRY_PROMPTS.length ? undefined : "true"}
                                    style={{ flexShrink: 0, padding: "6px 14px", borderRadius: 999, border: `1px solid ${t.border}`, background: t.card, color: t.text, fontSize: 13.5, whiteSpace: "nowrap", cursor: "pointer" }}>{p}</button>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {composer}

            <section aria-label="Popular documents" style={{ display: "flex", flexDirection: "column", gap: 18, marginTop: 6 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: t.text }}>Start with a popular document</h2>
                    <span style={{ flex: 1 }} />
                    {/* A real link back to the catalogue, or nothing. */}
                    {onViewTemplates && (
                        <button type="button" onClick={onViewTemplates}
                            style={{ display: "inline-flex", alignItems: "center", gap: 6, background: "none", border: "none", color: t.primary, fontSize: 14, fontWeight: 600, cursor: "pointer", padding: 0 }}>
                            View all <LIcon name="arrowRight" size={15} />
                        </button>
                    )}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))", gap: 18 }}>
                    {POPULAR_DRAFTS.map(d => (
                        <button key={d.title} type="button" data-popular={d.title} onClick={() => fill(d.prompt)}
                            style={{ display: "flex", alignItems: "flex-start", gap: 14, padding: 18, borderRadius: 16, border: `1px solid ${t.border}`, background: t.mode === "dark" ? "#0b1f24" : t.card, color: t.text, textAlign: "left", cursor: "pointer" }}>
                            <span aria-hidden="true" style={{ width: 44, height: 44, flexShrink: 0, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", background: `${t.primary}1a`, border: `1px solid ${t.primary}33`, color: t.primary }}>
                                <LIcon name="fileText" size={19} />
                            </span>
                            <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                                <strong style={{ fontSize: 16, fontWeight: 600 }}>{d.title}</strong>
                                <span style={{ fontSize: 13.5, lineHeight: 1.5, color: t.textMuted }}>{d.text}</span>
                                <span style={{ fontSize: 12.5, fontWeight: 600, color: t.warn, marginTop: 2 }}>{d.law}</span>
                            </span>
                            <LIcon name="arrowRight" size={18} style={{ color: t.textMuted, marginTop: 4 }} />
                        </button>
                    ))}
                </div>
            </section>
        </div>
    );
}

export default function DocumentsHome({
    templates, templateIssue, cases, draftingMode, dedicatedToolHref,
    onUse, onPlan, onOpenView, continueSlot,
}) {
    const t = useT();
    const [query, setQuery] = useState("");
    const [category, setCategory] = useState("All");
    const [preview, setPreview] = useState(null);     // index into `shown`
    const [customize, setCustomize] = useState(null); // spec

    const list = useMemo(() => (templates || []).map(s => ({ ...s, drafting_mode: draftingMode(s) })), [templates, draftingMode]);
    const categories = useMemo(() => {
        const counts = new Map();
        for (const spec of list) counts.set(spec.category, (counts.get(spec.category) || 0) + 1);
        return [["All", list.length], ...[...counts.entries()].sort(([a], [b]) => a.localeCompare(b))];
    }, [list]);
    const shown = list.filter(spec =>
        (category === "All" || spec.category === category) && templateMatches(spec, query));
    // The counts sit in the section's subtitle (2026-11-22). Four stat tiles
    // used to show them -- "Total templates" and "Available" were the same
    // number, and the block pushed the templates below the fold.
    const templateCount = templates === null ? null : list.length;
    const categoryCount = templates === null ? null : new Set(list.map(spec => spec.category).filter(Boolean)).size;
    // On the dashboard's palette (clientTheme.js) the cards and icons take its
    // surface and soft accents; otherwise the original colours stay.
    const onTokens = !!t.onTokens;

    // "Use template" opens the template's own text to fill in (2026-10-19).
    // The separate guided flow is gone from here: "Create draft" in the editor
    // makes the document and opens it in the drafting workspace, the same place
    // an AI draft opens. `onUse` resolves to { ok, message }.
    const use = spec => { setPreview(null); setCustomize(spec); };
    const create = async (spec, values, edited, caseId) => {
        const r = await onUse(spec, values, edited, caseId);
        if (r?.ok) setCustomize(null);
        return r;
    };
    // The cards' round icon buttons.
    const roundBtn = { width: 40, height: 40, borderRadius: "50%", color: t.primary };

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                    <h1 style={{ margin: 0, fontFamily: SERIF, fontSize: 34, fontWeight: 600, color: t.text }}>Documents</h1>
                    <div style={{ marginTop: 4, fontSize: 14, color: t.textMuted }}>Draft with AI, start from a template, or continue your work.</div>
                </div>
                {/* `.ch-pill-solid`: the lawyer's solid pill (Appointments' Export Excel);
                    `.ch-pill-go`: the icon in a round badge and an arrow, as a way to another page. */}
                {onTokens ? (
                    <Btn onClick={() => onOpenView?.("vault")} className="ch-pill-solid ch-pill-go">
                        <span className="b" aria-hidden="true">{Icon.folder}</span>Vault
                        <svg className="go" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                    </Btn>
                ) : (
                    <Btn onClick={() => onOpenView?.("vault")}>{Icon.folder} Vault</Btn>
                )}
            </div>

            <section id="templates" aria-label="Document templates" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {/* Row 1: the heading, and search on the far right. Row 2: the
                    category filters on a line of their own (2026-10-08). */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <h2 style={{ margin: 0, fontFamily: SERIF, fontSize: 20, fontWeight: 600, color: onTokens ? "var(--brand-text)" : t.text }}>Start from a template</h2>
                    <span data-template-summary style={{ fontSize: 13, color: t.textMuted }}>
                        {templateCount !== null
                            ? `${templateCount} reviewed templates · ${categoryCount} areas of law · you only fill the details`
                            : "Reviewed builders · you only fill the details"}
                    </span>
                    <div style={{ flex: 1 }} />
                    {/* `.ch-search`: the lawyer Cases search's hover and focus ring. */}
                    <div data-template-search className={onTokens ? "ch-search" : undefined} style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 12px", borderRadius: 10, border: `1px solid ${query ? t.primary : (t.inputBorder || t.border)}`, background: t.inputBg, width: "min(280px, 100%)", marginLeft: "auto" }}>
                        <span style={{ color: t.textMuted, display: "flex" }}>{Icon.search}</span>
                        <label htmlFor="tpl-search" style={{ position: "absolute", left: -9999 }}>Search templates</label>
                        <input id="tpl-search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search templates"
                            style={{ flex: 1, minWidth: 0, minHeight: 40, background: "transparent", border: "none", outline: "none", color: t.text, fontSize: 14, fontFamily: "'Inter', sans-serif" }} />
                        {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search" style={{ background: "none", border: "none", color: t.textMuted, cursor: "pointer", fontSize: 18 }}>×</button>}
                    </div>
                </div>
                {categories.length > 2 && (
                    <div role="group" aria-label="Filter by category" data-category-filters style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", ...(onTokens ? { margin: "8px 0 10px" } : null) }}>
                        {categories.map(([name, count]) => (
                            <Chip key={name} active={category === name} onClick={() => setCategory(name)} className={onTokens ? "ch-chip" : undefined}>
                                {name}<span className={onTokens ? "n" : undefined} style={onTokens ? undefined : { opacity: 0.7, fontWeight: 500 }}>{count}</span>
                            </Chip>
                        ))}
                    </div>
                )}

                {templateIssue ? (
                    <div role="alert" style={{ padding: "14px 16px", borderRadius: 12, background: `${t.warn}14`, border: `1px solid ${t.warn}55`, color: t.text, fontSize: 13 }}>{templateIssue}</div>
                ) : templates === null ? (
                    <div aria-busy="true" style={{ textAlign: "center", padding: 48, color: t.textMuted, fontSize: 13 }}>Loading available templates…</div>
                ) : shown.length === 0 ? (
                    <div style={{ textAlign: "center", padding: "40px 16px", color: t.textMuted, fontSize: 13.5 }}>
                        {list.length === 0 ? "No templates found." : <>No template matches{query ? <> “{query}”</> : null}.{" "}
                            <button type="button" onClick={() => { setQuery(""); setCategory("All"); }}
                                style={{ background: "none", border: "none", color: t.primary, fontWeight: 700, cursor: "pointer", fontSize: 13.5, padding: 0 }}>
                                Show all templates
                            </button></>}
                    </div>
                ) : (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(290px, 100%), 1fr))", gap: 16 }}>
                        {shown.map((spec, i) => {
                            const dedicated = spec.drafting_mode === "dedicated";
                            const ai = spec.drafting_mode === "ai";
                            const n = textFields(spec).length;
                            // A small marker only where the mode changes what happens
                            // (AI fills from the case; a calculator works out figures).
                            // "You fill the details" is the default and needs none.
                            const markInk = ai ? (onTokens ? "var(--brand-text)" : t.primary) : t.textMuted;
                            return (
                                /* Cleaned card (2026-11-22): category and mode marker,
                                   the name, what it is for, the facts, the actions.
                                   Removed: the icon tile (the same scales icon on
                                   almost every card), the mode pill on every card,
                                   "PDF" (every template is one), and the Edit button
                                   (it did exactly what "Use template" does). */
                                <Card key={spec.template_type} data-template={spec.template_type} title={spec.description} className={onTokens ? "ch-tcard" : undefined}
                                    style={{ display: "flex", flexDirection: "column", gap: 10, padding: 18, minHeight: 0, boxSizing: "border-box" }}>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, minHeight: 20 }}>
                                        <span data-template-category style={{ fontSize: 12, fontWeight: 600, color: t.textMuted }}>{spec.category}</span>
                                        {(ai || dedicated) && (
                                            <span data-template-mode={spec.drafting_mode} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: markInk }}>
                                                <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: ai ? 999 : 2, background: ai ? markInk : "transparent", border: ai ? "none" : `1.5px solid ${markInk}` }} />
                                                {ai ? "AI-assisted" : "Calculator"}
                                            </span>
                                        )}
                                    </div>
                                    <h3 style={{ margin: 0, fontSize: 16.5, fontWeight: 600, color: t.text, lineHeight: 1.35, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{spec.label}</h3>
                                    {spec.description && (
                                        <p data-template-description style={{ margin: 0, fontSize: 13.5, lineHeight: 1.45, color: t.textMuted, minHeight: 39, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{spec.description}</p>
                                    )}
                                    <div style={{ fontSize: 13, color: t.textMuted, marginTop: "auto", paddingTop: 4 }}>
                                        {dedicated ? "Calculated figures" : n > 0 ? `${n} details to fill` : "No details needed"}
                                    </div>
                                    <div style={{ display: "flex", gap: 8 }}>
                                        <IconBtn label={`Preview ${spec.label}`} onClick={() => setPreview(i)} style={roundBtn} className={onTokens ? "ch-ib" : undefined}><LIcon name="eye" size={18} /></IconBtn>
                                        {dedicated ? (
                                            <Btn href={dedicatedToolHref(spec)} style={{ flex: 1, minHeight: 38, color: t.primary }}>Open dedicated calculator</Btn>
                                        ) : (
                                            <Btn kind="primary" className={onTokens ? "ch-card-use" : undefined} onClick={() => use(spec)} style={{ flex: 1, minHeight: 38 }}>Use template</Btn>
                                        )}
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                )}
            </section>

            {continueSlot}

            {preview !== null && shown[preview] && (
                <PreviewDialog t={t} list={shown} index={preview} onIndex={setPreview}
                    onClose={() => setPreview(null)} onUse={spec => use(spec)}
                    dedicatedHref={dedicatedToolHref} />
            )}
            {customize && (
                <TemplateEditor spec={customize} onClose={() => setCustomize(null)}
                    cases={cases} onUse={create} />
            )}
        </div>
    );
}
