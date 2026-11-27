'use client';
// Cause List Watcher — the munshi's evening job, automated.
// Watch a court case number; the backend checks the LHC cause list on a
// schedule (and on demand) and matched listings land here + as notifications.
import { useEffect, useState } from "react";
import { useTheme } from "./theme.js";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { LX_PAGE_CSS } from "./pageShell.js";
import { Icon, I } from "./icons.jsx";
import { useToast } from "@/components/lawyer/Toast.jsx";
import {
    createCauselistWatch, listCauselistWatches, deleteCauselistWatch,
    checkCauselist, listCauselistEntries, matchCauselistText,
} from "@/lib/api.js";

const fmtDate = (iso) => iso
    ? new Date(iso + "T00:00:00").toLocaleDateString("en-PK", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    : "—";

function shareEntryOnWhatsApp(e) {
    const lines = [
        "⚖️ Cause List Alert — Attorney.AI",
        "",
        `Case: ${e.case_no}${e.title ? ` — ${e.title}` : ""}`,
        `Listed: ${fmtDate(e.hearing_date)}`,
        e.judge ? `Court: ${e.judge}` : null,
        e.court_room ? `Room: ${e.court_room}` : null,
        e.seq ? `Serial #: ${e.seq}` : null,
        e.list_type ? `List: ${e.list_type}` : null,
    ].filter(Boolean).join("\n");
    window.open(`https://wa.me/?text=${encodeURIComponent(lines)}`, "_blank", "noopener,noreferrer");
}

function CauselistPage() {
    const { t } = useTheme();
    const toast = useToast();
    const [watches, setWatches] = useState([]);
    const [entries, setEntries] = useState([]);
    const [caseNo, setCaseNo] = useState("");
    const [titleHint, setTitleHint] = useState("");
    const [adding, setAdding] = useState(false);
    const [checking, setChecking] = useState(false);
    const [pasteText, setPasteText] = useState("");
    const [pasteHits, setPasteHits] = useState(null);
    const [matching, setMatching] = useState(false);

    const refresh = async () => {
        const [w, e] = await Promise.all([listCauselistWatches(), listCauselistEntries()]);
        if (Array.isArray(w.data)) setWatches(w.data);
        if (Array.isArray(e.data)) setEntries(e.data);
    };
    useEffect(() => { refresh(); }, []);

    const addWatch = async () => {
        if (!caseNo.trim() || adding) return;
        setAdding(true);
        const { error } = await createCauselistWatch({ case_no: caseNo.trim(), title_hint: titleHint.trim() });
        setAdding(false);
        if (error) { toast.show("❌ " + (error.message || "Could not add watch"), "error", 3500); return; }
        setCaseNo(""); setTitleHint("");
        toast.show("✅ Watching — we'll alert you when it's listed", "success", 3000);
        refresh();
    };

    const removeWatch = async (id) => {
        const { error } = await deleteCauselistWatch(id);
        if (error) { toast.show("❌ " + (error.message || "Delete failed"), "error", 3000); return; }
        refresh();
    };

    const checkNow = async () => {
        if (checking) return;
        setChecking(true);
        const { data, error } = await checkCauselist();
        setChecking(false);
        if (error) { toast.show("❌ " + (error.message || "Check failed"), "error", 4000); return; }
        const n = data?.new_entries?.length || 0;
        const errs = data?.source_errors || 0;
        toast.show(
            n > 0 ? `📋 ${n} new listing${n === 1 ? "" : "s"} found!`
                : errs > 0 ? "⚠️ Court website unreachable — try again shortly"
                    : "✓ Checked — no new listings",
            n > 0 ? "success" : errs > 0 ? "warn" : "info", 3500,
        );
        refresh();
    };

    const runPasteMatch = async () => {
        if (!pasteText.trim() || matching) return;
        setMatching(true);
        const { data, error } = await matchCauselistText(pasteText);
        setMatching(false);
        if (error) { toast.show("❌ " + (error.message || "Match failed"), "error", 3000); return; }
        setPasteHits(Array.isArray(data) ? data : []);
    };

    const listDay = (iso) => iso ? new Date(iso + "T00:00:00") : null;
    const COLS = "120px minmax(0,1fr) minmax(0,1fr) 90px";

    // 2026-11-27: the app's theme (pageShell.js), full width; listings first,
    // watched cases in a right rail. The data and every handler are unchanged.
    return (
        <div data-lx-page data-causelist data-drafting-theme data-mode={draftingMode(t)} data-lenis-prevent>
            <style>{`${DRAFTING_TOKENS_CSS}\n${LX_PAGE_CSS}`}</style>
            <div className="lx-crumbs">Practice / <b>Cause lists</b></div>
            <div className="lx-head">
                <div>
                    <h1>Cause lists</h1>
                    <p>Lahore High Court benches (Principal Seat, Multan, Bahawalpur, Rawalpindi) are checked every few hours. You're told when a watched case is listed.</p>
                </div>
                <div className="lx-head-end">
                    <button type="button" className="lx-btn teal" onClick={checkNow} disabled={checking || !watches.length}
                        title={watches.length ? "Check the court's lists now" : "Watch a case first"}>
                        <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8" /><path d="M21 3v5h-5" /></svg>
                        {checking ? "Checking LHC…" : "Check now"}
                    </button>
                </div>
            </div>

            <div className="lx-split">
                <div className="lx-col">
                    {/* Upcoming listings */}
                    <section className="lx-card lx-flush" aria-label="Upcoming listings" data-listings>
                        <div className="lx-card-head"><b>Upcoming listings</b><span className="lx-count">{entries.length}</span></div>
                        <div className="lx-cols" style={{ gridTemplateColumns: COLS }}>
                            <span>Date</span><span>Case</span><span>Court</span><span style={{ textAlign: "right" }}>Share</span>
                        </div>
                        {entries.length === 0 ? (
                            <div className="lx-empty-row">
                                <span className="lx-tile" aria-hidden="true" style={{ width: 44, height: 44, borderRadius: 13 }}>
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
                                </span>
                                <div>
                                    <b style={{ fontSize: 14.5 }}>Nothing listed yet</b>
                                    <div className="lx-sub">Watch a case on the right. When it appears on a cause list, it shows here and as a notification.</div>
                                </div>
                            </div>
                        ) : entries.map(e => {
                            const d = listDay(e.hearing_date);
                            return (
                                <div key={e.id} className="lx-row" data-listing={e.id} style={{ gridTemplateColumns: COLS }}>
                                    <span title={fmtDate(e.hearing_date)}>
                                        <b style={{ display: "block", fontSize: 14 }}>{d ? d.toLocaleDateString("en-PK", { weekday: "short", day: "numeric", month: "short" }) : "—"}</b>
                                        {e.list_type && <span style={{ fontSize: 12, color: "var(--muted)" }}>{e.list_type}</span>}
                                    </span>
                                    <span style={{ minWidth: 0 }}>
                                        <span className="lx-mono">{e.case_no}</span>
                                        {e.connected && <span className="lx-tag gold" style={{ marginLeft: 8 }}>Connected matter</span>}
                                        {e.title && <span style={{ display: "block", fontSize: 13, color: "var(--muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title}</span>}
                                    </span>
                                    <span style={{ fontSize: 13, color: "var(--muted)", minWidth: 0 }}>
                                        {[e.judge, e.court_room, e.seq ? `Seq #${e.seq}` : null].filter(Boolean).join(" · ") || "—"}
                                        {e.remarks && <span style={{ display: "block", fontSize: 12, color: "var(--faint)" }}>{e.remarks}</span>}
                                    </span>
                                    <span style={{ textAlign: "right" }}>
                                        <button type="button" className="lx-btn fill sm" onClick={() => shareEntryOnWhatsApp(e)} title="Share on WhatsApp">Share</button>
                                    </span>
                                </div>
                            );
                        })}
                    </section>

                    {/* Paste fallback */}
                    <section className="lx-card lx-pad" aria-label="Paste a cause list">
                        <div>
                            <div className="lx-title">Paste a district court list</div>
                            <div className="lx-sub">Got the list on WhatsApp? Paste the text and we'll look for your watched cases in it.</div>
                        </div>
                        <label>
                            <span className="lx-sr">Cause list text</span>
                            <textarea className="lx-input" value={pasteText} onChange={e => setPasteText(e.target.value)} rows={6}
                                placeholder="Paste the cause list text here" />
                        </label>
                        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                            {pasteHits !== null && (
                                <span style={{ fontSize: 13, fontWeight: 600, color: pasteHits.length ? "var(--brand-text)" : "var(--muted)" }}>
                                    {pasteHits.length ? `${pasteHits.length} match${pasteHits.length === 1 ? "" : "es"} found` : "No watched cases in this list"}
                                </span>
                            )}
                            <button type="button" className="lx-btn mint" style={{ marginLeft: "auto" }} onClick={runPasteMatch} disabled={!pasteText.trim() || matching}>
                                {matching ? "Scanning…" : "Find my cases"}
                            </button>
                        </div>
                        {pasteHits?.length > 0 && pasteHits.map((h, i) => (
                            <div key={i} style={{ padding: "9px 12px", borderRadius: 10, background: "color-mix(in srgb, var(--brand-text) 10%, transparent)", fontSize: 13 }}>
                                <span className="lx-mono">{h.case_no}</span>
                                <span style={{ color: "var(--muted)" }}> — {h.line}</span>
                            </div>
                        ))}
                    </section>
                </div>

                {/* Watched cases */}
                <aside className="lx-card lx-pad" aria-label="Watched cases" data-watches>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span className="lx-title">Watched cases</span><span className="lx-count">{watches.length}</span>
                    </div>
                    <label className="lx-field">
                        <span>Court case number</span>
                        <input className="lx-input" value={caseNo} onChange={e => setCaseNo(e.target.value)}
                            onKeyDown={e => e.key === "Enter" && addWatch()} placeholder="As printed on the list, e.g. 39043/26" />
                    </label>
                    <label className="lx-field">
                        <span>Label <i>(optional)</i></span>
                        <input className="lx-input" value={titleHint} onChange={e => setTitleHint(e.target.value)}
                            onKeyDown={e => e.key === "Enter" && addWatch()} placeholder="e.g. Fayyaz bail matter" />
                    </label>
                    <button type="button" className="lx-btn mint" onClick={addWatch} disabled={!caseNo.trim() || adding}>
                        {adding ? "Adding…" : "Watch this case"}
                    </button>
                    <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                        {watches.length === 0 && <span style={{ fontSize: 13.5, color: "var(--muted)" }}>No cases watched yet.</span>}
                        {watches.map(w => (
                            <div key={w.id} data-watch={w.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderRadius: 12, background: "var(--surface-2)" }}>
                                <div style={{ minWidth: 0, flex: 1 }}>
                                    <span className="lx-mono">{w.case_no}</span>
                                    {w.title_hint && <span style={{ display: "block", fontSize: 12.5, color: "var(--muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.title_hint}</span>}
                                    {w.last_listed_date && <span style={{ display: "block", fontSize: 12, color: "var(--brand-text)", fontWeight: 600 }}>Listed {w.last_listed_date}</span>}
                                </div>
                                <button type="button" className="lx-btn fill sm" onClick={() => removeWatch(w.id)} title="Stop watching" aria-label={`Stop watching ${w.case_no}`}
                                    style={{ width: 34, padding: 0 }}>
                                    <Icon d={I.x} size={13} />
                                </button>
                            </div>
                        ))}
                    </div>
                </aside>
            </div>
        </div>
    );
}

export { CauselistPage };
