'use client';
// Case Law Research — semantic search over the LHC judgment corpus plus a
// citator: "which judgments cite PLD 2019 SC 675?" Every result links to the
// court's original PDF.
//
// 2026-11-27: the app's theme (pageShell.js), full width, and ONE search box
// with two modes instead of two separate boxes. The search, the citator and
// the hand-over from the AI Assistant work exactly as before.
import { useEffect, useState } from "react";
import { useTheme, useCase } from "./theme.js";
import { useToast } from "@/components/lawyer/Toast.jsx";
import { citatorSearch, citatorCitedBy, citatorStats } from "@/lib/api.js";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { LX_PAGE_CSS } from "./pageShell.js";

const TRY = [
    "Specific performance of an oral agreement",
    "Pre-arrest bail, malafide of the complainant",
    "Ejectment for default in rent",
];

function JudgmentRow({ j, onCiteClick }) {
    return (
        <div data-judgment={j.id} style={{ padding: "16px 20px", borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 240 }}>
                    <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", lineHeight: 1.45 }}>
                        {j.title || j.case_no || j.id}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 3 }}>
                        {[j.case_no, j.judge, j.id].filter(Boolean).join(" · ")}
                        {typeof j.score === "number" && <span style={{ color: "var(--brand-text)", fontWeight: 700 }}> · {(j.score * 100).toFixed(0)}% match</span>}
                    </div>
                </div>
                <a href={j.pdf_url} target="_blank" rel="noopener noreferrer" className="lx-btn teal sm">Court PDF ↗</a>
            </div>
            {(j.tag_line || j.snippet) && (
                <div style={{ fontSize: 13.5, color: "var(--muted)", lineHeight: 1.6, marginTop: 8 }}>
                    {j.tag_line || j.snippet}
                </div>
            )}
            {j.citations_out?.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 10 }}>
                    <span style={{ fontSize: 12, color: "var(--faint)", fontWeight: 700 }}>Cites</span>
                    {j.citations_out.slice(0, 8).map(c => (
                        <button key={c} type="button" className="lx-chip" onClick={() => onCiteClick(c)} title={`Who else cites ${c}?`}>
                            {c}
                        </button>
                    ))}
                    {j.citations_out.length > 8 && <span style={{ fontSize: 12, color: "var(--faint)" }}>+{j.citations_out.length - 8} more</span>}
                </div>
            )}
        </div>
    );
}

function CaseLawPage() {
    const { t } = useTheme();
    const { setPage } = useCase();
    const toast = useToast();
    const [stats, setStats] = useState(null);
    const [mode, setMode] = useState("search"); // search | citedby
    const [q, setQ] = useState("");
    const [cite, setCite] = useState("");
    const [results, setResults] = useState(null);
    const [citedBy, setCitedBy] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => { citatorStats().then(({ data }) => { if (data) setStats(data); }); }, []);

    // "Open in Legal library" from the AI Assistant's Sources panel: one
    // citation, handed over once and searched straight away.
    useEffect(() => {
        let term = "";
        try {
            term = sessionStorage.getItem("attorney:caselaw-query") || "";
            sessionStorage.removeItem("attorney:caselaw-query");
        } catch { /* storage off */ }
        if (term) { setQ(term); runSearch(term); }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // `term` is a handed-over search; a click passes an event, so fall back to q.
    const runSearch = async (given) => {
        const term = typeof given === "string" ? given : q;
        if (!term.trim() || busy) return;
        setBusy(true); setMode("search"); setCitedBy(null);
        const { data, error } = await citatorSearch(term.trim());
        setBusy(false);
        if (error) { toast.show("❌ " + (error.message || "Search failed"), "error", 3000); return; }
        setResults(Array.isArray(data) ? data : []);
    };

    const runCitedBy = async (citation) => {
        setBusy(true); setMode("citedby"); setResults(null);
        setCite(citation);
        const { data, error } = await citatorCitedBy(citation);
        setBusy(false);
        if (error) { toast.show("❌ " + (error.message || "Lookup failed"), "error", 3000); return; }
        setCitedBy(data);
    };

    const searching = mode === "search";
    const value = searching ? q : cite;
    const go = () => (searching ? runSearch() : (cite.trim() && runCitedBy(cite.trim())));
    const emptyLibrary = stats && stats.judgments === 0;

    return (
        <div data-lx-page data-caselaw data-drafting-theme data-mode={draftingMode(t)} data-lenis-prevent>
            <style>{`${DRAFTING_TOKENS_CSS}\n${LX_PAGE_CSS}`}</style>
            <div className="lx-crumbs">Research / <b>Legal Library</b></div>
            <div className="lx-head">
                <div>
                    <h1>Case law</h1>
                    <p>Reported judgments of the Lahore High Court, with links to the court's own PDFs.</p>
                </div>
                {stats && (
                    <div className="lx-head-end" data-caselaw-stats>
                        <span className="lx-pill"><b>{stats.judgments}</b> judgments</span>
                        <span className="lx-pill"><b>{stats.citation_edges}</b> citation links</span>
                    </div>
                )}
            </div>

            <section className="lx-card lx-pad" aria-label="Search">
                <div role="tablist" aria-label="Search mode" className="lx-seg">
                    <button type="button" role="tab" aria-selected={searching} onClick={() => setMode("search")}>Search judgments</button>
                    <button type="button" role="tab" aria-selected={!searching} onClick={() => setMode("citedby")}>Who cites this?</button>
                </div>
                <div style={{ display: "flex", gap: 10 }}>
                    <label className="lx-search">
                        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
                        <span className="lx-sr">{searching ? "Search judgments" : "Citation"}</span>
                        <input value={value} className={searching ? undefined : "mono"}
                            onChange={e => (searching ? setQ(e.target.value) : setCite(e.target.value))}
                            onKeyDown={e => e.key === "Enter" && go()}
                            placeholder={searching ? "Describe the point of law, e.g. post-arrest bail in narcotics cases" : "A citation, e.g. 1996 SCMR 1544 or PLD 2019 SC 675"} />
                    </label>
                    <button type="button" className="lx-btn mint" style={{ height: 38, padding: "0 16px", fontSize: 13 }} onClick={go} disabled={!value.trim() || busy}>
                        {busy ? (searching ? "Searching…" : "Looking…") : searching ? "Search" : "Find citing judgments"}
                    </button>
                </div>
                {searching && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 13, color: "var(--faint)" }}>Try</span>
                        {TRY.map(x => <button key={x} type="button" className="lx-chip" onClick={() => { setQ(x); runSearch(x); }}>{x}</button>)}
                    </div>
                )}
            </section>

            <section className="lx-card lx-flush" aria-label="Results" data-caselaw-results>
                {mode === "search" && results !== null ? (<>
                    <div className="lx-card-head"><b>Results</b><span className="lx-count">{results.length}</span></div>
                    {results.length === 0 && <div className="lx-empty-row"><span className="t" style={{ color: "var(--muted)" }}>Nothing matched. Try different wording.</span></div>}
                    {results.map(j => <JudgmentRow key={j.id} j={j} onCiteClick={runCitedBy} />)}
                </>) : mode === "citedby" && citedBy !== null ? (<>
                    <div className="lx-card-head" style={{ flexWrap: "wrap" }}>
                        <span className="lx-mono">{citedBy.citation}</span>
                        <span style={{ color: "var(--muted)" }}>is cited by <b style={{ color: "var(--ink)" }}>{citedBy.count}</b> judgment{citedBy.count === 1 ? "" : "s"} in the library</span>
                    </div>
                    {citedBy.cited_by.length === 0 && <div className="lx-empty-row"><span style={{ color: "var(--muted)" }}>No citing judgments found yet. The library grows with every import.</span></div>}
                    {citedBy.cited_by.map(j => <JudgmentRow key={j.id} j={j} onCiteClick={runCitedBy} />)}
                </>) : (
                    <div className="lx-empty" data-caselaw-empty={emptyLibrary ? "library" : "idle"}>
                        <span className="lx-tile" aria-hidden="true">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l9 5H3z" /></svg>
                        </span>
                        {emptyLibrary ? (<>
                            <b>No judgments in the library yet</b>
                            <span className="t">A search returns nothing until judgments are added. For a point of law now, ask the AI Assistant.</span>
                            {setPage && <button type="button" className="lx-btn teal" style={{ marginTop: 6 }} onClick={() => setPage("ai-legal")}>Open AI Assistant</button>}
                        </>) : (<>
                            <b>Search the judgments</b>
                            <span className="t">Describe the point of law, or switch to "Who cites this?" and enter a citation.</span>
                        </>)}
                    </div>
                )}
            </section>
        </div>
    );
}

export { CaseLawPage };
