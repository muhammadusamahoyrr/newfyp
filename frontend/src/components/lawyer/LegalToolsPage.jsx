'use client';
// Legal Tools for the lawyer (2026-10-09): the bail checker and the
// calculators the backend already serves (court fee, inheritance, labour
// dues). The client has its own copies in client/ModTools.jsx; this is the
// lawyer's, in the lawyer theme, and imports nothing from the client side.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTheme } from "./theme.js";
import { useToast } from "./Toast.jsx";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { keyForIntent } from "@/lib/intentKey.js";
import {
    bailSearch, bailCheck, courtFeeCalculate, inheritanceCalculate,
    inheritanceSettlementPdf, labourDuesCalculate, downloadDocumentFile,
} from "@/lib/api.js";

const TOOLS_CSS = `[data-tools-ws]{flex:none;min-height:100%;color:var(--ink);font-family:"Hanken Grotesk",system-ui,sans-serif;-webkit-font-smoothing:antialiased;background:var(--bg);padding:26px 30px 48px;box-sizing:border-box}
[data-tools-ws] *{box-sizing:border-box}
[data-tools-ws] button,[data-tools-ws] input,[data-tools-ws] select{font-family:inherit}
[data-tools-ws] .lt-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:18px}
[data-tools-ws] .lt-head h1{margin:0;font-family:"Literata",Georgia,serif;font-size:28px;font-weight:600;letter-spacing:-.01em}
[data-tools-ws] .lt-head p{margin:4px 0 0;font-size:13.5px;color:var(--muted)}
[data-tools-ws] .lt-tabs{display:flex;gap:4px;padding:4px;border-radius:12px;background:var(--surface-2);border:1px solid var(--line)}
[data-tools-ws] .lt-tabs button{height:34px;padding:0 14px;border:0;border-radius:9px;background:none;color:var(--muted);font-size:13px;font-weight:650;cursor:pointer}
[data-tools-ws] .lt-tabs button[aria-pressed="true"]{background:var(--surface);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}
[data-tools-ws] .lt-grid{display:grid;grid-template-columns:minmax(300px,380px) minmax(0,1fr);gap:16px;align-items:start}
[data-tools-ws] .lt-card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px}
[data-tools-ws] .lt-card h2{margin:0 0 4px;font-size:15px;font-weight:700}
[data-tools-ws] .lt-sub{font-size:12.5px;color:var(--muted);margin:0 0 14px;line-height:1.5}
[data-tools-ws] .lt-lbl{display:block;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin:12px 0 6px}
[data-tools-ws] .lt-in{width:100%;height:40px;padding:0 12px;border-radius:10px;border:1px solid var(--line-strong);background:var(--input);color:var(--ink);font-size:13.5px;outline:none}
[data-tools-ws] .lt-in:focus{border-color:var(--brand-text)}
[data-tools-ws] .lt-btn{height:40px;padding:0 16px;border-radius:10px;border:0;background:linear-gradient(135deg,#3EE0A1,#2EC4D6);color:#04212A;font-size:13.5px;font-weight:700;cursor:pointer;white-space:nowrap}
[data-tools-ws] .lt-btn:disabled{opacity:.55;cursor:default}
[data-tools-ws] .lt-btn.ghost{background:none;border:1px solid var(--line-strong);color:var(--ink)}
[data-tools-ws] .lt-empty{padding:40px 20px;text-align:center;color:var(--muted);font-size:13px;line-height:1.6}
[data-tools-ws] .lt-big{font-size:32px;font-weight:800;color:var(--brand-text);margin:6px 0}
[data-tools-ws] .lt-note{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.5}
[data-tools-ws] .lt-warn{margin-top:12px;padding:10px 12px;border-radius:10px;background:rgba(242,195,94,.1);border:1px solid rgba(242,195,94,.35);font-size:12.5px;color:var(--ink)}
[data-tools-ws] .lt-table{border:1px solid var(--line);border-radius:12px;overflow:hidden}
[data-tools-ws] .lt-row{display:grid;grid-template-columns:minmax(0,1fr) 64px 64px 120px;gap:8px;padding:10px 12px;border-top:1px solid var(--line);font-size:13px;align-items:center}
[data-tools-ws] .lt-row:first-child{border-top:0;background:var(--surface-2);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--faint)}
[data-tools-ws] .lt-row.two{grid-template-columns:minmax(0,1fr) 140px}
[data-tools-ws] .lt-row.total{border-top:2px solid var(--line-strong);font-weight:800;color:var(--brand-text)}
[data-tools-ws] .lt-num{text-align:right;font-weight:700}
[data-tools-ws] .lt-count{display:flex;align-items:center;justify-content:space-between;padding:8px 10px 8px 12px;border-radius:10px;border:1px solid var(--line);background:var(--input);font-size:13px;font-weight:600}
[data-tools-ws] .lt-count div{display:flex;align-items:center;gap:8px}
[data-tools-ws] .lt-count button{width:26px;height:26px;border-radius:7px;border:1px solid var(--line-strong);background:var(--surface);color:var(--ink);font-weight:700;cursor:pointer}
[data-tools-ws] .lt-count b{min-width:18px;text-align:center}
[data-tools-ws] .lt-count b.on{color:var(--brand-text)}
[data-tools-ws] .lt-chip{display:inline-flex;align-items:center;height:24px;padding:0 9px;border-radius:999px;font-size:11.5px;font-weight:700;border:1px solid}
[data-tools-ws] .lt-chip.good{color:#5AD69A;border-color:rgba(90,214,154,.4);background:rgba(90,214,154,.1)}
[data-tools-ws] .lt-chip.bad{color:#F28B80;border-color:rgba(242,139,128,.4);background:rgba(242,139,128,.1)}
[data-tools-ws] .lt-chip.warn{color:#F2C35E;border-color:rgba(242,195,94,.4);background:rgba(242,195,94,.1)}
[data-tools-ws] .lt-chip.neutral{color:var(--muted);border-color:var(--line-strong);background:var(--surface-2)}
[data-tools-ws] .lt-hit{display:block;width:100%;text-align:left;padding:11px 12px;border-radius:10px;border:1px solid transparent;background:none;color:var(--ink);cursor:pointer;margin-bottom:2px}
[data-tools-ws] .lt-hit:hover{background:var(--hover-tint)}
[data-tools-ws] .lt-hit.on{border-color:var(--brand-text);background:var(--hover-tint)}
[data-tools-ws] .lt-seg{display:inline-flex;gap:4px;padding:3px;border-radius:10px;background:var(--surface-2);border:1px solid var(--line);margin-bottom:14px}
[data-tools-ws] .lt-seg button{height:30px;padding:0 12px;border:0;border-radius:7px;background:none;color:var(--muted);font-size:12.5px;font-weight:700;cursor:pointer}
[data-tools-ws] .lt-seg button[aria-pressed="true"]{background:var(--surface);color:var(--ink);box-shadow:inset 0 0 0 1px var(--line)}
[data-tools-ws] .lt-guide{padding:14px;border-radius:12px;background:var(--surface-2);border:1px solid var(--line)}
[data-tools-ws] .lt-guide ol{margin:8px 0 0;padding-left:18px}
[data-tools-ws] .lt-guide li{font-size:13px;line-height:1.55;margin-bottom:6px}
[data-tools-ws] .lt-check{display:flex;align-items:center;gap:10px;margin-top:14px;padding:12px 14px;border-radius:12px;background:var(--surface-2);font-size:14px;font-weight:600;cursor:pointer}
[data-tools-ws] .lt-check input{width:18px;height:18px;accent-color:#3EE0A1}
/* CALCULATORS, STYLE A (2026-11-27): tabs under the title, heirs in two
   columns, the result side laid out before the first calculation. */
[data-tools-ws] .lt-tabs{display:flex;gap:4px;padding:4px;border-radius:999px;background:var(--surface);border:1px solid var(--line)}
[data-tools-ws] .lt-tabs button{height:34px;padding:0 16px;border-radius:999px;border:0;background:none;color:var(--ink);font-size:13.5px;font-weight:700;cursor:pointer}
[data-tools-ws] .lt-tabs button[aria-pressed="true"]{background:#F3F2F4;color:#2A282C;box-shadow:none}
[data-tools-ws][data-mode="light"] .lt-tabs button[aria-pressed="true"]{background:var(--chip-on-bg,#1A2E35);color:var(--chip-on-ink,#EAF2F4)}
[data-tools-ws] .lt-grid{grid-template-columns:minmax(300px,420px) minmax(0,1fr);gap:16px}
[data-tools-ws] .lt-card{border-radius:16px;padding:18px}
[data-tools-ws] .lt-card h2{font-size:15px}
[data-tools-ws] .lt-sub{font-size:12.5px;margin-bottom:12px}
[data-tools-ws] .lt-lbl{font-size:12.5px;font-weight:700;letter-spacing:0;text-transform:none;color:var(--muted);margin:12px 0 5px}
[data-tools-ws] .lt-in{height:40px;border-radius:10px;font-size:13.5px;padding:0 12px}
[data-tools-ws] .lt-btn{border-radius:999px;height:40px;font-size:13.5px}
[data-tools-ws] .lt-btn.lt-go{width:100%;margin-top:16px}
[data-tools-ws] .lt-btn.teal{height:36px;font-size:13px;background:linear-gradient(180deg,#8AE7F2 0%,#5BCFE2 55%,#3FBFD6 100%)}
[data-tools-ws] .lt-heirs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
[data-tools-ws] .lt-count{border:0;background:var(--surface-2);border-radius:10px;padding:6px 6px 6px 10px;gap:6px}
[data-tools-ws] .lt-count>span{flex:1;min-width:0;font-size:13px;font-weight:600;line-height:1.25}
[data-tools-ws] .lt-count small{display:block;font-size:11.5px;font-weight:500;color:var(--faint)}
[data-tools-ws] .lt-count div{gap:6px}
[data-tools-ws] .lt-count.on{background:color-mix(in srgb,var(--brand-text) 10%,transparent);box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--brand-text) 40%,transparent)}
/* HEIR BOXES "RAISED SLATE" (2026-11-27, option A): in dark mode a step LIGHTER
   than the card, so they sit on it; a chosen one only gains a mint edge. */
[data-tools-ws]:not([data-mode="light"]) .lt-count{background:#24474F;box-shadow:inset 0 1px 0 rgba(255,255,255,.05)}
[data-tools-ws]:not([data-mode="light"]) .lt-count.on{background:#24474F;box-shadow:inset 0 0 0 1.5px #3EE0A1}
[data-tools-ws]:not([data-mode="light"]) .lt-count button:not(.on){border:0;background:rgba(0,0,0,.22)}
[data-tools-ws] .lt-count button{width:26px;height:26px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.08);font-size:13px}
[data-tools-ws] .lt-count button.plus.on{border:0;background:linear-gradient(135deg,#3EE0A1,#2EC4D6);color:#04212A}
[data-tools-ws][data-mode="light"] .lt-count button:not(.on){background:var(--chip-n);border-color:var(--line)}
[data-tools-ws] .lt-count b{color:var(--faint);font-size:13px;min-width:14px}
[data-tools-ws] .lt-count b.on{color:var(--brand-text)}
[data-tools-ws] .lt-check{padding:10px 12px;font-size:13.5px;margin-top:12px}
[data-tools-ws] .lt-check input{width:16px;height:16px}
[data-tools-ws] .lt-card.flush{padding:0;overflow:hidden}
[data-tools-ws] .lt-pad{padding:14px 18px 18px}
[data-tools-ws] .lt-band{display:flex;flex-direction:column;gap:2px;padding:16px 18px;background:var(--surface-2)}
[data-tools-ws] .lt-band-k{font-size:12.5px;font-weight:700;color:var(--muted)}
[data-tools-ws] .lt-band-v{font:600 28px/1.15 "Literata",Georgia,serif;color:var(--brand-text)}
[data-tools-ws] .lt-band-v.none{color:var(--faint)}
[data-tools-ws] .lt-band-s{font-size:12.5px;color:var(--muted)}
[data-tools-ws] .lt-res-head{display:flex;align-items:center;gap:12px;padding:14px 18px}
[data-tools-ws] .lt-res-head h2{margin:0 0 2px;font-size:15px}
[data-tools-ws] .lt-table.flat{border:0;border-radius:0}
[data-tools-ws] .lt-table.flat .lt-row{padding:10px 18px;font-size:13.5px}
[data-tools-ws] .lt-table.flat .lt-row:first-child{font-size:11.5px;letter-spacing:.08em}
[data-tools-ws] .lt-row.pending{color:var(--faint)}
[data-tools-ws] .lt-hint{font-size:13px;color:var(--muted);line-height:1.55}
[data-tools-ws] .lt-hint b{color:var(--ink)}
[data-tools-ws] .lt-text{font-size:13.5px;line-height:1.55;margin-top:6px}
[data-tools-ws] .lt-list{margin:8px 0 0;padding-left:18px;font-size:13.5px;line-height:1.55;color:var(--muted)}
[data-tools-ws] .lt-info{margin-top:12px;padding:10px 12px;border-radius:12px;background:color-mix(in srgb,var(--teal-ink) 10%,transparent);border:1px solid color-mix(in srgb,var(--teal-ink) 35%,transparent);font-size:13px;color:var(--teal-ink)}
[data-tools-ws] .lt-head.center{flex-direction:column;align-items:center;text-align:center;margin:14px 0 22px}
[data-tools-ws] .lt-head.center h1{font-size:40px}
[data-tools-ws] .lt-head.center p{font-size:15px;margin-top:8px}
[data-tools-ws] .lb-wrap{display:flex;flex-direction:column;align-items:center;gap:18px}
[data-tools-ws] .lb-search{width:100%;max-width:760px;display:flex;align-items:center;gap:12px;height:56px;padding:0 20px;border-radius:999px;background:var(--surface);border:1px solid color-mix(in srgb,var(--brand-text) 50%,transparent);box-shadow:0 0 0 4px var(--brand-soft);color:var(--faint)}
[data-tools-ws] .lb-search input{flex:1;min-width:0;border:0;outline:none;background:transparent;color:var(--ink);font-size:17px}
[data-tools-ws] .lb-search input::placeholder{color:var(--faint)}
[data-tools-ws] .lb-n{font-size:12.5px;color:var(--faint);white-space:nowrap}
[data-tools-ws] .lb-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
[data-tools-ws] .lb-try{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--faint)}
[data-tools-ws] .lb-chip{height:30px;padding:0 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.06);color:var(--ink);font-size:12.5px;font-weight:600;cursor:pointer}
[data-tools-ws] .lb-chip:hover{border-color:var(--hover-line)}
[data-tools-ws] .lb-none{max-width:760px;width:100%;padding:14px 18px;border-radius:14px;background:var(--surface);border:1px solid var(--line);font-size:13.5px;color:var(--muted);text-align:center}
[data-tools-ws] .lb-cards{width:100%;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
[data-tools-ws] .lb-card{border-radius:18px;background:var(--surface);border:1px solid var(--line);padding:18px 20px;display:flex;flex-direction:column;gap:10px;transition:border-color .15s}
[data-tools-ws] .lb-card.on{border-color:color-mix(in srgb,var(--brand-text) 55%,transparent)}
[data-tools-ws] .lb-card-top{display:flex;align-items:center;gap:8px}
[data-tools-ws] .lb-sec{font:600 13px "JetBrains Mono",monospace;color:var(--brand-text)}
[data-tools-ws] .lb-title{font:600 19px/1.25 "Literata",Georgia,serif}
[data-tools-ws] .lb-meta{font-size:13px;color:var(--muted)}
[data-tools-ws] .lb-arrest{display:flex;gap:8px;margin-top:auto;padding-top:4px}
[data-tools-ws] .lb-arrest button{flex:1;height:36px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.08);color:var(--ink);font-size:13px;font-weight:700;cursor:pointer}
[data-tools-ws] .lb-arrest button.on{border:0;background:linear-gradient(135deg,#3EE0A1,#2EC4D6);color:#04212A}
[data-tools-ws] .lb-arrest button:disabled{opacity:.6;cursor:wait}
[data-tools-ws][data-mode="light"] .lb-arrest button:not(.on),[data-tools-ws][data-mode="light"] .lb-chip{background:var(--chip-n);border-color:var(--line)}
[data-tools-ws] .lb-result{width:100%;border-radius:18px;background:var(--surface);border:1px solid var(--line);padding:20px 22px;display:flex;flex-direction:column;gap:12px}
[data-tools-ws] .lb-result-head{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap}
[data-tools-ws] .lb-result-head h2{margin:2px 0 0;font:600 22px/1.2 "Literata",Georgia,serif}
[data-tools-ws] .lb-chips{display:flex;gap:6px;flex-wrap:wrap}
[data-tools-ws] .lb-result-head .lb-chips{margin-left:auto}
[data-tools-ws] .lb-steps{padding:16px 18px;border-radius:14px;background:var(--surface-2);display:flex;flex-direction:column;gap:10px}
[data-tools-ws] .lb-steps b{font-size:15px}
[data-tools-ws] .lb-steps ol{margin:0;padding-left:20px;display:flex;flex-direction:column;gap:6px;font-size:14px;line-height:1.55}`;

const errText = (error, fallback) => error?.message || error?.detail || fallback;
const toNum = (v) => parseInt(String(v).replace(/[^0-9]/g, ""), 10) || 0;

function Shell({ title, sub, tabs, tab, setTab, children, center = false }) {
    const { t } = useTheme();
    return (
        <div data-tools-ws data-drafting-theme data-mode={draftingMode(t)}>
            <style>{`${DRAFTING_TOKENS_CSS}\n${TOOLS_CSS}`}</style>
            <div className={`lt-head${center ? " center" : ""}`}>
                <div>
                    <h1>{title}</h1>
                    <p>{sub}</p>
                </div>
                {tabs && (
                    <div className="lt-tabs" role="group" aria-label="Calculator">
                        {tabs.map(([id, label]) => (
                            <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>
                        ))}
                    </div>
                )}
            </div>
            {children}
        </div>
    );
}

/* ── Bail checker ─────────────────────────────────────────────────────── */
function Chip({ tone, children }) { return <span className={`lt-chip ${tone}`}>{children}</span>; }
const yesNo = (v, yes, no) => (v === null || v === undefined
    ? <Chip tone="neutral">depends</Chip>
    : v ? <Chip tone="good">{yes}</Chip> : <Chip tone="bad">{no}</Chip>);

/* V4, "instant lookup" (2026-11-27): one big search; matches appear as cards
 * while the lawyer types, each with Before / After arrest; the chosen card's
 * classification and steps open in a panel underneath. bailSearch and
 * bailCheck are the same calls as before. */
function BailChecker() {
    const toast = useToast();
    const [q, setQ] = useState("");
    const [hits, setHits] = useState([]);
    const [searched, setSearched] = useState(false);
    const [searching, setSearching] = useState(false);
    const [picked, setPicked] = useState(null);
    const [arrested, setArrested] = useState(null);
    const [checking, setChecking] = useState(false);
    const [res, setRes] = useState(null);
    const seq = useRef(0);
    const resultRef = useRef(null);

    // Only the latest search may land: a slow reply for "30" must not
    // replace the results for "302".
    const search = async (term) => {
        const want = (term ?? q).trim();
        const mine = ++seq.current;
        if (!want) { setHits([]); setSearched(false); setSearching(false); return; }
        setSearching(true);
        const { data, error } = await bailSearch(want);
        if (mine !== seq.current) return;
        setSearching(false);
        if (error) return toast.show(errText(error, "Search failed"), "danger");
        setSearched(true); setHits(data?.results || []);
    };
    useEffect(() => {
        const id = setTimeout(() => search(q), 350);
        return () => clearTimeout(id);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [q]);

    const check = async (o, isArrested) => {
        setPicked(o); setArrested(isArrested); setChecking(true);
        const { data, error } = await bailCheck({ law: o.law, section: o.section, arrested: isArrested });
        setChecking(false);
        if (error || !data) return toast.show(errText(error, "Check failed"), "danger");
        setRes(data);
        setTimeout(() => { try { resultRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" }); } catch { /* no DOM */ } }, 0);
    };

    return (
        <div className="lb-wrap">
            <label className="lb-search">
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
                <span className="lb-sr">Section or offence</span>
                <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === "Enter" && search()}
                    placeholder="A section (302, 489-F) or an offence (theft, cheque)" autoFocus data-bail-search />
                <span className="lb-n">{searching ? "Searching…" : searched ? `${hits.length} match${hits.length === 1 ? "" : "es"}` : ""}</span>
            </label>

            {!searched && !searching && (
                <div className="lb-try">
                    <span>Try</span>
                    {["302", "489-F", "theft", "cheque"].map(x => (
                        <button key={x} type="button" className="lb-chip" onClick={() => setQ(x)}>{x}</button>
                    ))}
                </div>
            )}

            {searched && hits.length === 0 && (
                <div className="lb-none">No matching offence in the reference list. Confirm the section against the Second Schedule of the CrPC 1898.</div>
            )}

            {hits.length > 0 && (
                <div className="lb-cards" data-bail-cards>
                    {hits.map(o => {
                        const on = picked?.id === o.id;
                        return (
                            <article key={o.id} className={`lb-card${on ? " on" : ""}`} data-bail-hit={o.id}>
                                <div className="lb-card-top">
                                    <b className="lb-sec">{o.law} {o.section}</b>
                                    {o.confidence === "verify" && <Chip tone="warn">verify</Chip>}
                                    <span style={{ marginLeft: "auto" }}>{yesNo(o.bailable, "Bailable", "Non-bailable")}</span>
                                </div>
                                <b className="lb-title">{o.title}</b>
                                <span className="lb-meta">{[o.punishment, o.court].filter(Boolean).join(" · ")}</span>
                                <div className="lb-arrest" role="group" aria-label={`Bail steps for ${o.law} ${o.section}`}>
                                    {[["Before arrest", false], ["After arrest", true]].map(([label, v]) => (
                                        <button key={label} type="button" aria-pressed={on && arrested === v}
                                            className={on && arrested === v ? "on" : ""} disabled={checking}
                                            onClick={() => check(o, v)}>{label}</button>
                                    ))}
                                </div>
                            </article>
                        );
                    })}
                </div>
            )}

            {res && (
                <section ref={resultRef} className="lb-result" aria-label="Bail steps" data-bail-result>
                    {res.found ? (<>
                        <div className="lb-result-head">
                            <div>
                                <span className="lb-meta">{res.offence.law} s.{res.offence.section} · {arrested ? "after arrest" : "before arrest"}</span>
                                <h2>{res.offence.title}</h2>
                            </div>
                            <div className="lb-chips">
                                {yesNo(res.offence.bailable, "bailable", "non-bailable")}
                                {yesNo(res.offence.cognizable, "cognizable", "non-cognizable")}
                                {yesNo(res.offence.compoundable, "compoundable", "non-compoundable")}
                                {res.offence.prohibitory && <Chip tone="warn">prohibitory clause (s.497(1))</Chip>}
                                <Chip tone={res.confidence === "verify" ? "warn" : "neutral"}>{res.confidence === "verify" ? "verify classification" : "established"}</Chip>
                            </div>
                        </div>
                        <div className="lb-steps">
                            <b>{res.guidance.summary}</b>
                            {res.guidance.sections?.length > 0 && (
                                <div className="lb-chips">{res.guidance.sections.map((s, i) => <Chip key={i} tone="neutral">{s}</Chip>)}</div>
                            )}
                            <ol>{res.guidance.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                        </div>
                        {res.offence.note && <div className="lt-warn">{res.offence.note}</div>}
                        <div className="lt-note">{res.legal_basis}</div>
                        <div className="lt-note" style={{ fontSize: 11.5 }}>{res.disclaimer}</div>
                    </>) : (<>
                        <div className="lb-steps">
                            <b>{res.guidance.summary}</b>
                            <ol>{res.guidance.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
                        </div>
                        <div className="lt-note">{res.general_rule?.text}</div>
                        <div className="lt-note" style={{ fontSize: 11.5 }}>{res.disclaimer}</div>
                    </>)}
                </section>
            )}
        </div>
    );
}

/* ── Court fee ────────────────────────────────────────────────────────── */
const SUIT_TYPES = [
    ["money_recovery", "Recovery of money (ad valorem)"],
    ["specific_performance", "Specific performance (ad valorem)"],
    ["declaration_with_consequential", "Declaration + consequential relief"],
    ["declaration_simple", "Simple declaration (fixed)"],
    ["injunction", "Injunction (fixed)"],
    ["family", "Family suit (fixed)"],
    ["rent", "Rent / ejectment (fixed)"],
    ["appeal", "Appeal (fixed)"],
    ["writ", "Writ petition (fixed)"],
];
const PROVINCES = [["punjab", "Punjab"], ["sindh", "Sindh"], ["kp", "Khyber Pakhtunkhwa"], ["balochistan", "Balochistan"], ["islamabad", "Islamabad (ICT)"]];

function CourtFee() {
    const toast = useToast();
    const [claim, setClaim] = useState("");
    const [suit, setSuit] = useState("money_recovery");
    const [prov, setProv] = useState("punjab");
    const [res, setRes] = useState(null);
    const [busy, setBusy] = useState(false);
    const run = async () => {
        setBusy(true);
        const { data, error } = await courtFeeCalculate({ claim_value: toNum(claim), suit_type: suit, province: prov });
        setBusy(false);
        if (error || !data) return toast.show(errText(error, "Calculation failed"), "danger");
        setRes(data);
    };
    const suitLabel = SUIT_TYPES.find(([v]) => v === suit)?.[1];
    const provLabel = PROVINCES.find(([v]) => v === prov)?.[1];
    return (
        <div className="lt-grid">
            <div className="lt-card">
                <h2>Estimate the court fee</h2>
                <p className="lt-sub">Court Fees Act 1870 as applied in each province.</p>
                <label className="lt-lbl" htmlFor="cf-suit">Suit type</label>
                <select id="cf-suit" className="lt-in" value={suit} onChange={e => setSuit(e.target.value)}>
                    {SUIT_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <label className="lt-lbl" htmlFor="cf-prov">Province</label>
                <select id="cf-prov" className="lt-in" value={prov} onChange={e => setProv(e.target.value)}>
                    {PROVINCES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
                <label className="lt-lbl" htmlFor="cf-claim">Claim value (PKR)</label>
                <input id="cf-claim" className="lt-in" value={claim} onChange={e => setClaim(e.target.value)} placeholder="For ad valorem suits" />
                <button type="button" className="lt-btn lt-go" onClick={run} disabled={busy}>{busy ? "Calculating…" : "Calculate court fee"}</button>
            </div>
            <div className="lt-card flush" data-calc-result="court">
                <div className="lt-band">
                    <span className="lt-band-k">Estimated court fee</span>
                    <b className={`lt-band-v${res ? "" : " none"}`}>{res ? `Rs ${res.court_fee.toLocaleString()}` : "Rs —"}</b>
                    <span className="lt-band-s">{res ? `${res.suit_label} · ${PROVINCES.find(([v]) => v === String(res.province).toLowerCase())?.[1] || res.province}` : `${suitLabel} · ${provLabel}`}</span>
                </div>
                <div className="lt-pad">
                    {!res ? <div className="lt-hint">Fill in the suit and press <b>Calculate court fee</b>. The fee, its legal basis and what it assumes appear here.</div> : (<>
                        <div className="lt-note" style={{ marginTop: 0 }}>{res.computation === "ad_valorem" ? "Ad valorem (on the claim value)" : "Fixed fee"} · rates as of {res.effective_as_of}</div>
                        <div className="lt-text">{res.legal_basis}</div>
                        {res.assumptions?.length > 0 && <ul className="lt-list">{res.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>}
                        <div className="lt-warn">{res.verify}</div>
                    </>)}
                </div>
            </div>
        </div>
    );
}

/* ── Inheritance (Faraid) ─────────────────────────────────────────────── */
const EMPTY_HEIRS = { husband: 0, wives: 0, sons: 0, daughters: 0, father: 0, mother: 0, predeceased_sons: 0, predeceased_daughters: 0, full_brothers: 0, full_sisters: 0 };
// What each heir is called in the "chosen so far" rows, one and many.
const HEIR_NAMES = {
    husband: ["Husband", "Husband"], wives: ["Wife", "Wives"], sons: ["Son", "Sons"], daughters: ["Daughter", "Daughters"],
    father: ["Father", "Father"], mother: ["Mother", "Mother"],
    predeceased_sons: ["Predeceased son's children", "Predeceased sons' children"],
    predeceased_daughters: ["Predeceased daughter's children", "Predeceased daughters' children"],
    full_brothers: ["Full brother", "Full brothers"], full_sisters: ["Full sister", "Full sisters"],
};

function Counter({ label, sub, value, onChange, max = 20 }) {
    const on = value > 0;
    return (
        <div className={`lt-count${on ? " on" : ""}`}>
            <span>{label}{sub && <small>{sub}</small>}</span>
            <div>
                <button type="button" aria-label={`Fewer ${label}`} onClick={() => onChange(Math.max(0, value - 1))}>−</button>
                <b className={on ? "on" : ""}>{value}</b>
                <button type="button" className={on ? "plus on" : "plus"} aria-label={`More ${label}`} onClick={() => onChange(Math.min(max, value + 1))}>+</button>
            </div>
        </div>
    );
}

function Inheritance() {
    const toast = useToast();
    const [heirs, setHeirs] = useState(EMPTY_HEIRS);
    const [estate, setEstate] = useState("");
    const [res, setRes] = useState(null);
    const [busy, setBusy] = useState(false);
    const [deceased, setDeceased] = useState("");
    const [died, setDied] = useState("");
    const [desc, setDesc] = useState("");
    const pdfKey = useRef(null);   // one Idempotency-Key per request (lib/intentKey.js)
    const set = (k) => (v) => setHeirs(p => ({ ...p, [k]: v }));
    const estateNum = toNum(estate);
    const chosen = Object.entries(heirs).filter(([, n]) => n > 0);

    const run = async () => {
        if (!estateNum) return toast.show("Enter the estate value first", "warn");
        if (!Object.values(heirs).some(v => v > 0)) return toast.show("Select at least one heir", "warn");
        setBusy(true);
        const { data, error } = await inheritanceCalculate(estateNum, heirs);
        setBusy(false);
        if (error || !data) return toast.show(errText(error, "Calculation failed"), "danger");
        setRes(data);
    };
    const pdf = async () => {
        const req = { estate_value: estateNum, heirs, deceased_name: deceased, date_of_death: died, estate_description: desc };
        setBusy(true);
        const { data, error } = await inheritanceSettlementPdf(req, keyForIntent(pdfKey, req));
        setBusy(false);
        if (error || !data?.doc_id) return toast.show(errText(error, "PDF failed"), "danger");
        await downloadDocumentFile(data.doc_id, "inheritance-share-statement", { revisionId: data.revision_id, expectedPdfSha256: data.pdf_sha256 });
        toast.show("Share statement downloaded", "success");
    };

    return (
        <div className="lt-grid">
            <div className="lt-card">
                <h2>Surviving heirs</h2>
                <p className="lt-sub">Sunni (Hanafi) rules as applied in Pakistan, incl. MFLO 1961 s.4.</p>
                <div className="lt-heirs">
                    <Counter label="Husband" value={heirs.husband} max={1} onChange={v => setHeirs(p => ({ ...p, husband: v, wives: v ? 0 : p.wives }))} />
                    <Counter label="Wives" value={heirs.wives} max={4} onChange={v => setHeirs(p => ({ ...p, wives: v, husband: v ? 0 : p.husband }))} />
                    <Counter label="Sons" value={heirs.sons} onChange={set("sons")} />
                    <Counter label="Daughters" value={heirs.daughters} onChange={set("daughters")} />
                    <Counter label="Father" value={heirs.father} max={1} onChange={set("father")} />
                    <Counter label="Mother" value={heirs.mother} max={1} onChange={set("mother")} />
                    <Counter label="Full brothers" value={heirs.full_brothers} onChange={set("full_brothers")} />
                    <Counter label="Full sisters" value={heirs.full_sisters} onChange={set("full_sisters")} />
                    <Counter label="Predeceased sons" sub="left children" value={heirs.predeceased_sons} onChange={set("predeceased_sons")} />
                    <Counter label="Predeceased daughters" sub="left children" value={heirs.predeceased_daughters} onChange={set("predeceased_daughters")} />
                </div>
                <label className="lt-lbl" htmlFor="ih-estate">Total estate value (PKR)</label>
                <input id="ih-estate" className="lt-in" value={estate} onChange={e => setEstate(e.target.value)} placeholder="e.g. 10,000,000" />
                <button type="button" className="lt-btn lt-go" onClick={run} disabled={busy}>{busy ? "Calculating…" : "Calculate shares"}</button>
            </div>
            <div className="lt-card flush" data-calc-result="inheritance">
                <div className="lt-res-head">
                    <div>
                        <h2>{res ? `Distribution of Rs ${res.estate_value.toLocaleString()}` : "Distribution"}</h2>
                        <span className="lt-band-s">{res ? res.school
                            : `${chosen.length ? `${chosen.length} heir${chosen.length === 1 ? "" : "s"} chosen` : "No heirs chosen yet"}${estateNum ? ` · Rs ${estateNum.toLocaleString()}` : ""}`}</span>
                    </div>
                </div>
                <div className="lt-table flat">
                    <div className="lt-row"><span>Heir</span><span>Share</span><span>%</span><span className="lt-num">Amount</span></div>
                    {res ? res.breakdown.map((r, i) => (
                        <div key={i} className="lt-row">
                            <span style={{ fontWeight: 600 }}>{r.heir}{r.note && <div className="lt-note" style={{ marginTop: 2, fontWeight: 400 }}>{r.note}</div>}</span>
                            <span style={{ color: "var(--brand-text)", fontWeight: 700 }}>{r.fraction}</span>
                            <span>{r.percentage}%</span>
                            <span className="lt-num">Rs {r.amount.toLocaleString()}</span>
                        </div>
                    )) : chosen.map(([k, n]) => (
                        // Before the calculation: who is in, nothing invented.
                        <div key={k} className="lt-row pending" data-pending-heir={k}>
                            <span style={{ fontWeight: 600, color: "var(--ink)" }}>{HEIR_NAMES[k][n === 1 ? 0 : 1]}{n > 1 ? ` (${n})` : ""}</span>
                            <span>—</span><span>—</span><span className="lt-num">—</span>
                        </div>
                    ))}
                </div>
                <div className="lt-pad">
                    {!res ? <div className="lt-hint">{chosen.length ? <>Press <b>Calculate shares</b> to see each heir's share.</> : "Choose the surviving heirs on the left; they appear here as you add them."}</div> : (<>
                        {res.notes?.map((n, i) => <div key={i} className="lt-note">• {n}</div>)}
                        {res.warnings?.map((w, i) => <div key={i} className="lt-warn">{w}</div>)}
                        <label className="lt-lbl" style={{ marginTop: 16 }}>For the share statement (optional)</label>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            <input className="lt-in" value={deceased} onChange={e => setDeceased(e.target.value)} placeholder="Deceased's name" aria-label="Deceased's name" />
                            <input className="lt-in" value={died} onChange={e => setDied(e.target.value)} placeholder="Date of death" aria-label="Date of death" />
                        </div>
                        <input className="lt-in" style={{ marginTop: 8 }} value={desc} onChange={e => setDesc(e.target.value)} placeholder="Estate description, e.g. house in Gulberg, bank deposits" aria-label="Estate description" />
                        <button type="button" className="lt-btn teal" style={{ marginTop: 12 }} onClick={pdf} disabled={busy}>Download share statement (PDF)</button>
                        <div className="lt-note" style={{ fontSize: 11.5 }}>{res.disclaimer}</div>
                    </>)}
                </div>
            </div>
        </div>
    );
}

/* ── Labour dues ──────────────────────────────────────────────────────── */
function LabourDues() {
    const toast = useToast();
    const [f, setF] = useState({ monthly_wage: "", years_of_service: "", extra_months: "", unpaid_months: "", overtime_hours: "", terminated_without_notice: false });
    const [res, setRes] = useState(null);
    const [busy, setBusy] = useState(false);
    const set = (k) => (e) => setF(p => ({ ...p, [k]: e.target.value }));
    const run = async () => {
        if (!toNum(f.monthly_wage)) return toast.show("Enter the monthly wage", "warn");
        setBusy(true);
        const { data, error } = await labourDuesCalculate({
            monthly_wage: toNum(f.monthly_wage), years_of_service: toNum(f.years_of_service), extra_months: toNum(f.extra_months),
            unpaid_months: toNum(f.unpaid_months), overtime_hours: toNum(f.overtime_hours), terminated_without_notice: f.terminated_without_notice,
        });
        setBusy(false);
        if (error || !data) return toast.show(errText(error, "Calculation failed"), "danger");
        setRes(data);
    };
    const field = (k, label, ph = "0") => (
        <div><label className="lt-lbl" htmlFor={`ld-${k}`}>{label}</label><input id={`ld-${k}`} className="lt-in" value={f[k]} onChange={set(k)} placeholder={ph} /></div>
    );
    const wage = toNum(f.monthly_wage);
    return (
        <div className="lt-grid">
            <div className="lt-card">
                <h2>Employee's dues</h2>
                <p className="lt-sub">Gratuity, unpaid wages, overtime and notice pay.</p>
                {field("monthly_wage", "Monthly wage (PKR)", "e.g. 50,000")}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {field("years_of_service", "Years of service")}
                    {field("extra_months", "Extra months")}
                    {field("unpaid_months", "Unpaid months")}
                    {field("overtime_hours", "Overtime hours")}
                </div>
                <label className="lt-check">
                    <input type="checkbox" checked={f.terminated_without_notice} onChange={e => setF(p => ({ ...p, terminated_without_notice: e.target.checked }))} />
                    Terminated without notice
                </label>
                <button type="button" className="lt-btn lt-go" onClick={run} disabled={busy}>{busy ? "Calculating…" : "Calculate dues"}</button>
            </div>
            <div className="lt-card flush" data-calc-result="labour">
                <div className="lt-band">
                    <span className="lt-band-k">Total owed</span>
                    <b className={`lt-band-v${res ? "" : " none"}`}>{res ? `Rs ${res.total.toLocaleString()}` : "Rs —"}</b>
                    {wage > 0 && <span className="lt-band-s">Rs {wage.toLocaleString()} a month</span>}
                </div>
                {!res ? <div className="lt-pad"><div className="lt-hint">Enter the employment details and press <b>Calculate dues</b>. Each amount owed appears here under the total.</div></div> : (<>
                    <div className="lt-table flat">
                        <div className="lt-row two"><span>Item</span><span className="lt-num">Amount</span></div>
                        {res.breakdown.map((r, i) => (
                            <div key={i} className="lt-row two"><span>{r.item}</span><span className="lt-num">Rs {r.amount.toLocaleString()}</span></div>
                        ))}
                    </div>
                    <div className="lt-pad">
                        <div className="lt-text">{res.legal_basis}</div>
                        {res.remedy && <div className="lt-info">{res.remedy}</div>}
                        <div className="lt-note" style={{ fontSize: 11.5 }}>{res.disclaimer}</div>
                    </div>
                </>)}
            </div>
        </div>
    );
}

/* ── Pages ────────────────────────────────────────────────────────────── */
function BailCheckerPage() {
    return (
        <Shell center title="Is it bailable?" sub="Type a section or an offence. Answers appear as you type, with the bail steps before or after arrest.">
            <BailChecker />
        </Shell>
    );
}

const CALCS = [
    ["court", "Court fee", "M12 3v18M7 21h10M3 7h18M6 7l-3 7a3 3 0 0 0 6 0zM18 7l-3 7a3 3 0 0 0 6 0z"],
    ["inheritance", "Inheritance", "M9 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM3 21v-2a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v2M16 3.5a3 3 0 0 1 0 6M21 21v-2a4 4 0 0 0-3-3.9"],
    ["labour", "Labour dues", "M3 7h18v13H3zM8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
];
function CalculatorsPage() {
    const [tab, setTab] = useState("court");
    const body = useMemo(() => ({ court: <CourtFee />, inheritance: <Inheritance />, labour: <LabourDues /> }), []);
    return (
        <Shell title="Calculators" sub="Court fee, Islamic inheritance shares and labour dues. Each one shows the rule it applies."
            tabs={CALCS} tab={tab} setTab={setTab}>
            {body[tab]}
        </Shell>
    );
}

export { BailCheckerPage, CalculatorsPage };
