/* The lawyer Draft Assistant's pieces that do not need React (2026-10-14).
 *
 * WHY THIS EXISTS
 * The assistant used to REPLACE the whole editor with the model's reply
 * (`innerText = reply`), decided by guessing from the reply's length. A
 * template's centred headings, numbered "That ..." paragraphs and bold clause
 * titles were wiped by any request, even "add a confidentiality clause". Now a
 * reply is a PROPOSAL: the lawyer inserts it at the cursor, swaps it for the
 * selected text, or (asked for explicitly) replaces the draft.
 */
import { escapeHtml } from "./escapeHtml.js";

/* What the assistant returns. Mirrors DraftRequest.mode on the server. */
export const MODES = {
    clause:  { label: "Add to draft",       hint: "New clause or paragraph, inserted where your cursor is" },
    rewrite: { label: "Rewrite selection",  hint: "Select text in the draft first; only that part changes" },
    full:    { label: "Whole draft",        hint: "Rework the whole draft (replaces it only if you choose)" },
    answer:  { label: "Ask",                hint: "A question about the draft; nothing is inserted" },
};

const PETITION = [
    { label: "Add a ground", mode: "clause", text: "Add a further ground supporting the relief, as a numbered \"That …\" paragraph." },
    { label: "Stronger prayer", mode: "clause", text: "Draft a stronger and complete PRAYER section for this filing." },
    { label: "Add verification", mode: "clause", text: "Add a verification paragraph appropriate to this filing." },
    { label: "Jurisdiction para", mode: "clause", text: "Add a paragraph establishing this court's jurisdiction." },
    { label: "Improve wording", mode: "rewrite", text: "Make the selected text more precise and persuasive without changing the facts." },
    { label: "Key arguments", mode: "answer", text: "Summarise the strongest arguments for my client in this draft." },
];
const AGREEMENT = [
    { label: "Confidentiality", mode: "clause", text: "Add a confidentiality clause." },
    { label: "Dispute resolution", mode: "clause", text: "Add a dispute resolution clause (negotiation, then arbitration in Pakistan, with the courts of [city] as a fallback)." },
    { label: "Force majeure", mode: "clause", text: "Add a force majeure clause." },
    { label: "Termination", mode: "clause", text: "Add a termination clause with notice period and consequences of termination." },
    { label: "Balance for my client", mode: "rewrite", text: "Rewrite the selected clause so it better protects my client, keeping it fair and enforceable." },
    { label: "Risk review", mode: "answer", text: "List the main risks in this agreement for my client, and the clause that addresses each (or that it is missing)." },
];
const BUSINESS = [
    { label: "Add a resolution", mode: "clause", text: "Add a further board resolution in the same format." },
    { label: "Formal tone", mode: "rewrite", text: "Make the selected text more formal." },
    { label: "Missing items", mode: "answer", text: "What items does this document usually contain that are missing here?" },
];
const LETTER = [
    { label: "Formal tone", mode: "rewrite", text: "Make the selected text more formal and professional." },
    { label: "Shorter", mode: "rewrite", text: "Make the selected text shorter and clearer." },
    { label: "Add a deadline", mode: "clause", text: "Add a sentence giving a clear deadline to respond and the consequence of not responding." },
    { label: "Polish whole letter", mode: "full", text: "Polish the whole letter: clear, formal and concise, keeping all facts." },
];
const GENERAL = [
    { label: "Draft from facts", mode: "full", text: "Draft the complete document from these facts: " },
    { label: "Add a clause", mode: "clause", text: "Add a clause about " },
    { label: "Improve wording", mode: "rewrite", text: "Make the selected text more precise and formal." },
];

/* Quick actions that fit the open document: a letter has no prayer to strengthen. */
export function quickActionsFor(cat = "") {
    if (/application|petition|litigation|family/i.test(cat)) return PETITION;
    if (/agreement|contract/i.test(cat)) return AGREEMENT;
    if (/business|commercial/i.test(cat)) return BUSINESS;
    if (/notice|letter|email/i.test(cat)) return LETTER;
    return GENERAL;
}

/* The mode a request goes out in: a selection means "rewrite that"; an
   explicit choice is kept; otherwise a new clause (never a silent overwrite). */
export function modeFor({ chosen, hasSelection }) {
    if (chosen === "rewrite" && !hasSelection) return "clause";
    if (chosen) return chosen;
    return hasSelection ? "rewrite" : "clause";
}

const HEADING = /^[A-Z0-9][A-Z0-9 ,.&()'’\-–—/:]{2,90}$/;
const NUMBERED = /^(\d{1,2}[.)]|\([a-z0-9]{1,3}\)|[a-z][.)])\s+/i;
// A short numbered clause TITLE ("10. CONFIDENTIALITY", "4. Security Deposit"),
// as the templates bold "1. Premises Description" -- not a numbered paragraph
// ("1. That the Applicant ..." is long and ends with a full stop).
const CLAUSE_TITLE = /^\d{1,2}\.\s+[A-Z][^.]{2,58}[^.\s]$/;

/* The model's plain-text proposal as editor HTML, ESCAPED. Blank lines separate
   paragraphs; a short line in CAPITALS (or **bold**) is a bold heading; single
   line breaks are kept. Only tags the draft sanitiser keeps are emitted. */
export function proposalToHtml(text = "") {
    const clean = String(text).replace(/\r\n?/g, "\n").replace(/^```[a-z]*\n?|```$/gim, "").trim();
    if (!clean) return "";
    return clean.split(/\n{2,}/).map(block => {
        const lines = block.split("\n").map(l => l.trimEnd()).filter(l => l.trim());
        if (!lines.length) return "";
        const html = lines.map(line => {
            const bold = /^\*\*(.+)\*\*:?$/.exec(line.trim());
            if (bold) return `<strong>${escapeHtml(bold[1])}</strong>`;
            const t = line.trim();
            const isHeading = (HEADING.test(t) && !NUMBERED.test(t) && /[A-Z]{3}/.test(t))
                || (CLAUSE_TITLE.test(t) && !/^\d{1,2}\.\s+That\b/.test(t));
            const inline = escapeHtml(line).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
            return isHeading ? `<strong>${inline}</strong>` : inline;
        }).join("<br>");
        return `<p>${html}</p>`;
    }).join("");
}

/* ── AI-first drafting (2026-10-19) ───────────────────────────────────────
 * A whole draft written from the lawyer's description, tidied before it is
 * shown. Cosmetic only: the guard's text is never reworded.
 *   - a first line that is only the jurisdiction ("Punjab") is dropped: the
 *     jurisdiction is the assistant's setting, not the document's heading;
 *   - when the guard withheld a numbered paragraph, the remaining top-level
 *     "N." paragraphs are renumbered so the draft does not read 1, 3, 4. Only
 *     the first run counting up from 1 is touched -- a list that restarts
 *     (a prayer's own 1, 2, 3) is left exactly as written. */
const JURISDICTION_LINE = /^(punjab|sindh|khyber pakhtunkhwa|kpk|balochistan|federal|islamabad|federal \/ islamabad|pakistan)[.:]?$/i;
const TOP_NUMBER = /^(\s*)(\d{1,2})\.(\s+)/;

export function tidyFullDraft(text = "") {
    let lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    while (lines.length && !lines[0].trim()) lines.shift();
    if (lines.length > 1 && JURISDICTION_LINE.test(lines[0].trim())) {
        lines.shift();
        while (lines.length && !lines[0].trim()) lines.shift();
    }
    // The first numbered run: from its "1." up to where numbering restarts.
    const run = [];
    for (let i = 0, prev = 0; i < lines.length; i++) {
        const m = TOP_NUMBER.exec(lines[i]);
        if (!m) continue;
        const v = Number(m[2]);
        if (!run.length && v !== 1) break;
        if (run.length && v <= prev) break;
        run.push(i); prev = v;
    }
    const num = idx => Number(TOP_NUMBER.exec(lines[idx])[2]);
    const gap = run.some((idx, k) => k > 0 && num(idx) !== num(run[k - 1]) + 1);
    if (gap) run.forEach((idx, k) => { lines[idx] = lines[idx].replace(TOP_NUMBER, (_m, sp, _d, ws) => `${sp}${k + 1}.${ws}`); });
    return lines.join("\n");
}

/* The blanks still to fill: [Bracketed words] and runs of underscores. */
const PLACEHOLDER = /\[[^\]\n]{1,60}\]|_{3,}/g;
export function findPlaceholders(text = "") {
    const seen = new Map();
    for (const m of String(text).matchAll(PLACEHOLDER)) {
        const key = m[0].startsWith("_") ? "___" : m[0];
        seen.set(key, (seen.get(key) || 0) + 1);
    }
    return [...seen].map(([label, count]) => ({ label, count }));
}

/* A short title from a whole draft: its Subject line, else a line that names
 * the kind of document, else its first heading-like line. (A letter starts
 * with the sender's name -- that is not a title.) */
const DOC_KIND = /\b(notice|petition|application|plaint|affidavit|agreement|deed|reply|suit|appeal|complaint|undertaking|power of attorney|contract|memorandum|statement)\b/i;
const shorten = (t, max = 70) => (t.length <= max ? t : `${t.slice(0, max).replace(/\s+\S*$/, "")}…`);
export function draftTitle(text = "") {
    const all = String(text).split("\n").map(l => l.replace(/\*\*/g, "").trim()).filter(Boolean);
    const subject = all.map(l => /^(subject|re)\s*:\s*(.+)$/i.exec(l)).find(Boolean);
    if (subject && !/[[\]_]/.test(subject[2])) return shorten(subject[2].trim());
    const kind = all.find(l => l.length <= 70 && DOC_KIND.test(l) && !/^\d/.test(l) && !/[[\]_]/.test(l));
    if (kind) return titleCase(kind);
    for (const raw of String(text).split("\n")) {
        const t = raw.replace(/\*\*/g, "").trim();
        if (!t || /^\d/.test(t) || /^(to|from|date|subject|sir|madam)\b/i.test(t)) continue;
        if (t.length > 70 || JURISDICTION_LINE.test(t) || /[[\]_]/.test(t)) continue;
        return titleCase(t);
    }
    return "";
}
function titleCase(t) {
    // An all-caps heading is re-cased; a heading already in mixed case is kept.
    if (t !== t.toUpperCase()) return t;
    return t.toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
        .replace(/\b(Of|And|The|To|For|In|On|Under)\b/g, w => w.toLowerCase()).replace(/^./, c => c.toUpperCase());
}
