'use client';
// Lawyer — Overseas Property Disputes inbox.
// Read/handoff only: a client sends a dispute's case brief here; the lawyer opens
// the full brief (eligibility, grievance, intake, jurisdiction) and downloads the
// draft petition when one exists. No fee negotiation, engagement letter or payment —
// that is the separate hiring flow.
//
// 2026-11-27: the app's theme (pageShell.js), full width, the inbox as a table.
// What is shown and every rule about the petition are unchanged.
import { useState, useEffect, useCallback } from "react";
import { useTheme } from "./theme.js";
import { disputeLawyerInbox, disputeBrief, downloadDocumentFile } from "@/lib/api.js";
import { DRAFTING_TOKENS_CSS, draftingMode } from "./draftingTheme.js";
import { LX_PAGE_CSS } from "./pageShell.js";

const STATE_META = {
    ready_for_drafting: { label: "Ready to draft", tone: "" },
    held_for_lawyer_triage: { label: "Held for your review", tone: "gold" },
};
const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "";
const COLS = "minmax(0,1.6fr) minmax(0,1fr) 150px minmax(0,1.3fr) 110px";

function Field({ label, value }) {
    return (
        <div style={{ marginBottom: 12, minWidth: 140 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--faint)", marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 14, color: "var(--ink)" }}>{value || "—"}</div>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <div style={{ padding: "16px 20px", borderTop: "1px solid var(--line)" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)", marginBottom: 10 }}>{title}</div>
            {children}
        </div>
    );
}

export function DisputesInboxPage() {
    const { t: T } = useTheme();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [brief, setBrief] = useState(null);
    const [openingId, setOpeningId] = useState(null);
    const [busyDoc, setBusyDoc] = useState(false);
    const [toast, setToast] = useState(null);
    const showToast = (m) => { setToast(m); setTimeout(() => setToast(null), 3000); };

    const reload = useCallback(() => {
        setLoading(true);
        disputeLawyerInbox().then(({ data }) => {
            if (Array.isArray(data)) setItems(data);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);
    useEffect(() => { reload(); }, [reload]);

    const openBrief = async (id) => {
        setOpeningId(id); setBrief(null);
        const { data, error } = await disputeBrief(id);
        setOpeningId(null);
        if (error || !data || data.error) return showToast("❌ Could not load the case brief");
        setBrief(data);
    };

    // Only a petition that was actually SHARED with this lawyer can be opened:
    // sharing is what grants the reviewer access. `shared_with_lawyer` is the
    // server's record of whether that succeeded (`petition_shared`). Anything
    // but an explicit `true` — false, missing, malformed — means no download.
    const petitionShared = brief?.petition?.shared_with_lawyer === true;

    const downloadPetition = async () => {
        if (!petitionShared || !brief?.petition?.document_id) return;
        setBusyDoc(true);
        // The revision that was shared with this lawyer. A V2 petition has no
        // legacy file, and the V2 route authorises the reviewer only for the
        // revision put in front of them. None on a legacy petition, which then
        // takes the legacy route exactly as before.
        await downloadDocumentFile(brief.petition.document_id, "special-court-petition", {
            revisionId: brief.petition.revision_id || null,
            expectedPdfSha256: brief.petition.pdf_sha256 || null,
        });
        setBusyDoc(false);
    };

    const shell = (children) => (
        <div data-lx-page data-disputes data-drafting-theme data-mode={draftingMode(T)} data-lenis-prevent>
            <style>{`${DRAFTING_TOKENS_CSS}\n${LX_PAGE_CSS}`}</style>
            {children}
            {toast && <div className="lx-toast" role="status">{toast}</div>}
        </div>
    );

    // ── Brief detail view ────────────────────────────────────────────────────
    if (brief) {
        const g = brief.grievance || {}, j = brief.jurisdiction || {}, ik = brief.intake || {}, el = brief.eligibility || {};
        const sm = STATE_META[brief.state] || { label: brief.state, tone: "muted" };
        return shell(<>
            <div className="lx-crumbs">Practice / Overseas disputes / <b>Case brief</b></div>
            <div className="lx-head">
                <div>
                    <h1>Property dispute — case brief</h1>
                    <p>From {brief.client?.name || "an overseas Pakistani client"} · sent {fmtDate(brief.assignment?.sent_at)}</p>
                </div>
                <div className="lx-head-end">
                    <span className={`lx-tag ${sm.tone}`}>{sm.label}</span>
                    <button type="button" className="lx-btn fill" onClick={() => setBrief(null)}>Back to inbox</button>
                </div>
            </div>

            {(brief.hold_reasons || []).length > 0 && (
                <section className="lx-card lx-pad" style={{ borderColor: "color-mix(in srgb, var(--gold) 45%, var(--line))" }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "var(--gold)" }}>Held for your review because:</div>
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                        {brief.hold_reasons.map((r, i) => <li key={i} style={{ fontSize: 13.5, color: "var(--muted)", marginBottom: 4 }}>{r}</li>)}
                    </ul>
                </section>
            )}

            <section className="lx-card lx-flush">
                <Section title="Overseas-Pakistani eligibility">
                    <Field label="Qualifies" value={el.eligible ? "Yes" : "Not established"} />
                    {(el.reasons || []).length > 0 && <Field label="Notes" value={el.reasons.join(" ")} />}
                </Section>

                <Section title="Grievance classification">
                    <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <Field label="Type" value={g.category_label || g.category} />
                        <Field label="Confidence" value={g.confidence} />
                        <Field label="Needs triage" value={g.needs_triage ? "Yes — ambiguous" : "No — clear"} />
                    </div>
                    {(g.alternatives || []).length > 0 && <Field label="Other possibilities" value={g.alternatives.join(", ")} />}
                    {g.reasoning && <Field label="Reasoning" value={g.reasoning} />}
                </Section>

                <Section title="The facts (as entered)">
                    <Field label="Property" value={ik.property_description} />
                    <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <Field label="Opposing party" value={ik.opposing_party + (ik.opposing_party_relation ? ` (${ik.opposing_party_relation})` : "")} />
                        <Field label="Khasra / registry" value={ik.khasra_number} />
                    </div>
                    <Field label="Timeline" value={ik.timeline} />
                    <Field label="Documents held" value={(ik.documents_held || []).join(", ")} />
                    <Field label="Relief sought" value={ik.relief_wanted} />
                </Section>

                <Section title="Jurisdiction (Special Court, 2024 Act)">
                    <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <Field label="Province" value={j.province} />
                        <Field label="Court status" value={j.court_status} />
                        <Field label="Appeal window" value={j.appeal_days ? `${j.appeal_days} days` : "confirm with court"} />
                        <Field label="Disposal" value={j.disposal_days ? `${j.disposal_days} days (from leave to defend)` : "—"} />
                    </div>
                </Section>

                <Section title="Draft petition">
                    {brief.petition && petitionShared ? (
                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <button type="button" className="lx-btn mint" onClick={downloadPetition} disabled={busyDoc}>
                                {busyDoc ? "Downloading…" : "⤓ Download draft petition (PDF)"}
                            </button>
                            <span style={{ fontSize: 13, color: "var(--muted)" }}>Drafted {fmtDate(brief.petition.drafted_at)} — a DRAFT for you to review, complete and file.</span>
                        </div>
                    ) : brief.petition ? (
                        // Drafted, but the share did not go through — so the
                        // download would be refused. Say so; offer nothing.
                        <div data-petition-state="not-shared" style={{ fontSize: 13.5, color: "var(--muted)" }}>A petition was drafted, but it has not been shared with you, so it cannot be opened here.</div>
                    ) : (
                        <div style={{ fontSize: 13.5, color: "var(--muted)" }}>No petition drafted — this dispute was held for your review before drafting.</div>
                    )}
                </Section>
            </section>
        </>);
    }

    // ── Inbox list ───────────────────────────────────────────────────────────
    return shell(<>
        <div className="lx-crumbs">Practice / <b>Overseas disputes</b></div>
        <div className="lx-head">
            <div>
                <h1>Overseas property disputes</h1>
                <p>Case briefs that overseas Pakistanis send you. Open one to see the whole case in one place.</p>
            </div>
        </div>

        <section className="lx-card lx-flush" aria-label="Case briefs" data-disputes-list>
            <div className="lx-cols" style={{ gridTemplateColumns: COLS }}>
                <span>Brief</span><span>Province</span><span>Received</span><span>Status</span><span style={{ textAlign: "right" }}>Action</span>
            </div>
            {loading ? (
                <div className="lx-empty-row"><span style={{ color: "var(--muted)" }}>Loading…</span></div>
            ) : items.length === 0 ? (
                <div className="lx-empty">
                    <span className="lx-tile" aria-hidden="true">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11l9-8 9 8v10H3z" /><path d="M9 21v-6h6v6" /></svg>
                    </span>
                    <b>No case briefs yet</b>
                    <span className="t">When an overseas client sends you a property dispute, it appears here with everything they shared.</span>
                </div>
            ) : items.map(d => {
                const sm = STATE_META[d.state] || { label: d.state, tone: "muted" };
                return (
                    <div key={d.dispute_id} className="lx-row" data-dispute={d.dispute_id} style={{ gridTemplateColumns: COLS }}>
                        <b style={{ fontSize: 14.5, minWidth: 0 }}>{d.category_label || "Property dispute"}</b>
                        <span style={{ color: "var(--muted)" }}>{d.province || "—"}</span>
                        <span style={{ color: "var(--muted)" }}>{fmtDate(d.sent_at)}</span>
                        <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            <span className={`lx-tag ${sm.tone}`}>{sm.label}</span>
                            {d.has_petition && <span className="lx-tag teal">Petition ready</span>}
                        </span>
                        <span style={{ textAlign: "right" }}>
                            <button type="button" className="lx-btn teal sm" onClick={() => openBrief(d.dispute_id)} disabled={openingId === d.dispute_id}>
                                {openingId === d.dispute_id ? "Opening…" : "Open"}
                            </button>
                        </span>
                    </div>
                );
            })}
        </section>
    </>);
}
