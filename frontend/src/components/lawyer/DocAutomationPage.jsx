'use client';
// Lawyer Document Automation Page — paste your code here
import { useState, useRef, useEffect } from "react";
import { useTheme } from "./theme.js";
import { useCase } from "./theme.js";
import { Icon, I } from "./icons.jsx";
import { listCases, getCase, aiDraftStream, saveDocDraft, listDocDrafts, deleteDocDraft, aiPleadingUrduStream, pleadingUrduPdf, pleadingUrduDocumentV2, publishDraftAsDocumentV2, downloadDocumentFile, idempotencyKey, errorCode } from "@/lib/api.js";

// Infer the statute collection to ground drafting in, from the template.
function templateCaseType(name = "") {
    const n = name.toLowerCase();
    if (/bail|criminal|fir|crpc|ppc|remand|acquittal|f\.?i\.?r/.test(n)) return "criminal";
    if (/marriage|divorce|khula|custody|nikah|dower|maintenance|guardian|family/.test(n)) return "family";
    if (/writ|constitution|fundamental right|article 199|mandamus|habeas/.test(n)) return "constitutional";
    return "civil";
}
import { useAuth } from "@/context/AuthContext.jsx";
import DraftingHome from "./DraftingHome.jsx";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { ModalPortal } from "./ui.jsx";
import { TEMPLATES, buildContent } from "@/lib/lawyerDraftTemplates.js";
import { MODES, quickActionsFor, modeFor, proposalToHtml, tidyFullDraft, findPlaceholders, draftTitle } from "@/lib/draftAssist.js";
import { PROVINCES, NEUTRAL, provinceLabel, coverageNote } from "@/lib/jurisdictions.js";
import {
    NO_CASE, bindingForNewDocument, pendingBindingForDraft, bindingForDraft,
    caseActionsBlocked, boundCaseId,
} from "@/lib/draftCaseBinding.js";
import { verificationView } from "@/lib/draftVerification.js";

// ============================================================
// EDITOR LOOK (2026-10-09) — the approved drafting-editor design, on the
// Legal Drafting palette (draftingTheme.js). Scoped by [data-drafter-editor].
// ============================================================
export const EDITOR_CSS = `[data-drafter-editor]{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;--top-h:72px;--tools-h:72px;background:var(--bg);color:var(--ink);font:15px/1.5 "Hanken Grotesk",system-ui,sans-serif;-webkit-font-smoothing:antialiased;--stage:rgba(0,0,0,.16)}
[data-drafter-editor][data-mode="light"]{--stage:#E6E4EA}
[data-drafter-editor] *{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:var(--line-strong) transparent}
[data-drafter-editor] ::-webkit-scrollbar{width:8px;height:6px}
[data-drafter-editor] ::-webkit-scrollbar-track{background:transparent}
[data-drafter-editor] ::-webkit-scrollbar-thumb{background:var(--line-strong);border-radius:6px}
[data-drafter-editor] button,[data-drafter-editor] select,[data-drafter-editor] textarea{font:inherit;color:inherit}
[data-drafter-editor] :focus-visible{outline:2px solid var(--focus);outline-offset:2px}
[data-drafter-editor] .de-top{position:sticky;top:0;z-index:8;min-height:var(--top-h);background:var(--bg);box-shadow:0 2px 0 var(--bg);display:flex;align-items:center;gap:14px;padding:14px 26px;flex-wrap:wrap}
[data-drafter-editor] .de-back{width:44px;height:44px;flex:none;border-radius:12px;border:1px solid transparent;background:transparent;color:var(--ink);display:grid;place-items:center;cursor:pointer}
[data-drafter-editor] .de-back:hover{background:var(--hover-tint);border-color:var(--hover-line);color:var(--hover-ink)}
[data-drafter-editor] .de-title{min-width:0;flex:1}
[data-drafter-editor] .de-title h1{margin:0;font:600 19px/1.25 "Literata",Georgia,serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-drafter-editor] .de-meta{display:flex;gap:8px;align-items:center;font-size:12.5px;color:var(--muted);flex-wrap:wrap}
[data-drafter-editor] .de-cat{font-weight:600;color:var(--brand-text)}
[data-drafter-editor] .de-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-left:auto}
[data-drafter-editor] .de-btn{display:inline-flex;align-items:center;gap:7px;height:40px;padding:0 15px;border-radius:10px;border:1px solid var(--line-strong);background:var(--surface);font-weight:600;font-size:13.5px;white-space:nowrap;cursor:pointer}
[data-drafter-editor] .de-btn:hover:not(:disabled){border-color:var(--hover-line);background:var(--hover-tint);color:var(--hover-ink)}
[data-drafter-editor] .de-btn:disabled{opacity:.55;cursor:not-allowed}
[data-drafter-editor] .de-btn.primary{background:var(--brand-solid);border-color:transparent;color:var(--on-brand)}
[data-drafter-editor] .de-btn.primary:hover:not(:disabled){background:var(--brand-solid-hover);color:var(--on-brand)}
[data-drafter-editor] .de-note{font-size:12.5px;font-weight:600;padding:5px 11px;border-radius:999px;white-space:nowrap}
[data-drafter-editor] .de-note.ok{background:var(--brand-soft);color:var(--brand-text)}
[data-drafter-editor] .de-note.bad{background:var(--danger-soft);color:var(--danger)}
[data-drafter-editor] .de-drop{position:relative;flex:none}
[data-drafter-editor] .de-case{display:flex;align-items:center;gap:8px;height:38px;max-width:260px;padding:0 11px 0 4px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font:inherit;cursor:pointer;text-align:left;transition:border-color .15s,background .15s}
[data-drafter-editor] .de-case:hover,[data-drafter-editor] .de-case[aria-expanded="true"]{border-color:var(--hover-line);background:var(--hover-tint)}
[data-drafter-editor] .de-case .ic{width:30px;height:30px;flex:none;display:grid;place-items:center;border-radius:50%;background:var(--brand-soft);color:var(--brand-text)}
[data-drafter-editor] .de-case[data-case-binding="unavailable"]{border-color:color-mix(in srgb,var(--danger) 55%,transparent)}
[data-drafter-editor] .de-case[data-case-binding="unavailable"] .ic{background:var(--danger-soft);color:var(--danger)}
[data-drafter-editor] .de-case b{display:block;font-size:12.5px;font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-drafter-editor] .de-case small{display:block;font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-drafter-editor] .de-pop{position:absolute;top:calc(100% + 8px);right:0;z-index:60;width:min(380px,90vw);max-height:60vh;overflow-y:auto;padding:8px;border-radius:16px;border:1px solid var(--line-strong);background:var(--surface);box-shadow:0 24px 48px -18px rgba(0,0,0,.8);scrollbar-width:thin}
[data-drafter-editor] .de-pop[hidden]{display:none}
[data-drafter-editor] .de-pop h3{margin:4px 8px 8px;font:600 15px/1.2 Literata,Georgia,serif}
[data-drafter-editor] .de-opt{display:flex;flex-direction:column;align-items:flex-start;gap:1px;width:100%;padding:8px 10px;border:0;border-radius:10px;background:transparent;color:var(--ink);font:inherit;font-size:13px;text-align:left;cursor:pointer}
[data-drafter-editor] .de-opt small{font-size:11.5px;color:var(--muted)}
[data-drafter-editor] .de-opt:hover{background:var(--hover-tint)}
[data-drafter-editor] .de-opt[aria-selected="true"]{background:var(--brand-soft);color:var(--brand-text);font-weight:650}
[data-drafter-editor] .de-save{display:flex}
/* A pill, like the case button beside it. */
[data-drafter-editor] .de-save .de-btn{height:38px;font-size:13px}
[data-drafter-editor] .de-save .de-save-main{border-radius:999px 0 0 999px;padding:0 14px 0 16px}
[data-drafter-editor] .de-save .de-save-more{width:36px;padding:0;justify-content:center;border-radius:0 999px 999px 0;border-left:1px solid rgba(4,33,42,.22);width:36px;padding-right:3px}
[data-drafter-editor] .de-save .de-save-more[aria-expanded="true"] svg{transform:rotate(180deg)}
[data-drafter-editor] .de-save-menu{width:min(330px,90vw)}
[data-drafter-editor] .de-opt:disabled{opacity:.5;cursor:not-allowed}
[data-drafter-editor] .de-sep-h{height:1px;margin:6px 4px;background:var(--line)}
[data-drafter-editor] .de-acct{display:flex;align-items:center;gap:10px;height:46px;padding:0 14px 0 6px;border-radius:999px;border:1px solid var(--line);background:var(--surface);max-width:250px}
[data-drafter-editor] .de-acct b{display:block;font-size:13px;font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-drafter-editor] .de-acct small{font-size:11.5px;color:var(--muted)}
[data-drafter-editor] .de-avatar{width:34px;height:34px;flex:none;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;background:#5B7BE0;color:#fff}
/* Edge to edge (2026-10-11): no strip of page colour between the sidebar and the stage. */
[data-drafter-editor] .de-stage{flex:1;min-height:0;margin:0;border-radius:24px 24px 0 0;background:var(--stage);display:flex;flex-direction:column;padding:0 18px 6px}
[data-drafter-editor] .de-tools{position:sticky;top:var(--top-h);z-index:7;padding-top:8px;margin:0 -18px;padding-inline:18px;border-radius:24px 24px 0 0;background:linear-gradient(var(--stage),var(--stage)) top/100% 8px no-repeat,linear-gradient(var(--bg),var(--bg)) top/100% 8px no-repeat}
[data-drafter-editor] .de-toolbar{display:flex;align-items:center;gap:2px;padding:6px 8px;border-radius:16px;border:1px solid var(--line);background:var(--surface);overflow-x:auto;scrollbar-width:none;box-shadow:var(--shadow-rest)}
/* Scrolls sideways when narrow, with no visible scrollbar. */
[data-drafter-editor] .de-toolbar::-webkit-scrollbar{display:none}
[data-drafter-editor] .de-tb{height:34px;min-width:34px;padding:0 6px;border-radius:9px;border:1px solid transparent;background:transparent;color:var(--muted);display:grid;place-items:center;cursor:pointer;font-weight:700;font-size:15px;flex:none}
[data-drafter-editor] .de-tb:hover{background:var(--hover-tint);color:var(--hover-ink)}
[data-drafter-editor] .de-tb[aria-pressed="true"]{background:var(--teal);color:var(--on-teal)}
[data-drafter-editor] .de-sep{width:1px;height:22px;background:var(--line-strong);margin:0 4px;flex:none}
[data-drafter-editor] .de-select{height:34px;padding:0 8px;border-radius:9px;border:1px solid var(--line);background:var(--input);font-size:13px;flex:none;cursor:pointer}
[data-drafter-editor] .de-select:hover{border-color:var(--hover-line)}
/* Two columns of one height that fill the screen (2026-10-11): the page scrolls
   inside its own column, so its top and bottom always line up with the assistant's. */
[data-drafter-editor] .de-split{display:flex;gap:16px;margin-top:16px;align-items:stretch;flex:1;min-height:0}
/* The page sits straight on the stage's grey (2026-10-11): no card around it. */
[data-drafter-editor] .de-doc{flex:1;min-width:0;display:flex;flex-direction:column}
[data-drafter-editor] .de-strips{flex:none;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line)}
[data-drafter-editor] .de-strips > div{padding:7px 20px}
[data-drafter-editor] .de-strips > div + div{border-top:1px solid var(--line)}
[data-drafter-editor] .de-doc{min-height:0}
[data-drafter-editor] .de-scroll{flex:1;min-height:0;overflow-y:auto;padding:0 6px 0 0;border-radius:6px}
[data-drafter-editor] .de-scroll::-webkit-scrollbar{width:6px}
[data-drafter-editor] .de-scroll::-webkit-scrollbar-thumb{border-radius:6px;background:color-mix(in srgb,var(--ink) 22%,transparent)}
[data-drafter-editor] .de-scroll::-webkit-scrollbar-track{background:transparent}
[data-drafter-editor] .de-ph-btn{display:inline-flex;align-items:center;gap:7px;height:34px;padding:0 10px 0 12px;margin-left:4px;border-radius:10px;border:1px dashed var(--brand-text);background:var(--brand-soft);color:var(--brand-text);font:inherit;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap;flex:none}
[data-drafter-editor] .de-ph-btn b{min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:#e8b84b;color:#1d1a12;font-size:11.5px;display:grid;place-items:center}
[data-drafter-editor] .de-ph-btn[aria-expanded=true]{border-style:solid}
[data-drafter-editor] .de-assist.big{position:fixed;top:0;right:0;bottom:0;width:min(520px,100vw);z-index:60;border-radius:0;border-width:0 0 0 1px;border-color:var(--line-strong);box-shadow:-18px 0 50px -20px rgba(0,0,0,.6);animation:deSlide .18s ease}
[data-drafter-editor] .de-scrim{position:fixed;inset:0;z-index:59;background:rgba(4,12,14,.45);animation:deFade .18s ease}
@keyframes deSlide{from{transform:translateX(24px);opacity:.5}to{transform:none;opacity:1}}
@keyframes deFade{from{opacity:0}to{opacity:1}}
[data-drafter-editor] .de-assist-head{display:flex;align-items:center;gap:10px}
[data-drafter-editor] .de-big-btn{margin-left:auto;width:32px;height:32px;border-radius:9px;border:none;background:transparent;color:var(--muted);cursor:pointer;display:grid;place-items:center;flex:none}
[data-drafter-editor] .de-big-btn:hover{background:var(--chip-n);color:var(--ink)}
[data-drafter-editor] .de-fill-head .de-big-btn{margin-left:auto}
[data-drafter-editor] .de-fill-head .de-big-btn + .de-fill-x{margin-left:0}
[data-drafter-editor] .de-fill-head{display:flex;align-items:center;gap:12px;padding:14px 16px;background:var(--surface-2);border-bottom:1px solid var(--line)}
[data-drafter-editor] .de-fill-ic{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:var(--brand-soft);color:var(--brand-text);flex:none}
[data-drafter-editor] .de-fill-head b{display:block;font-size:16px}
[data-drafter-editor] .de-fill-head small{font-size:12.5px;color:var(--muted)}
[data-drafter-editor] .de-fill-x{margin-left:auto;width:32px;height:32px;border-radius:9px;border:none;background:transparent;color:var(--muted);cursor:pointer;font-size:16px}
[data-drafter-editor] .de-fill-x:hover{background:var(--chip-n);color:var(--ink)}
[data-drafter-editor] .de-fill-bar{height:5px;margin:12px 16px 4px;border-radius:999px;background:var(--line);overflow:hidden}
[data-drafter-editor] .de-fill-bar i{display:block;height:100%;background:linear-gradient(90deg,#1c9c66,#40f0dc);transition:width .2s}
[data-drafter-editor] .de-fill-tabs{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;border-bottom:1px solid var(--line)}
[data-drafter-editor] .de-fill-tabs div{display:inline-flex;padding:3px;border-radius:12px;border:1px solid var(--line);gap:2px}
[data-drafter-editor] .de-fill-tabs button{height:30px;padding:0 12px;border-radius:9px;border:none;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:700;cursor:pointer}
[data-drafter-editor] .de-fill-tabs button[aria-pressed=true]{background:var(--chip-n);color:var(--ink)}
[data-drafter-editor] .de-fill-tabs span{font-size:12.5px;font-weight:700;color:#e8b84b}
[data-drafter-editor] .de-fill-list{flex:1;min-height:0;overflow-y:auto;padding:8px 12px;display:flex;flex-direction:column;gap:2px}
[data-drafter-editor] .de-fill-row{padding:7px 10px;border-radius:12px;border:1px solid transparent}
[data-drafter-editor] .de-fill-row:focus-within{border-color:var(--line-strong);background:var(--surface-2)}
[data-drafter-editor] .de-fill-row header{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:13.5px;font-weight:700;color:var(--ink)}
[data-drafter-editor] .de-fill-row header i{width:9px;height:9px;border-radius:50%;border:2px solid #e8b84b;flex:none}
[data-drafter-editor] .de-fill-row.done header i{border-color:#3ec99a;background:#3ec99a}
[data-drafter-editor] .de-fill-row header em{margin-left:auto;font-style:normal;font-size:12px;color:#e8b84b}
[data-drafter-editor] .de-fill-row.done header em{color:#3ec99a}
[data-drafter-editor] .de-fill-row header button{border:none;background:transparent;color:var(--brand-text);font:inherit;font-size:12px;font-weight:700;cursor:pointer;padding:0}
[data-drafter-editor] .de-fill-row textarea{display:block;width:100%;box-sizing:border-box;height:38px;min-height:38px;max-height:120px;padding:8px 11px;border-radius:10px;border:1px solid var(--line-strong);background:var(--input);color:var(--ink);font:inherit;font-size:13.5px;line-height:1.45;resize:none;overflow-y:auto}
[data-drafter-editor] .de-fill-row textarea:focus{outline:none;border-color:var(--brand-text)}
[data-drafter-editor] .de-fill-foot{padding:12px 14px 14px;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:8px}
[data-drafter-editor] .de-fill-go{display:flex;align-items:center;justify-content:center;gap:9px;width:100%;height:46px;border-radius:12px;border:none;background:linear-gradient(135deg,#12897f 0%,#1c9c66 55%,#1f8f9c 100%);color:#fff;font:inherit;font-size:14.5px;font-weight:700;cursor:pointer;box-shadow:0 8px 22px -12px rgba(28,156,102,.7);transition:filter .15s}
[data-drafter-editor] .de-fill-go:hover:not(:disabled){filter:brightness(1.08)}
[data-drafter-editor] .de-fill-go:disabled{opacity:.72;cursor:not-allowed;box-shadow:none}
[data-drafter-editor] .de-fill-foot small{font-size:12px;color:var(--muted);text-align:center;line-height:1.45}
[data-drafter-editor] .de-paper:empty::before{content:attr(data-empty);color:#8a9aa0;font-style:italic;pointer-events:none}
[data-drafter-editor] .de-paper{max-width:820px;margin:0 auto;min-height:640px;background:var(--paper);color:var(--paper-ink);border-radius:6px;padding:64px 76px;line-height:1.95;font-size:15px;outline:none;white-space:pre-wrap;box-shadow:0 18px 40px -22px rgba(0,0,0,.65)}
/* Tailwind's preflight strips list markers and paragraph margins; a pleading's numbered "That ..."
   paragraphs and its prayer list need them back (template library, 2026-10-14). Scoped to the paper. */
[data-drafter-editor] .de-paper ol{list-style:decimal;padding-left:2.1em;margin:.15em 0 .6em}
[data-drafter-editor] .de-paper ul{list-style:disc;padding-left:2.1em;margin:.15em 0 .6em}
[data-drafter-editor] .de-paper li{margin:.1em 0 .35em;padding-left:.25em}
[data-drafter-editor] .de-paper li > ul,[data-drafter-editor] .de-paper li > ol{margin:.2em 0 .2em}
[data-drafter-editor] .de-paper p{margin:0 0 .45em}
[data-drafter-editor] .de-assist{width:400px;flex:none;display:flex;flex-direction:column;border-radius:18px;border:1px solid var(--line);background:var(--surface);overflow:hidden}
[data-drafter-editor] .de-assist-head{padding:14px 22px;background:var(--surface-2);border-bottom:1px solid var(--line)}
[data-drafter-editor] .de-assist-head b{display:block;font-size:17px}
[data-drafter-editor] .de-assist-head span{font-size:13.5px;color:var(--muted)}
[data-drafter-editor] .de-assist-body{flex:1;min-height:0;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px}
/* Just the greeting now (2026-10-11): no second title or icon card around it. */
[data-drafter-editor] .de-hello{padding:0}
[data-drafter-editor] .de-hello-top{display:flex;gap:14px;align-items:center}
[data-drafter-editor] .de-hello-ic{width:58px;height:58px;flex:none;border-radius:14px;background:var(--brand-solid);color:var(--on-brand);display:grid;place-items:center}
[data-drafter-editor] .de-hello-top b{display:block;font-size:19px;line-height:1.2}
[data-drafter-editor] .de-hello-top span{font-size:14px;color:var(--muted)}
[data-drafter-editor] .de-greet{margin-top:0;border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--surface)}
[data-drafter-editor] .de-greet b{font-size:16px}
[data-drafter-editor] .de-greet b em{font-style:normal;color:var(--brand-text)}
[data-drafter-editor] .de-greet p{margin:4px 0 0;font-size:13px;color:var(--muted);line-height:1.5}
[data-drafter-editor] .de-label{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);font-weight:600}
/* Quick actions as small pills that wrap (2026-10-11). */
[data-drafter-editor] .de-quick{display:flex;flex-wrap:wrap;gap:6px}
/* The panel stays put; whatever is inside it -- the opening note or the
   conversation -- scrolls within it, on a slim bar. */
[data-drafter-editor] .de-assist-body::-webkit-scrollbar{width:6px}
[data-drafter-editor] .de-assist-body::-webkit-scrollbar-thumb{border-radius:6px;background:color-mix(in srgb,var(--ink) 22%,transparent)}
[data-drafter-editor] .de-assist-body::-webkit-scrollbar-track{background:transparent}
[data-drafter-editor] .de-quick button{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--muted);text-align:left;font-size:13px;cursor:pointer}
[data-drafter-editor] .de-quick button:hover{border-color:var(--hover-line);background:var(--hover-tint);color:var(--hover-ink)}
/* Draft Assistant proposals (2026-10-14): a reply is shown, never applied by itself. */
[data-drafter-editor] .de-prop{display:flex;flex-direction:column;gap:8px;max-width:100%}
[data-drafter-editor] .de-prop-kind{font-size:11.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
[data-drafter-editor] .de-prop-text{white-space:pre-wrap;max-height:260px;overflow-y:auto;padding:10px 12px;border-radius:10px;background:var(--surface-2);border:1px solid var(--line);font-family:Georgia,'Times New Roman',serif;font-size:13.5px;line-height:1.6;color:var(--ink)}
[data-drafter-editor] .de-prop-actions{display:flex;flex-wrap:wrap;gap:6px}
[data-drafter-editor] .de-prop-actions button{padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--ink);font-size:12.5px;font-weight:600;cursor:pointer}
[data-drafter-editor] .de-prop-actions button.primary{background:var(--brand,#2bd4a8);border-color:transparent;color:#05261d}
[data-drafter-editor] .de-prop-actions button:hover{border-color:var(--hover-line)}
[data-drafter-editor] .de-prop-done{font-size:12.5px;font-weight:700;color:var(--brand-text,#2bd4a8)}
[data-drafter-editor] .de-guard{font-size:12.5px;line-height:1.5;padding:8px 10px;border-radius:8px;border:1px solid var(--warn-line,#d9a43a);background:var(--warn-tint,rgba(217,164,58,.10));color:var(--ink)}
[data-drafter-editor] .de-guard ul{margin:4px 0 0;padding-left:18px;list-style:disc}
[data-drafter-editor] .de-check-scope{font-size:11.5px;line-height:1.45;color:var(--muted)}
[data-drafter-editor] .de-prop-actions button:disabled{opacity:.5;cursor:not-allowed}
[data-drafter-editor] .de-retry{margin-top:8px;padding:5px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--ink);font-size:12.5px;font-weight:600;cursor:pointer}
[data-drafter-editor] .de-juris{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:0 0 8px;font-size:12.5px;color:var(--muted)}
[data-drafter-editor] .de-juris select{padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--ink);font-size:12.5px}
[data-drafter-editor] .de-juris small{flex-basis:100%;font-size:11.5px}
[data-drafter-editor] .de-modes{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 8px}
[data-drafter-editor] .de-modes button{padding:4px 10px;border-radius:999px;border:1px solid var(--line);background:transparent;color:var(--muted);font-size:12px;cursor:pointer}
[data-drafter-editor] .de-modes button[aria-pressed="true"]{background:var(--hover-tint);border-color:var(--hover-line);color:var(--ink);font-weight:700}
[data-drafter-editor] .de-modes button:disabled{opacity:.45;cursor:not-allowed}
[data-drafter-editor] .de-selchip{display:flex;align-items:center;gap:8px;margin:0 0 8px;padding:6px 10px;border-radius:8px;background:var(--surface-2);border:1px dashed var(--line-strong,var(--line));font-size:12px;color:var(--muted)}
[data-drafter-editor] .de-selchip span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
[data-drafter-editor] .de-selchip button{border:none;background:none;color:var(--muted);font-size:16px;cursor:pointer;line-height:1}
[data-drafter-editor] .de-msg{max-width:92%;padding:10px 13px;font-size:13.5px;line-height:1.6;white-space:pre-wrap}
[data-drafter-editor] .de-msg.user{align-self:flex-end;border-radius:14px 14px 4px 14px;background:var(--teal);color:var(--on-teal)}
[data-drafter-editor] .de-msg.ai{align-self:flex-start;border-radius:4px 14px 14px 14px;background:var(--surface-2);border:1px solid var(--line)}
[data-drafter-editor] .de-dots{display:flex;gap:5px;padding:12px 16px}
[data-drafter-editor] .de-dots i{width:6px;height:6px;border-radius:50%;background:var(--brand-text);animation:pulse 1.2s ease infinite}
[data-drafter-editor] .de-compose{flex:none;padding:14px 16px;border-top:1px solid var(--line)}
[data-drafter-editor] .de-compose-box{border:1px solid var(--line);border-radius:18px;background:var(--surface-2);overflow:hidden}
[data-drafter-editor] .de-compose-box:focus-within{border-color:var(--focus);box-shadow:0 0 0 3px var(--brand-soft)}
[data-drafter-editor] .de-compose textarea{width:100%;border:0;outline:none;background:transparent;resize:none;padding:12px 16px 2px;font-size:14px;line-height:1.5}
[data-drafter-editor] .de-compose textarea::placeholder{color:var(--faint)}
[data-drafter-editor] .de-compose-row{display:flex;justify-content:space-between;align-items:center;padding:0 8px 8px 16px;gap:10px}
[data-drafter-editor] .de-hint{font-size:11.5px;color:var(--faint)}
[data-drafter-editor] .de-foot{font-size:11.5px;color:var(--faint);text-align:center;margin-top:9px}
[data-drafter-editor] .de-send{overflow:hidden}
/* Send: a small round arrow, like a chat app's (2026-10-11). */
[data-drafter-editor] .de-send-ic{width:34px;height:34px;flex:none;display:grid;place-items:center;border:0;border-radius:50%;background:var(--brand-solid);color:var(--on-brand);cursor:pointer;transition:transform .15s,opacity .15s}
[data-drafter-editor] .de-send-ic:hover:not(:disabled){transform:translateY(-1px)}
[data-drafter-editor] .de-send-ic:disabled{opacity:.35;cursor:default}
[data-drafter-editor] .de-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
[data-drafter-editor] .de-send:hover:not(:disabled) svg{animation:deFly .75s cubic-bezier(.5,0,.3,1)}
[data-drafter-editor] .de-tb svg{transition:transform .3s cubic-bezier(.34,1.56,.64,1)}
[data-drafter-editor] .de-tb:hover svg{transform:translateY(-1px) scale(1.12)}
[data-drafter-editor] .de-back svg{transition:transform .3s cubic-bezier(.34,1.56,.64,1)}
[data-drafter-editor] .de-back:hover svg{transform:translateX(-3px)}
@keyframes deFly{0%{transform:translate(0,0)}40%{transform:translate(16px,-16px);opacity:0}41%{transform:translate(-16px,16px);opacity:0}100%{transform:translate(0,0);opacity:1}}
@media (prefers-reduced-motion:reduce){[data-drafter-editor] *{transition:none!important;animation:none!important}}`;

/* One toolbar button: an icon with its name for screen readers and hover. */
function TB({ label, active, onClick, children, style }) {
    return (
        <button type="button" className="de-tb" title={label} aria-label={label}
            aria-pressed={active === undefined ? undefined : Boolean(active)}
            onMouseDown={e => e.preventDefault()} onClick={onClick} style={style}>
            {children}
        </button>
    );
}

// STAGE 1 — the template home lives in DraftingHome.jsx (2026-10-09).

// ============================================================
// STAGE 2 — EDITOR
// ============================================================

/* THE CITATION CHECK, ONLY WHEN IT MATTERS (2026-10-11). The always-on strip
 * was noise. What stays is the one finding a lawyer must not miss: an
 * authority the check could not find, or one that is repealed -- the kind of
 * wrong citation that otherwise reaches a filed document. Shown for the draft
 * as last saved; once the text changes the finding is about other words, so
 * it goes until the next save checks again. Nothing is shown for a clean or
 * an unchecked draft: no finding is not a pass, and is not claimed as one. */
function CitationWarning({ draftCheck, stale }) {
    const d = verificationView(draftCheck);
    if (!d || stale || d.tone !== "danger") return null;
    return (
        <span className="de-note bad" role="alert" data-citation-warning title={d.detail}>
            ⚠ {d.headline}
        </span>
    );
}

/* Asked again when the check withheld the whole reply: a paragraph with no
   authority in it, for the lawyer to complete. */
const PLACEHOLDER_ASK = "Do not cite any provision or case. Where the law would be cited, write [PROVISION] for me to fill in.";

/* What the server's legal-authority check took out of an AI reply, and why
   (2026-10-14). Removed text never reaches the draft. A reply whose check did
   not run is never a proposal at all (sendToAI). */
function GuardNote({ withheld = [] }) {
    if (!withheld.length) return null;
    return (
        <div className="de-guard" data-guard-withheld>
            <b>Withheld by the legal check ({withheld.length}):</b>
            <ul>{withheld.map((w, k) => (
                <li key={k}><q>{w.text}</q> — {(w.reasons || []).join(" ")}</li>
            ))}</ul>
        </div>
    );
}

/* What the check covered -- and what it did not. It looks at the statute
   provisions the reply cites and at provincial Acts outside the chosen
   jurisdiction; it is not a review of the facts, the remedy or case law. */
function CheckScope({ check, onChooseJurisdiction }) {
    if (!check) return null;
    // Counts describe THIS proposal's final text (draft_guard): a provision
    // cited only in a withheld sentence is in none of them, and "found and
    // consistent" is never phrased as "legally correct".
    const supported = check.supported || [];
    const missing = check.notChecked || [];
    const n = supported.length;
    const j = check.jurisdiction;
    const where = !j ? "" : j.basis === "neutral" ? "Jurisdiction-neutral (federal law only)"
        : `${provinceLabel(j.province) || j.province}${j.basis === "case" ? " (from the case)" : ""}`;
    const c = check.clarify;
    return (
        <div className="de-check-scope" data-check-scope>
            <span data-check-supported={n}>
                {n ? `Legal check: ${n} cited provision${n === 1 ? "" : "s"} found in the library and consistent with ${n === 1 ? "its" : "their"} subject (${supported.join(", ")}).`
                    : missing.length ? "Legal check: none of the cited provisions could be checked against the library."
                    : "Legal check: no statute provision cited in this proposal."}
            </span>
            {" "}This does not confirm the claim is right; facts, remedies and case law are not checked.{where ? ` ${where}.` : ""}
            {missing.length > 0 && (
                // Each entry carries its reason (not in our copy, several provisions
                // under one number, subject does not match, personal law unknown).
                <div data-check-unverified>Not verified — check these yourself: {missing.join("; ")}.</div>
            )}
            {c && (
                <div className="de-guard" data-clarify={c.topic}>
                    {c.message}{c.placeholder ? "" : " This proposal has no placeholder for it — add one before using it."}
                    {onChooseJurisdiction && (
                        <> <button type="button" className="de-retry" onClick={onChooseJurisdiction}>Choose jurisdiction</button></>
                    )}
                </div>
            )}
        </div>
    );
}

const _norm = (s) => String(s || "").replace(/\s+/g, " ").trim();

function StageEditor({ tmpl, binding = NO_CASE, draft, onBack, t, cases = [], onRebind }) {
    // The case this document is bound to — fixed when the editor opened, never
    // the page selector's current value. See lib/draftCaseBinding.js.
    const caseObj = binding.caseObj;
    const caseId = boundCaseId(binding);
    const { setPage } = useCase();
    const caseBlocked = caseActionsBlocked(binding);
    const [caseOpen, setCaseOpen] = useState(false);
    const [saveOpen, setSaveOpen] = useState(false);
    const [justPublished, setJustPublished] = useState(false);
    const caseRef = useRef(null), saveRef = useRef(null);
    useEffect(() => {
        if (!caseOpen && !saveOpen) return undefined;
        const onDown = e => {
            if (!caseRef.current?.contains(e.target)) setCaseOpen(false);
            if (!saveRef.current?.contains(e.target)) setSaveOpen(false);
        };
        const onKey = e => { if (e.key === "Escape") { setCaseOpen(false); setSaveOpen(false); } };
        document.addEventListener("mousedown", onDown);
        window.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("mousedown", onDown); window.removeEventListener("keydown", onKey); };
    }, [caseOpen, saveOpen]);
    // The lawyer's own choice of case -- the only way the binding changes.
    const pickCase = (c) => { setCaseOpen(false); onRebind?.(bindingForNewDocument(c)); };
    // A saved draft stores editor HTML; a fresh template is plain text
    // "Draft with AI" (2026-10-19) starts on an EMPTY page: the AI writes the
    // whole draft from the lawyer's description, as on the client side.
    const aiFirst = Boolean(tmpl?.aiFirst && !draft);
    const initialHtml = draft ? draft.content : aiFirst ? "" : buildContent(tmpl, caseObj).replace(/\n/g, "<br>");
    // ONE object for the editor's lifetime. React 19 re-applies
    // dangerouslySetInnerHTML whenever the prop OBJECT changes, and an inline
    // `{{ __html }}` is a new object every render: any re-render (a word-count
    // change while typing, an AI reply arriving) reset the paper to the
    // template and threw away the lawyer's work. The content is the DOM's from
    // mount on; opening another template or draft mounts a new editor.
    const [paperHtml] = useState(() => ({ __html: initialHtml }));
    const [aiMessages, setAiMessages] = useState([]);
    const [aiInput, setAiInput] = useState("");
    const [aiLoading, setAiLoading] = useState(false);
    // Draft Assistant (2026-10-14): what the reply should be (null = decided by
    // whether text is selected), the lawyer's last cursor/selection INSIDE the
    // draft (kept while focus is in the panel), and the selected text itself.
    const [assistMode, setAssistMode] = useState(aiFirst ? "full" : null);
    // The document's title: a saved draft's, else the AI draft's own heading.
    const [docTitle, setDocTitle] = useState(draft?.title || (aiFirst ? "AI draft" : tmpl.name));
    // Blanks still to fill ([Address], ___), read from the live text.
    const [fields, setFields] = useState([]);
    // The "Fill placeholders" panel (2026-10-20) takes the Draft Assistant's
    // place on the right while it is open.
    const [fieldsOpen, setFieldsOpen] = useState(false);
    const [fillValues, setFillValues] = useState({});
    const [fillStart, setFillStart] = useState([]);      // the labels when the panel opened
    const [fillTab, setFillTab] = useState("all");
    // Either right-hand panel can be expanded to the full height (2026-10-20),
    // over the page, like the chat panel. Esc or a click on the page shrinks it.
    const [panelBig, setPanelBig] = useState(false);
    useEffect(() => {
        if (!panelBig) return undefined;
        const esc = (e) => { if (e.key === "Escape") { e.stopPropagation(); setPanelBig(false); } };
        window.addEventListener("keydown", esc, true);
        return () => window.removeEventListener("keydown", esc, true);
    }, [panelBig]);
    const bigBtn = (
        <button type="button" className="de-big-btn" data-panel-expand aria-pressed={panelBig}
            aria-label={panelBig ? "Shrink the panel" : "Expand the panel to full height"}
            title={panelBig ? "Shrink (Esc)" : "Expand to full height"} onClick={() => setPanelBig(b => !b)}>
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                {panelBig ? <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" /> : <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />}
            </svg>
        </button>
    );
    const openFill = () => {
        setFillStart(findPlaceholders(editorRef.current?.innerText || "").map(f => f.label).filter(l => l !== "___"));
        setFillTab("all");
        setFieldsOpen(true);
    };
    // "Edit" in the template preview opens straight onto the Fill panel.
    useEffect(() => {
        if (tmpl?.openFill && !draft && findPlaceholders(editorRef.current?.innerText || "").length) openFill();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    useEffect(() => {
        if (!fieldsOpen) return undefined;
        const esc = (e) => { if (e.key === "Escape") setFieldsOpen(false); };
        window.addEventListener("keydown", esc);
        return () => window.removeEventListener("keydown", esc);
    }, [fieldsOpen]);
    const fieldCursor = useRef({});
    const [selectedText, setSelectedText] = useState("");
    const savedRangeRef = useRef(null);
    const [draftId, setDraftId] = useState(draft?.id || null);
    const [saving, setSaving] = useState(false);
    const [saveErr, setSaveErr] = useState("");
    const [saved, setSaved] = useState(false);
    const [fontSize, setFontSize] = useState("13");
    const [font, setFont] = useState("Default Font");
    const [wordCount, setWordCount] = useState(0);
    // Court-Urdu pleading generator
    const [urduOpen, setUrduOpen] = useState(false);
    const [urduText, setUrduText] = useState("");
    const [urduBusy, setUrduBusy] = useState(false);
    const [urduPdfBusy, setUrduPdfBusy] = useState(false);
    const [urduMeta, setUrduMeta] = useState({ court_ur: "", title_ur: "" });
    // One key for one pleading. Held in a ref so a re-render between a failed
    // download and the retry cannot lose it — losing it is what turns a retry
    // into a second document.
    //
    // Cleared when the TEXT changes, because a different translation is a
    // different pleading: reusing the key there would replay the old revision
    // and hand the lawyer a PDF of text they had already replaced.
    const urduKeyRef = useRef(null);
    const urduKeyedTextRef = useRef(null);
    const [urduIssue, setUrduIssue] = useState("");

    // Publishing the draft as a real document. Same key discipline as the
    // pleading: one key per intent, dropped when the CONTENT changes, because
    // republishing edited prose under the old key would return the old
    // revision and tell the lawyer their edits were filed when they were not.
    const [publishing, setPublishing] = useState(false);
    const [published, setPublished] = useState(null);   // {docId, revisionId, ...}
    const [publishIssue, setPublishIssue] = useState("");
    const publishKeyRef = useRef(null);
    const publishedHtmlRef = useRef(null);
    // The server's citation check over the text AS LAST SAVED — restored with a
    // reopened draft, replaced on every save, and stale from the first edit
    // after it. `editSeq` counts edits so a save that raced a keystroke is
    // still marked stale when its answer lands.
    const [savedCheck, setSavedCheck] = useState(draft?.verification ?? null);
    const [checkStale, setCheckStale] = useState(false);
    const editSeq = useRef(0);
    // Re-render on every edit: a pending rewrite's "Replace selected text" is
    // enabled only while its passage is still there, unchanged.
    const [, setEditTick] = useState(0);
    const markEdited = () => { editSeq.current += 1; setCheckStale(true); setEditTick(n => n + 1); };
    // The jurisdiction of a caseless draft, chosen by the lawyer before the
    // first request ("" = not yet). A case-bound draft uses the case's own.
    const [jurisdiction, setJurisdiction] = useState("");
    const editorRef = useRef(null);
    const aiEndRef = useRef(null);
    const aiInputRef = useRef(null);
    // "Draft with AI" from the template home opens here, ready to describe the facts.
    useEffect(() => { if (tmpl?.aiFirst) aiInputRef.current?.focus(); }, [tmpl]);

    const h = new Date().getHours();
    const greeting = h < 12 ? "Good Morning" : h < 17 ? "Good Afternoon" : "Good Evening";
    const { user } = useAuth();
    const userName = user?.full_name?.split(" ")[0] || "Counselor";

    // Follow the conversation once there is one. On an empty panel this would
    // scroll the assistant's introduction out of view.
    useEffect(() => {
        if (aiMessages.length || aiLoading) aiEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, [aiMessages, aiLoading]);
    useEffect(() => { setWordCount((editorRef.current?.innerText || "").trim().split(/\s+/).filter(Boolean).length); }, []);

    // Emit tag-based formatting (<b>, <font face>, align=) rather than inline
    // CSS. The server sanitises draft HTML against an allowlist that permits
    // those and drops `style` -- nh3 does not filter CSS, so a permitted style
    // attribute would still admit url(...) inside an otherwise clean draft.
    // Without this, browsers that default to styleWithCSS would emit
    // <span style="font-weight:bold"> and the lawyer's formatting would be
    // silently stripped on save.
    useEffect(() => {
        try { document.execCommand("styleWithCSS", false, false); } catch { /* not supported */ }
    }, []);

    const exec = (cmd, val = null) => { editorRef.current?.focus(); document.execCommand(cmd, false, val); };
    const queryState = (cmd) => document.queryCommandState(cmd);

    /* ── Draft Assistant: where a proposal goes ──────────────────────────
       The cursor or selection is remembered while the lawyer types a prompt
       in the panel (focus leaves the paper, and the browser forgets it). */
    const captureSelection = () => {
        const sel = window.getSelection?.();
        const ed = editorRef.current;
        if (!sel || !sel.rangeCount || !ed) return;
        const range = sel.getRangeAt(0);
        if (!ed.contains(range.commonAncestorContainer)) return;
        savedRangeRef.current = range.cloneRange();
        setSelectedText(sel.toString().trim());
    };
    const refreshFields = () => setFields(findPlaceholders(editorRef.current?.innerText || ""));
    useEffect(() => { refreshFields(); }, []);
    // Select the next occurrence of a blank in the paper, so the lawyer can type over it.
    const selectField = (label) => {
        const ed = editorRef.current;
        if (!ed) return;
        const re = label === "___" ? /_{3,}/g : new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g");
        const hits = [];
        const walker = document.createTreeWalker(ed, 4 /* NodeFilter.SHOW_TEXT */);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            re.lastIndex = 0;
            for (let m = re.exec(n.data); m; m = re.exec(n.data)) hits.push([n, m.index, m[0].length]);
        }
        if (!hits.length) { refreshFields(); return; }
        const i = ((fieldCursor.current[label] ?? -1) + 1) % hits.length;
        fieldCursor.current[label] = i;
        const [node, at, len] = hits[i];
        ed.focus();
        const r = document.createRange();
        r.setStart(node, at); r.setEnd(node, at + len);
        const sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(r);
        node.parentElement?.scrollIntoView?.({ block: "center", behavior: "smooth" });
        captureSelection();
    };
    // Write each value over every copy of its placeholder. Through
    // insertText, so Ctrl+Z takes it back; nothing is saved until Save Draft.
    const fillAll = () => {
        const ed = editorRef.current;
        if (!ed) return;
        const entries = Object.entries(fillValues).filter(([label, v]) => v.trim() && label !== "___");
        if (!entries.length) return;
        ed.focus();
        for (const [label, value] of entries) {
            const re = new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
            for (let guard = 0; guard < 200; guard++) {
                let hit = null;
                const walker = document.createTreeWalker(ed, 4 /* SHOW_TEXT */);
                for (let n = walker.nextNode(); n && !hit; n = walker.nextNode()) {
                    const m = re.exec(n.data);
                    if (m) hit = [n, m.index, m[0].length];
                }
                if (!hit) break;
                const r = document.createRange();
                r.setStart(hit[0], hit[1]); r.setEnd(hit[0], hit[1] + hit[2]);
                const sel = window.getSelection();
                sel.removeAllRanges(); sel.addRange(r);
                const before = hit[0].data;
                const ok = document.execCommand("insertText", false, value.trim());
                // Some editors report success without writing: then write directly.
                if (!ok || (hit[0].isConnected && hit[0].data === before)) { r.deleteContents(); r.insertNode(document.createTextNode(value.trim())); }
            }
        }
        setFillValues({});
        afterChange();
    };
    const afterChange = () => {
        refreshFields();
        markEdited();
        setWordCount((editorRef.current?.innerText || "").trim().split(/\s+/).filter(Boolean).length);
    };
    // Put `html` where `range` is (replacing what it covers), or at the end of
    // the draft. insertHTML keeps the browser's undo (Ctrl+Z) working.
    const placeHtml = (html, range, { newBlock = false } = {}) => {
        const ed = editorRef.current;
        if (!ed || !html) return false;
        ed.focus();
        const sel = window.getSelection();
        sel.removeAllRanges();
        if (range && ed.contains(range.commonAncestorContainer)) {
            sel.addRange(range);
        } else {
            const end = document.createRange();
            end.selectNodeContents(ed);
            end.collapse(false);
            sel.addRange(end);
        }
        // A new clause starts its own paragraph. Without this the browser merged
        // the first inserted block into the line the cursor was on ("Witness 2"
        // + "10. CONFIDENTIALITY" on one line, heading unbolded -- live check).
        if (newBlock) document.execCommand("insertParagraph", false, null);
        document.execCommand("insertHTML", false, html);
        afterChange();
        captureSelection();
        return true;
    };
    const chooseJurisdiction = () => document.getElementById("de-juris")?.focus();
    const markApplied = (i, how) => setAiMessages(prev => prev.map((m, k) => (k === i ? { ...m, applied: how } : m)));
    // The passage a rewrite was asked for, IF it is still in this editor and
    // still reads as it did: the range was saved before a slow request, and the
    // lawyer may have edited, deleted or replaced it since. A live Range follows
    // edits elsewhere; one inside the passage changes its text, and a removal
    // collapses it. null = do not replace anything.
    const rewriteTarget = (p) => {
        const ed = editorRef.current;
        const r = p?.range;
        if (!r || !ed || p.editor !== ed || !ed.isConnected || r.collapsed) return null;
        if (!ed.contains(r.startContainer) || !ed.contains(r.endContainer)) return null;
        return _norm(r.toString()) === _norm(p.original) ? r : null;
    };
    const applyProposal = (i, how) => {
        const msg = aiMessages[i];
        const p = msg?.proposal;
        if (!p) return;
        if (how === "insert") {
            const at = savedRangeRef.current ? savedRangeRef.current.cloneRange() : null;
            at?.collapse(false);                     // after the selection, never over it
            if (placeHtml(p.html, at, { newBlock: true })) markApplied(i, "Inserted into the draft");
        } else if (how === "replace-selection") {
            const target = rewriteTarget(p);
            if (!target) return;                     // stale: the button says why
            if (placeHtml(p.html, target.cloneRange())) markApplied(i, "Replaced the selected text");
        } else if (how === "replace-all") {
            if (!window.confirm("Replace the whole draft with this version? Its formatting is simplified; Undo (Ctrl+Z) restores the previous draft.")) return;
            const ed = editorRef.current;
            if (!ed) return;
            ed.focus();
            document.execCommand("selectAll", false, null);
            document.execCommand("insertHTML", false, p.html);
            afterChange();
            markApplied(i, "Replaced the whole draft");
        } else if (how === "copy") {
            navigator.clipboard?.writeText(p.text).then(() => markApplied(i, "Copied"), () => {});
        }
    };

    const handleSave = async () => {
        if (saving || caseBlocked) return;
        setSaving(true); setSaveErr("");
        const seqAtSave = editSeq.current;
        const { data, error } = await saveDocDraft({
            draft_id: draftId,
            title: docTitle,
            content: editorRef.current?.innerHTML || "",
            template_name: tmpl.name,
            template_icon: tmpl.icon,
            case_id: caseId,
        });
        setSaving(false);
        if (error) { setSaveErr(error.message || "Save failed"); setTimeout(() => setSaveErr(""), 4000); return; }
        setDraftId(data.id);
        setSavedCheck(data.verification ?? null);
        setCheckStale(editSeq.current !== seqAtSave);
        setSaved(true); setTimeout(() => setSaved(false), 2500);
    };

    /* Save this draft into the system as a document.
     *
     * "SAVE", NOT "FILE". Filing is what a court accepts, and nothing here goes
     * near a court — implying otherwise on a legal product is the kind of wrong
     * word a user acts on. What this does is keep a fixed, hashed copy the
     * system can name, check citations on, and reproduce identically.
     *
     * The .doc export below remains, and is still the right tool for handing a
     * file to someone who will edit it. They are not alternatives.
     */
    const publishAsDocument = async () => {
        if (publishing || caseBlocked) return;
        const bodyHtml = editorRef.current?.innerHTML || "";
        if (!(editorRef.current?.innerText || "").trim()) {
            setPublishIssue("There is nothing in the draft to save.");
            return;
        }

        setPublishing(true);
        setPublishIssue("");

        // Edited prose is a new document, not a retry of the old one.
        if (publishedHtmlRef.current !== bodyHtml) {
            publishKeyRef.current = null;
            publishedHtmlRef.current = bodyHtml;
        }
        publishKeyRef.current = publishKeyRef.current || idempotencyKey();

        const res = await publishDraftAsDocumentV2({
            title: docTitle,
            bodyHtml,
            authorName: user?.full_name || "",
            caseId,
        }, publishKeyRef.current);
        setPublishing(false);

        if (res.error) {
            setPublishIssue(res.status === 404 && res.code === "feature_disabled"
                // Not an error the lawyer caused, and not one they can act on.
                // The export below is what they have until the flag is on.
                ? "Saving a draft to Documents is not enabled yet — use Export."
                : (res.error.message || "Could not save the draft."));
            return;
        }
        setPublished(res);
        setJustPublished(true); setTimeout(() => setJustPublished(false), 3500);
    };

    const handleExport = () => {
        // Word-compatible download: HTML body wrapped in a Word-namespaced
        // document, saved as .doc — opens with formatting in MS Word.
        const body = editorRef.current?.innerHTML || "";
        const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word"><head><meta charset="utf-8"><title>${tmpl.name}</title></head><body style="font-family:Georgia,'Times New Roman',serif;line-height:1.9;">${body}</body></html>`;
        const blob = new Blob(["﻿", html], { type: "application/msword" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${docTitle.replace(/[^\w\s-]/g, "").trim() || "document"}.doc`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    const sendToAI = async (again = null) => {
        const q = again ? again.q : aiInput.trim();
        if (!q || aiLoading || caseBlocked) return;
        if (!caseId && !jurisdiction) return;        // chosen first: the control says so
        // What comes back, and for a rewrite, the exact passage it replaces.
        const selection = again ? again.selection : selectedText;
        const mode = again ? again.mode : modeFor({ chosen: assistMode, hasSelection: !!selection });
        const range = again ? again.range
            : (mode === "rewrite" && savedRangeRef.current ? savedRangeRef.current.cloneRange() : null);
        const target = { q, mode, selection, range };
        // A whole draft asked for on an EMPTY page goes straight onto it (there
        // is nothing to overwrite), as on the client side. Measured now, before
        // the reply: typing meanwhile makes it a proposal again.
        const pageWasEmpty = mode === "full" && !(editorRef.current?.innerText || "").trim();
        // Not a proposal: what went wrong, and a Retry of the same request.
        const failed = (text) => setAiMessages(prev => [...prev, { role: "assistant", text, retry: target }]);
        if (!again) setAiInput("");
        setAiMessages(prev => [...prev, { role: "user", text: q, mode }]);
        setAiLoading(true);
        try {
            const history = aiMessages.filter(m => !m.retry)
                .map(m => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
            let reply = "";
            // RAG-grounded: the backend retrieves real Pakistani law for this template
            // and instructs the model to cite only genuine sections/precedents.
            let verif = null;
            // The server checks the finished text against the law it can see
            // (omitted / absent / mispaired sections) and sends what survives.
            let guard = null;
            await aiDraftStream(
                {
                    instruction: q,
                    document: editorRef.current?.innerText || "",
                    // An AI-first draft has no template: "legal document" on the server.
                    template: aiFirst ? "" : tmpl.name,
                    // CASE-BOUND when a case is selected: the server authorises it
                    // and derives jurisdiction from it (so a Punjab matter no
                    // longer retrieves federal law). case_type is the fallback.
                    case_id: caseId,
                    case_type: templateCaseType(tmpl.name),
                    // Caseless: the lawyer's choice (NEUTRAL = jurisdiction-neutral).
                    // Case-bound: the server reads the case and ignores this.
                    province: caseId ? "" : jurisdiction,
                    history,
                    mode,
                    selection: mode === "rewrite" ? selection : "",
                },
                (token) => { reply += token; },
                (evt) => {
                    if (evt?.verification) verif = evt.verification;
                    if (evt?.guard) guard = evt.guard;
                },
            );
            // FAIL-CLOSED (2026-10-14). The streamed tokens are the UNCHECKED
            // draft; only the guard's text may become something to insert. No
            // guard result, or a check that did not run, is a Retry -- never a
            // proposal, never text to copy. (A stream cut short already threw.)
            if (!guard && !reply.trim()) {
                failed("No text came back. Please try again.");
                return;
            }
            if (!guard) {
                failed("The legal check's result did not arrive, so this reply is not shown. Nothing was added to the draft.");
                return;
            }
            if (!guard.ran) {
                failed(guard.reason === "corpus_unavailable"
                    ? "The statute library could not be read, so the legal check could not run. This reply is not shown and nothing was added to the draft."
                    : "The legal check could not run, so this reply is not shown. Nothing was added to the draft.");
                return;
            }
            // A whole draft is tidied (a lone jurisdiction line, a numbering gap a
            // withheld paragraph left) -- layout only, never the guard's wording.
            const tidy = (x) => (mode === "full" ? tidyFullDraft(x || "") : (x || ""));
            reply = tidy(guard.text);
            const withheld = guard.withheld || [];
            const check = { supported: guard.supported || [], notChecked: guard.not_checked || [],
                            jurisdiction: guard.jurisdiction || null, clarify: guard.clarify || null };
            if (!reply.trim() && withheld.length) {
                // NOTHING to insert -- never "insert it anyway". What to do next
                // depends on why (draft_guard.next_step); the one action offered
                // asks again WITHOUT citations, and that reply is checked like any
                // other (eval v2 dev: 5 of 44 replies were withheld whole).
                const next = guard.next_step?.text || "Rephrase the request or name the provision you mean.";
                setAiMessages(prev => [...prev, { role: "assistant", withheld,
                    placeholderAsk: q.includes(PLACEHOLDER_ASK) ? null : { ...target, q: `${q}\n\n${PLACEHOLDER_ASK}` },
                    text: `The legal check withheld the whole reply, so there is nothing to insert. ${next}` }]);
            } else if (!reply.trim()) {
                failed("No text came back. Please try again.");
            } else if (mode === "answer") {
                setAiMessages(prev => [...prev, { role: "assistant", text: reply, withheld, check }]);
            }
            // A PROPOSAL, never applied by itself: the template's formatting
            // stays until the lawyer chooses where this goes. A rewrite keeps
            // the passage it was asked for and the editor it lives in, so a
            // later edit can be detected before anything is replaced.
            const proposals = [];
            if (mode !== "answer" && reply.trim()) {
                proposals.push({
                    role: "assistant", text: reply,
                    proposal: { mode, text: reply, html: proposalToHtml(reply), range,
                                original: selection, editor: editorRef.current },
                    withheld, check,
                });
            }
            // A sentence stating a fact the lawyer did not give is never insertable
            // (draft_claims S3). The server's version with [placeholders] for those
            // facts -- checked again in full -- is a SEPARATE proposal to choose.
            const alt = guard.placeholder_alternative;
            if (mode !== "answer" && alt && (alt.text || "").trim()) {
                const altText = tidy(alt.text);
                proposals.push({
                    role: "assistant", text: altText,
                    proposal: { mode, text: altText, html: proposalToHtml(altText), range,
                                original: selection, editor: editorRef.current,
                                // The server says what the placeholders stand for:
                                // facts not given and/or a CPC provision to verify
                                // outside Punjab (draft_guard, 2026-10-16).
                                kindLabel: alt.label || "With [placeholders] for facts you did not give" },
                    withheld: alt.withheld || [],
                    check: { supported: alt.supported || [], notChecked: alt.not_checked || [],
                             jurisdiction: guard.jurisdiction || null, clarify: null },
                });
            }
            // ON AN EMPTY PAGE the whole draft is placed at once -- the version
            // with [placeholders] when there is one, since it keeps every
            // paragraph and marks the facts still to give. Still empty now?
            // (The lawyer may have typed while it was being written.)
            const auto = pageWasEmpty && !(editorRef.current?.innerText || "").trim()
                ? (proposals.length > 1 ? proposals[1] : proposals[0]) : null;
            if (auto) {
                const ed = editorRef.current;
                ed.focus();
                document.execCommand("selectAll", false, null);
                document.execCommand("insertHTML", false, auto.proposal.html);
                auto.applied = "Placed in the draft — edit it on the page";
                afterChange();
                setDocTitle(cur => (cur === "AI draft" ? (draftTitle(auto.text) || cur) : cur));
            }
            if (proposals.length) setAiMessages(prev => [...prev, ...proposals]);
            // Surface the citation check the backend runs on the finished draft.
            // It used to be computed, streamed, and silently dropped by the client.
            if (verif) {
                // Same rules as every other citation display: repealed and
                // uncheckable citations are named, and "nothing to check" is
                // never phrased as a pass.
                const v = verificationView(verif);
                const note = `${v.tone === "ok" ? "⚖️" : "⚠️"} Citation check: ${v.headline}.${v.detail ? " " + v.detail : ""}`;
                setAiMessages(prev => [...prev, { role: "assistant", text: note }]);
            }
        } catch (e) {
            // The server's own reason when there is one (403 case access, 409 a
            // draft case, 422 nothing selected); "Connection error" hid them all.
            const msg = e?.message && !/^HTTP \d+$/.test(e.message) ? e.message : "Connection error. Please try again.";
            failed(msg);
        } finally {
            setAiLoading(false);
        }
    };

    const translateToUrdu = async () => {
        const src = (editorRef.current?.innerText || "").trim();
        if (!src) return;
        setUrduOpen(true); setUrduBusy(true); setUrduText("");
        try {
            let out = "";
            await aiPleadingUrduStream({ document: src, template: tmpl.name }, (tok) => { out += tok; setUrduText(out); });
            if (!out) setUrduText("(No translation returned — please try again.)");
        } catch (e) {
            setUrduText("Translation failed: " + (e?.message || "error"));
        } finally { setUrduBusy(false); }
    };

    const downloadUrduPdf = async () => {
        if (!urduText.trim() || urduPdfBusy) return;
        setUrduPdfBusy(true);
        setUrduIssue("");

        const filename = (docTitle + "-urdu")
            .replace(/[^\w\s-]/g, "").trim() || "pleading-urdu";
        const payload = {
            urdu_text: urduText, title_ur: urduMeta.title_ur,
            court_ur: urduMeta.court_ur, english_label: tmpl.name,
        };

        // A new translation is a new intent and must get a new key.
        if (urduKeyedTextRef.current !== urduText) {
            urduKeyRef.current = null;
            urduKeyedTextRef.current = urduText;
        }
        urduKeyRef.current = urduKeyRef.current || idempotencyKey();

        const v2 = await pleadingUrduDocumentV2(payload, urduKeyRef.current);

        if (!v2.error) {
            const saved = await downloadDocumentFile(v2.docId, filename, {
                revisionId: v2.revisionId, expectedPdfSha256: v2.pdfSha256,
            });
            setUrduPdfBusy(false);
            if (saved?.error) setUrduIssue(saved.error);
            return;
        }

        if (!(v2.status === 404 && v2.code === "feature_disabled")) {
            // A real failure. Reported rather than swallowed: the old code
            // returned silently on error, so a lawyer pressed Download, nothing
            // happened, and nothing said why.
            setUrduPdfBusy(false);
            setUrduIssue(v2.error.message || "Could not produce the PDF.");
            return;
        }

        // The flag is off. The legacy route still works; it just cannot be
        // retried safely, which is why it is the fallback and not the default.
        const { data, error } = await pleadingUrduPdf(payload, urduKeyRef.current);
        setUrduPdfBusy(false);
        if (error || !data?.doc_id) {
            setUrduIssue(error?.message || "Could not produce the PDF.");
            return;
        }
        const saved = await downloadDocumentFile(data.doc_id, filename, {
            revisionId: data.revision_id, expectedPdfSha256: data.pdf_sha256 });
        if (saved?.error) setUrduIssue(saved.error);
    };

    const FONT_OPTIONS = ["Default Font", "Georgia", "Times New Roman", "Courier New", "Arial"];
    const SIZE_OPTIONS = ["10", "11", "12", "13", "14", "16", "18", "20"];
    const mode = draftingMode(t);
    const docFile = docTitle.replace(/[^\w\s-]/g, "").trim() || "document";
    const lineIcon = d => <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">{d}</svg>;

    return (
        <div data-drafter-editor data-drafting-theme data-mode={mode}>
            <style>{DRAFTING_TOKENS_CSS + "\n" + EDITOR_CSS}</style>

            {/* ── Top bar: back, the document, its actions, the account ── */}
            <header className="de-top">
                <button type="button" className="de-back" onClick={onBack} aria-label="Back to templates" title="Back to templates">
                    <Icon d={I.chevronLeft} size={20} />
                </button>
                <div className="de-title">
                    <h1>{docTitle}</h1>
                    <div className="de-meta">
                        <span className="de-cat">{tmpl.cat}</span>
                        <span aria-hidden="true">·</span>
                        <span>{new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</span>
                        <span aria-hidden="true">·</span>
                        <span>{wordCount} words</span>
                    </div>
                </div>
                <div className="de-right">
                    {saved && <span className="de-note ok"><Icon d={I.checkCircle} size={12} /> Saved to My Drafts</span>}
                    {justPublished && <span className="de-note ok" role="status"><Icon d={I.checkCircle} size={12} /> PDF saved to the Vault</span>}
                    {saveErr && <span className="de-note bad" role="alert">{saveErr}</span>}
                    {publishIssue && <span className="de-note bad" role="alert">{publishIssue}</span>}
                    <CitationWarning draftCheck={savedCheck} stale={checkStale} />
                    {/* ONE SAVE (2026-10-11). Two side-by-side buttons, "Save Draft" and
                        "Save to Documents", saved to two different places and said
                        neither. Now the button saves the working draft (My Drafts, where
                        it stays editable), and its menu holds the other save -- a fixed
                        PDF copy kept in the Vault -- with where each one goes in words.
                        The menu stays mounted while closed so its items keep their
                        state. A Vault copy does NOT file anything with a court. */}
                    <div className="de-drop de-save" ref={saveRef}>
                        <button type="button" className="de-btn primary de-save-main" onClick={handleSave} disabled={saving || caseBlocked}
                            title="Save your working draft. It stays in My Drafts, where you can keep editing it.">
                            <Icon d={I.save} size={15} /> {saving ? "Saving…" : "Save Draft"}
                        </button>
                        <button type="button" className="de-btn primary de-save-more" aria-label="More ways to save"
                            aria-haspopup="menu" aria-expanded={saveOpen} onClick={() => setSaveOpen(o => !o)}>
                            <Icon d="m6 9 6 6 6-6" size={15} />
                        </button>
                        <div className="de-pop de-save-menu" role="menu" aria-label="Save" hidden={!saveOpen}>
                            <button type="button" role="menuitem" className="de-opt" onClick={() => { setSaveOpen(false); handleSave(); }}
                                disabled={saving || caseBlocked}>
                                Save draft<small>Your working copy, in Legal Drafting → My Drafts. Stays editable.</small>
                            </button>
                            <button type="button" role="menuitem" className="de-opt" onClick={() => { setSaveOpen(false); publishAsDocument(); }}
                                disabled={publishing || caseBlocked}
                                title="Save a fixed, hashed copy of this draft into your documents">
                                {publishing ? "Saving PDF…" : published ? "Save a new PDF copy to the Vault" : "Save as PDF to the Vault"}
                                <small>A fixed PDF in Documents → Vault{caseId ? ", filed under this case" : ""}. It cannot be edited; save again for a new copy.</small>
                            </button>
                            {/* Where the saved copy lives, once there is one. */}
                            {published && <>
                                <div className="de-sep-h" aria-hidden="true" />
                                <button type="button" role="menuitem" className="de-opt" data-open-vault
                                    onClick={() => { setSaveOpen(false); setPage?.("vault"); }}>
                                    Open in Vault<small>Where the PDF copy is kept</small>
                                </button>
                                <button type="button" role="menuitem" className="de-opt"
                                    onClick={async () => {
                                        setSaveOpen(false); setPublishIssue("");
                                        const saved = await downloadDocumentFile(published.docId, `${docFile}.pdf`,
                                            { revisionId: published.revisionId, expectedPdfSha256: published.pdfSha256 });
                                        if (saved?.error) setPublishIssue(saved.error);
                                    }}>
                                    Saved PDF — download<small>The copy kept in the Vault</small>
                                </button>
                            </>}
                        </div>
                    </div>
                    {/* Which matter this document belongs to (2026-10-11): one button in
                        place of the account. The binding changes ONLY when the lawyer
                        picks another case here -- never by itself; see
                        lib/draftCaseBinding.js. */}
                    <div className="de-drop" ref={caseRef}>
                        <button type="button" className="de-case" data-case-binding={binding.state}
                            aria-haspopup="listbox" aria-expanded={caseOpen} onClick={() => setCaseOpen(o => !o)}
                            title={binding.state === "unavailable"
                                ? "This draft's case could not be loaded. Save, AI drafting and Save to Documents are paused."
                                : "The case this draft belongs to"}>
                            <span className="ic"><Icon d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16M4 6h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" size={16} /></span>
                            <span style={{ minWidth: 0, flex: 1 }}>
                                {binding.state === "bound" && <><b>{caseObj?.id} — {caseObj?.title}</b><small>{caseObj?.client}</small></>}
                                {binding.state === "none" && <><b>No case</b><small>Standalone document</small></>}
                                {binding.state === "loading" && <><b>Loading case…</b><small>Please wait</small></>}
                                {binding.state === "unavailable" && <><b>Case unavailable</b><small>Saving is paused</small></>}
                            </span>
                            <Icon d="m6 9 6 6 6-6" size={14} />
                        </button>
                        {caseOpen && (
                            <div className="de-pop" role="listbox" aria-label="Choose the case">
                                <h3>Attach to a case</h3>
                                <button type="button" role="option" className="de-opt"
                                    aria-selected={binding.state === "none"} onClick={() => pickCase(null)}>
                                    No case<small>Standalone document</small>
                                </button>
                                {cases.map(c => (
                                    <button key={c._id} type="button" role="option" className="de-opt"
                                        aria-selected={binding.state === "bound" && binding.caseId === c._id}
                                        onClick={() => pickCase(c)}>
                                        {c.id} — {c.title}<small>{c.client} · {c.type} · {c.status}</small>
                                    </button>
                                ))}
                                {cases.length === 0 && <div style={{ padding: "8px 10px", fontSize: 12.5, color: "var(--muted)" }}>You have no cases yet.</div>}
                            </div>
                        )}
                    </div>
                </div>
            </header>

            <div className="de-stage">
                {/* ── Formatting toolbar ── */}
                <div className="de-tools">
                <div className="de-toolbar" role="toolbar" aria-label="Formatting"
                    onWheel={e => {
                        // With the scrollbar hidden, a mouse wheel moves the bar along.
                        const el = e.currentTarget;
                        if (el.scrollWidth > el.clientWidth && Math.abs(e.deltaY) > Math.abs(e.deltaX)) el.scrollLeft += e.deltaY;
                    }}>
                    <TB label="Undo (Ctrl+Z)" onClick={() => exec("undo")}>{lineIcon(<><path d="M9 14 4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></>)}</TB>
                    <TB label="Redo (Ctrl+Y)" onClick={() => exec("redo")}>{lineIcon(<><path d="m15 14 5-5-5-5" /><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13" /></>)}</TB>
                    <span className="de-sep" />
                    <label style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }} htmlFor="de-font">Font</label>
                    <select id="de-font" className="de-select" style={{ width: 146 }} value={font}
                        onChange={e => { setFont(e.target.value); exec("fontName", e.target.value); }}>
                        {FONT_OPTIONS.map(f => <option key={f} value={f}>{f}</option>)}
                    </select>
                    <label style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }} htmlFor="de-size">Font size</label>
                    <select id="de-size" className="de-select" style={{ width: 62 }} value={fontSize}
                        onChange={e => { setFontSize(e.target.value); exec("fontSize", e.target.value); }}>
                        {SIZE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <span className="de-sep" />
                    <TB label="Bold (Ctrl+B)" active={queryState("bold")} onClick={() => exec("bold")} style={{ fontFamily: "Georgia, serif", fontWeight: 900, fontSize: 17 }}>B</TB>
                    <TB label="Italic (Ctrl+I)" active={queryState("italic")} onClick={() => exec("italic")} style={{ fontFamily: "Georgia, serif", fontStyle: "italic", fontWeight: 400, fontSize: 17 }}>I</TB>
                    <TB label="Underline (Ctrl+U)" active={queryState("underline")} onClick={() => exec("underline")} style={{ textDecoration: "underline", fontSize: 16 }}>U</TB>
                    <TB label="Subscript" onClick={() => exec("subscript")} style={{ fontSize: 15 }}><span>X<sub style={{ fontSize: "60%" }}>1</sub></span></TB>
                    <TB label="Superscript" onClick={() => exec("superscript")} style={{ fontSize: 15 }}><span>X<sup style={{ fontSize: "60%" }}>1</sup></span></TB>
                    <TB label="Strikethrough" onClick={() => exec("strikeThrough")} style={{ textDecoration: "line-through", fontSize: 16 }}>S</TB>
                    <span className="de-sep" />
                    <TB label="Align left" active={queryState("justifyLeft")} onClick={() => exec("justifyLeft")}>{lineIcon(<path d="M4 6h16M4 10h10M4 14h16M4 18h10" />)}</TB>
                    <TB label="Align centre" active={queryState("justifyCenter")} onClick={() => exec("justifyCenter")}>{lineIcon(<path d="M4 6h16M7 10h10M4 14h16M7 18h10" />)}</TB>
                    <TB label="Align right" active={queryState("justifyRight")} onClick={() => exec("justifyRight")}>{lineIcon(<path d="M4 6h16M10 10h10M4 14h16M10 18h10" />)}</TB>
                    <TB label="Justify" active={queryState("justifyFull")} onClick={() => exec("justifyFull")}>{lineIcon(<path d="M4 6h16M4 10h16M4 14h16M4 18h16" />)}</TB>
                    <span className="de-sep" />
                    <TB label="Bullet list" active={queryState("insertUnorderedList")} onClick={() => exec("insertUnorderedList")}>{lineIcon(<><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" strokeWidth="3" /></>)}</TB>
                    <TB label="Numbered list" active={queryState("insertOrderedList")} onClick={() => exec("insertOrderedList")}>{lineIcon(<><path d="M10 6h10M10 12h10M10 18h10" /><path d="M4 5h1.5v4M4 9h3M4 13.5c0-1 2.8-1 2.8.4 0 1-2.8 1.8-2.8 3.1h3" strokeWidth="1.5" /></>)}</TB>
                    <span className="de-sep" />
                    <TB label="Heading 1" onClick={() => exec("formatBlock", "h1")} style={{ fontSize: 15 }}>H1</TB>
                    <TB label="Heading 2" onClick={() => exec("formatBlock", "h2")} style={{ fontSize: 15 }}>H2</TB>
                    <TB label="Heading 3" onClick={() => exec("formatBlock", "h3")} style={{ fontSize: 15 }}>H3</TB>
                    <span className="de-sep" />
                    <TB label="Block quote" onClick={() => exec("formatBlock", "blockquote")}>{lineIcon(<path d="M7 7h4v4H8.5c0 2 1 3 2.5 3.5M14 7h4v4h-2.5c0 2 1 3 2.5 3.5" />)}</TB>
                    <TB label="Horizontal rule" onClick={() => exec("insertHorizontalRule")}>{lineIcon(<path d="M4 12h16" strokeWidth="2.6" />)}</TB>
                    <span className="de-sep" />
                    <TB label="Export Word (.doc)" onClick={handleExport} style={{ fontSize: 10.5, fontWeight: 800, letterSpacing: ".04em" }}>
                        <span style={{ display: "grid", placeItems: "center", gap: 1 }}><Icon d={I.fileText} size={15} />DOC</span>
                    </TB>
                    <TB label="Translate this draft into court Urdu" onClick={translateToUrdu} style={{ fontSize: 14, fontWeight: 600, padding: "0 10px" }}>اردو</TB>
                    {/* The blanks still to fill, behind one button (2026-10-20): the
                        list used to sit above the paper and push the document down. */}
                    {fields.length > 0 && (<>
                        <span className="de-sep" />
                        <button type="button" className="de-ph-btn" data-fields-toggle aria-expanded={fieldsOpen}
                            title="Fill the placeholders in this draft" onMouseDown={e => e.preventDefault()} onClick={() => (fieldsOpen ? setFieldsOpen(false) : openFill())}>
                            Placeholders <b>{fields.reduce((n, f) => n + f.count, 0)}</b>
                        </button>
                    </>)}
                </div>
                </div>

                <div className="de-split">
                    {/* ── The document ── */}
                    <section className="de-doc" aria-label="Document">
                        {/* The one note that stays on the page: the actions it explains
                            are paused, so the lawyer must see why. */}
                        {binding.state === "unavailable" && (
                            <div className="de-strips" role="alert">
                                <div style={{ fontWeight: 600, background: "var(--danger-soft)", color: "var(--danger)" }}>
                                    This draft belongs to a case that could not be loaded — it may have been
                                    reassigned, or you may be offline. Save, AI drafting and Save to Documents
                                    are paused so this draft is not attached to another matter. Export still works.
                                </div>
                            </div>
                        )}
                        <div className="de-scroll">
                            <div
                                ref={editorRef}
                                className="de-paper"
                                contentEditable
                                suppressContentEditableWarning
                                spellCheck={false}
                                aria-label={`${tmpl.name} — document text`}
                                data-empty={aiFirst ? "Describe the document in the Draft Assistant — the AI writes it here, then you edit it." : undefined}
                                onInput={e => { markEdited(); refreshFields(); setWordCount(e.currentTarget.innerText.trim().split(/\s+/).filter(Boolean).length); }}
                                onMouseUp={captureSelection}
                                onKeyUp={captureSelection}
                                style={{ fontFamily: font === "Default Font" ? "Georgia, 'Times New Roman', serif" : font }}
                                dangerouslySetInnerHTML={paperHtml}
                            />
                        </div>
                    </section>

                    {/* ── Fill placeholders (2026-10-20) ── */}
                    {fieldsOpen && (() => {
                        const left = new Map(fields.map(f => [f.label, f.count]));
                        const rows = fillStart.filter(l => fillTab === "all" || left.has(l));
                        const total = fillStart.length;
                        const done = fillStart.filter(l => !left.has(l)).length;
                        const blanks = left.get("___") || 0;
                        const pretty = l => (/^\[_+\]$/.test(l) ? "Blank (in brackets)" : l.replace(/^\[|\]$/g, ""));
                        const typed = Object.entries(fillValues).filter(([, v]) => v.trim()).length;
                        return (
                            <aside className={`de-assist${panelBig ? " big" : ""}`} aria-label="Fill placeholders" data-fill-panel>
                                <div className="de-fill-head">
                                    <span className="de-fill-ic" aria-hidden="true"><Icon d={I.edit} size={18} /></span>
                                    <div><b>Fill placeholders</b><small>{done} of {total} filled</small></div>
                                    {bigBtn}
                                    <button type="button" className="de-fill-x" aria-label="Close" title="Close (Esc)" onClick={() => { setFieldsOpen(false); setPanelBig(false); }}>✕</button>
                                </div>
                                <div className="de-fill-tabs">
                                    <div>
                                        <button type="button" aria-pressed={fillTab === "all"} onClick={() => setFillTab("all")}>All</button>
                                        <button type="button" aria-pressed={fillTab === "empty"} onClick={() => setFillTab("empty")}>Empty</button>
                                    </div>
                                    <span>{total - done} empty</span>
                                </div>
                                <div className="de-fill-list" data-lenis-prevent data-fields>
                                    {rows.map(l => {
                                        const filled = !left.has(l);
                                        return (
                                            <div key={l} className={`de-fill-row${filled ? " done" : ""}`} data-fill-row={l}>
                                                <header>
                                                    <i aria-hidden="true" />{pretty(l)}
                                                    {left.get(l) > 1 && <small style={{ color: "var(--muted)", fontWeight: 600 }}>×{left.get(l)}</small>}
                                                    <em>{filled ? "Filled" : "Empty"}</em>
                                                    {!filled && <button type="button" data-field={l} onMouseDown={e => e.preventDefault()} onClick={() => selectField(l)}>Find</button>}
                                                </header>
                                                {!filled && (
                                                    <textarea rows={1} aria-label={pretty(l)} placeholder={l} value={fillValues[l] || ""}
                                                        onChange={e => setFillValues(v => ({ ...v, [l]: e.target.value }))} />
                                                )}
                                            </div>
                                        );
                                    })}
                                    {blanks > 0 && (
                                        <div className="de-fill-row" data-fill-blanks>
                                            <header>
                                                <i aria-hidden="true" />Blank lines (___)<small style={{ color: "var(--muted)", fontWeight: 600 }}>×{blanks}</small>
                                                <em />
                                                <button type="button" data-field="___" onMouseDown={e => e.preventDefault()} onClick={() => selectField("___")}>Find next</button>
                                            </header>
                                            <small style={{ fontSize: 12, color: "var(--muted)" }}>Each is a different detail — select it on the page and type over it.</small>
                                        </div>
                                    )}
                                    {!rows.length && !blanks && <div style={{ color: "var(--muted)", fontSize: 13, textAlign: "center", padding: 20 }}>Every placeholder is filled.</div>}
                                </div>
                                <div className="de-fill-foot">
                                    <button type="button" className="de-fill-go" data-fill-go disabled={!typed} onClick={fillAll}
                                        title={typed ? undefined : "Type a value in any field first"}>
                                        <Icon d={I.check} size={17} />Fill in draft{typed ? ` (${typed})` : ""}
                                    </button>
                                </div>
                            </aside>
                        );
                    })()}
                    {/* ── Draft Assistant ── */}
                    {panelBig && <div className="de-scrim" data-panel-scrim aria-hidden="true" onClick={() => setPanelBig(false)} />}
                    <aside className={`de-assist${panelBig && !fieldsOpen ? " big" : ""}`} aria-label="Draft Assistant" style={fieldsOpen ? { display: "none" } : undefined}>
                        <div className="de-assist-head">
                            <b>Draft Assistant</b>
                            {bigBtn}
                        </div>
                        <div className="de-assist-body">
                            {aiMessages.length === 0 && (
                                <>
                                    <div className="de-hello">
                                        <div className="de-greet">
                                            <b>{greeting}, <em>{userName}</em></b>
                                            {aiFirst && (
                                                <p data-ai-first>Describe the document and its facts — who it is from and to, what happened, what you want. The AI writes the whole draft on the page; then edit it and fill the blanks.</p>
                                            )}
                                        </div>
                                    </div>
                                    <div className="de-label">Quick actions</div>
                                    <div className="de-quick" data-quick-actions>
                                        {/* Actions that fit THIS document (a letter has no prayer).
                                            A short name on the pill; the full instruction goes into
                                            the prompt, editable, with the action's mode selected. */}
                                        {quickActionsFor(tmpl.cat).map(a => (
                                            <button key={a.label} type="button" title={a.text}
                                                onClick={() => { setAiInput(a.text); setAssistMode(a.mode); aiInputRef.current?.focus(); }}>{a.label}</button>
                                        ))}
                                    </div>
                                </>
                            )}
                            {aiMessages.map((msg, i) => {
                                if (!msg.proposal) return (
                                    <div key={i} className={`de-msg ${msg.role === "user" ? "user" : "ai"}`} data-failed={msg.retry ? "" : undefined}>
                                        {msg.text}
                                        {msg.role !== "user" && <GuardNote withheld={msg.withheld} />}
                                        {msg.role !== "user" && <CheckScope check={msg.check} onChooseJurisdiction={caseId ? null : chooseJurisdiction} />}
                                        {msg.retry && (
                                            <div><button type="button" className="de-retry" data-retry disabled={aiLoading || caseBlocked}
                                                onClick={() => sendToAI(msg.retry)}>Retry</button></div>
                                        )}
                                        {msg.placeholderAsk && (
                                            <div><button type="button" className="de-retry" data-placeholder-ask disabled={aiLoading || caseBlocked}
                                                onClick={() => sendToAI(msg.placeholderAsk)}>Draft it with a [PROVISION] placeholder</button></div>
                                        )}
                                    </div>
                                );
                                const p = msg.proposal;
                                const rewrite = p.mode === "rewrite" && !!p.range;
                                const stale = rewrite && !msg.applied && !rewriteTarget(p);
                                return (
                                    <div key={i} className="de-msg ai de-prop" data-proposal={p.mode}>
                                        <div className="de-prop-kind" data-prop-kind={p.kindLabel ? "placeholder-alternative" : undefined}>{p.kindLabel || MODES[p.mode]?.label || "Proposal"}{msg.applied ? "" : " — not applied yet"}</div>
                                        <div className="de-prop-text">{p.text}</div>
                                        <GuardNote withheld={msg.withheld} />
                                        <CheckScope check={msg.check} onChooseJurisdiction={caseId ? null : chooseJurisdiction} />
                                        {msg.applied ? (
                                            <div className="de-prop-done" data-applied>✓ {msg.applied}</div>
                                        ) : (
                                            <>
                                                <div className="de-prop-actions">
                                                    {rewrite && (
                                                        <button type="button" className={stale ? "" : "primary"} disabled={stale} data-replace-selection
                                                            onClick={() => applyProposal(i, "replace-selection")}>Replace selected text</button>
                                                    )}
                                                    {p.mode === "full" ? (
                                                        <button type="button" className="primary" onClick={() => applyProposal(i, "replace-all")}>Replace whole draft</button>
                                                    ) : (
                                                        <button type="button" className={rewrite && !stale ? "" : "primary"}
                                                            onClick={() => applyProposal(i, "insert")}>Insert at cursor</button>
                                                    )}
                                                    <button type="button" onClick={() => applyProposal(i, "copy")}>Copy</button>
                                                </div>
                                                {stale && (
                                                    <div className="de-guard" data-stale-selection>
                                                        The passage this was written for has changed or is no longer in the draft, so it will not be replaced. Select the passage again and ask again — or insert this at the cursor.
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                );
                            })}
                            {aiLoading && <div className="de-msg ai de-dots" aria-label="Drafting"><i /><i style={{ animationDelay: ".2s" }} /><i style={{ animationDelay: ".4s" }} /></div>}
                            <div ref={aiEndRef} />
                        </div>
                        <div className="de-compose">
                            {/* Which law the draft is written under -- chosen before
                                the first request when there is no case. */}
                            <div className="de-juris" data-jurisdiction>
                                {caseId ? (
                                    <span data-jurisdiction-case>Jurisdiction: {provinceLabel(caseObj?.province)
                                        ? `${provinceLabel(caseObj.province)} (from the case)` : "jurisdiction-neutral — the case has no province"}</span>
                                ) : (
                                    <>
                                        <label htmlFor="de-juris">Jurisdiction</label>
                                        <select id="de-juris" value={jurisdiction} aria-required="true" onChange={e => setJurisdiction(e.target.value)}>
                                            <option value="" disabled>Choose before drafting…</option>
                                            {PROVINCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                                            <option value={NEUTRAL}>Not sure — jurisdiction-neutral</option>
                                        </select>
                                    </>
                                )}
                                {(caseId ? (provinceLabel(caseObj?.province) ? caseObj.province : NEUTRAL) : jurisdiction) && (
                                    <small>{coverageNote(caseId ? (provinceLabel(caseObj?.province) ? caseObj.province : NEUTRAL) : jurisdiction)}</small>
                                )}
                            </div>
                            {/* What the next reply will be, and what it acts on. */}
                            {(() => {
                                const active = modeFor({ chosen: assistMode, hasSelection: !!selectedText });
                                return (
                                    <div className="de-modes" role="group" aria-label="What the assistant should return" data-assist-modes>
                                        {Object.entries(MODES).map(([key, m]) => (
                                            <button key={key} type="button" aria-pressed={active === key} title={m.hint}
                                                disabled={key === "rewrite" && !selectedText}
                                                onClick={() => setAssistMode(key)}>{m.label}</button>
                                        ))}
                                    </div>
                                );
                            })()}
                            {selectedText && (
                                <div className="de-selchip" data-selection-chip>
                                    <span>Selected: “{selectedText.length > 70 ? selectedText.slice(0, 70) + "…" : selectedText}”</span>
                                    <button type="button" aria-label="Clear selection"
                                        onClick={() => { setSelectedText(""); savedRangeRef.current?.collapse(false); if (assistMode === "rewrite") setAssistMode(null); }}>×</button>
                                </div>
                            )}
                            <div className="de-compose-box">
                                <label style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }} htmlFor="de-prompt">Prompt for the draft assistant</label>
                                <textarea
                                    id="de-prompt"
                                    ref={aiInputRef}
                                    value={aiInput} onChange={e => setAiInput(e.target.value)}
                                    onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendToAI(); } }}
                                    placeholder="Enter prompt to generate or modify draft"
                                    rows={1}
                                />
                                <div className="de-compose-row">
                                    <span className="de-hint">{!caseId && !jurisdiction ? "Choose a jurisdiction to start drafting" : "Enter to send · Shift+Enter for a new line"}</span>
                                    <button type="button" className="de-send-ic" onClick={() => sendToAI()} disabled={!aiInput.trim() || aiLoading || caseBlocked || (!caseId && !jurisdiction)}
                                        aria-label="Generate" title="Generate (Enter)">
                                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
                                        <span className="de-sr">Generate</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </aside>
                </div>
            </div>

            {urduOpen && (<ModalPortal>
                <div onClick={() => setUrduOpen(false)} style={{
                    position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 60,
                    display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
                }}>
                    <div onClick={e => e.stopPropagation()} style={{
                        width: "min(760px, 96vw)", maxHeight: "92vh", display: "flex", flexDirection: "column",
                        background: t.surface, border: `1px solid ${t.border}`, borderRadius: 14, boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
                    }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${t.border}` }}>
                            <div>
                                <div style={{ fontSize: 14, fontWeight: 800, color: t.text }}>Court Urdu — عدالتی اردو</div>
                                <div style={{ fontSize: 11, color: t.textFaint, marginTop: 2 }}>{tmpl.name} · review the translation, then export as an RTL PDF</div>
                            </div>
                            <button onClick={() => setUrduOpen(false)} style={{ background: "none", border: "none", color: t.textMuted, fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
                        </div>

                        <div style={{ padding: 16, overflowY: "auto" }}>
                            <div className="rgrid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
                                <input value={urduMeta.court_ur} onChange={e => setUrduMeta(m => ({ ...m, court_ur: e.target.value }))} placeholder="عدالت (court header, optional)" dir="rtl"
                                    style={{ padding: "8px 10px", borderRadius: 8, border: `1.5px solid ${t.border}`, background: t.card, color: t.text, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
                                <input value={urduMeta.title_ur} onChange={e => setUrduMeta(m => ({ ...m, title_ur: e.target.value }))} placeholder="عنوان (title, optional)" dir="rtl"
                                    style={{ padding: "8px 10px", borderRadius: 8, border: `1.5px solid ${t.border}`, background: t.card, color: t.text, fontSize: 13, fontFamily: "inherit", outline: "none" }} />
                            </div>
                            <textarea value={urduText} onChange={e => setUrduText(e.target.value)} dir="rtl" readOnly={urduBusy}
                                placeholder={urduBusy ? "ترجمہ ہو رہا ہے…" : ""}
                                style={{ width: "100%", minHeight: 320, boxSizing: "border-box", padding: "12px 14px", borderRadius: 10, border: `1.5px solid ${t.border}`, background: t.card, color: t.text, fontSize: 15, lineHeight: 2, fontFamily: "'Noto Naskh Arabic','Jameel Noori Nastaleeq',serif", resize: "vertical", outline: "none" }} />
                            {urduBusy && <div style={{ fontSize: 11.5, color: t.primary, marginTop: 8 }}>Translating… ترجمہ ہو رہا ہے…</div>}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 18px", borderTop: `1px solid ${t.border}`, gap: 10 }}>
                            {/* A failed download used to return silently: the
                                lawyer pressed Download, nothing arrived, and
                                nothing said why. */}
                            <span style={{ fontSize: 10.5, color: urduIssue ? t.danger : t.textFaint, flex: 1 }}>
                                {urduIssue || "Machine-assisted — verify legal terms before filing"}
                            </span>
                            <div style={{ display: "flex", gap: 8 }}>
                                <button onClick={translateToUrdu} disabled={urduBusy} style={{ padding: "8px 14px", borderRadius: 8, border: `1px solid ${t.border}`, background: t.card, color: t.text, fontSize: 12, fontWeight: 700, cursor: urduBusy ? "default" : "pointer", fontFamily: "inherit" }}>↻ Retranslate</button>
                                <button onClick={downloadUrduPdf} disabled={urduBusy || urduPdfBusy || !urduText.trim()} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: (urduBusy || urduPdfBusy || !urduText.trim()) ? t.border : "#16a34a", color: "#fff", fontSize: 12, fontWeight: 800, cursor: (urduBusy || urduPdfBusy || !urduText.trim()) ? "default" : "pointer", fontFamily: "inherit" }}>{urduPdfBusy ? "Generating…" : "⬇ Download Urdu PDF"}</button>
                            </div>
                        </div>
                    </div>
                </div>
            </ModalPortal>)}
        </div>
    );
}

// ============================================================
// ROOT
// ============================================================
const _DA_MAP = { open: "Filed", active: "Under Hearing", closed: "Closed", dismissed: "Closed" };

// One shape for a case, whether it came from the list or was fetched by id.
const _mapCase = (c) => ({
    id: c.case_number || c._id,
    _id: c._id,
    title: c.title || "Untitled",
    client: c.client_name || "—",
    court: c.province || "—",
    // The stored province value (punjab | sindh | kpk | balochistan | federal):
    // shown in the drafter as the case's jurisdiction, never sent as an override.
    province: c.province || null,
    type: c.case_type ? c.case_type.charAt(0).toUpperCase() + c.case_type.slice(1) : "Other",
    status: _DA_MAP[c.status] || "Filed",
});

function DocAutomationPage() {
    const { t } = useTheme();
    const { activeCase } = useCase();
    const [stage, setStage] = useState("gallery");
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [apiCases, setApiCases] = useState([]);
    const [selectedCaseId, setSelectedCaseId] = useState("");
    const [drafts, setDrafts] = useState([]);
    const [activeDraft, setActiveDraft] = useState(null);
    // The open editor's case, fixed when it opened. See lib/draftCaseBinding.js.
    const [editorBinding, setEditorBinding] = useState(NO_CASE);
    // Guards against a slow case lookup for one draft landing after another
    // draft (or a new document) has been opened.
    const openSeq = useRef(0);
    // One editor instance per opened document: a new template or draft never
    // inherits the previous one's AI proposals or saved selection.
    const [editorKey, setEditorKey] = useState(0);

    useEffect(() => {
        if (stage !== "gallery") return;
        listDocDrafts().then(({ data }) => { if (Array.isArray(data)) setDrafts(data); });
    }, [stage]);

    const openDraft = async (d) => {
        const seq = ++openSeq.current;
        setEditorKey(k => k + 1);
        setActiveDraft(d);
        setEditorBinding(pendingBindingForDraft(d));
        setSelectedTemplate({ id: -1, name: d.template_name || d.title, cat: "Draft", desc: "", icon: d.template_icon || "📄" });
        setStage("editor");
        const binding = await bindingForDraft(d, apiCases, getCase, _mapCase);
        if (seq === openSeq.current) setEditorBinding(binding);
    };

    const openTemplate = (tmpl) => {
        ++openSeq.current;
        setEditorKey(k => k + 1);
        setActiveDraft(null);
        setEditorBinding(bindingForNewDocument(activeCaseObj));
        setSelectedTemplate(tmpl);
        setStage("editor");
    };

    const removeDraft = async (id) => {
        const { error } = await deleteDocDraft(id);
        if (!error) setDrafts(prev => prev.filter(x => x.id !== id));
    };

    useEffect(() => {
        listCases({ page_size: 50 }).then(({ data }) => {
            if (data?.items) {
                const mapped = data.items.map(_mapCase);
                setApiCases(mapped);
                // A CASE IS OPTIONAL. Only the case the lawyer is already working
                // in is preselected. It used to fall back to the FIRST listed case,
                // so a new template silently bound itself -- prefilled with that
                // case's client -- to a matter the lawyer never chose, and "Save to
                // Documents" filed it there. No active case: no case.
                if (activeCase) {
                    const match = mapped.find(c => c.id === activeCase || c._id === activeCase);
                    if (match) setSelectedCaseId(match.id);
                }
            }
        });
    }, []);

    const activeCaseObj = apiCases.find(c => c.id === selectedCaseId) || null;

    // Fills the app's <main> in normal flow (2026-10-09). It used to be
    // position:fixed at the sidebar's guessed width, but <main> animates in
    // with a transform, which makes it the containing block: the offset
    // applied twice and left an empty band beside the sidebar.
    return (
        <div data-drafter-pane style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, minWidth: 0, background: t.bg }}>
            {stage === "gallery" && (
                <DraftingHome
                    onSelect={openTemplate}
                    drafts={drafts}
                    onOpenDraft={openDraft}
                    onDeleteDraft={removeDraft}
                    t={t}
                />
            )}
            {stage === "editor" && selectedTemplate && (
                <StageEditor key={editorKey} tmpl={selectedTemplate} binding={editorBinding} draft={activeDraft} onBack={() => setStage("gallery")} t={t}
                    cases={apiCases} onRebind={b => { ++openSeq.current; setEditorBinding(b); }} />
            )}
        </div>
    );
}

export { DocAutomationPage };
