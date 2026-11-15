/* The lawyer drafter's starting points.
 *
 * WHY THE CATALOGUE WAS SHORT, AND WHAT CHANGED
 *
 * It once advertised fourteen document types of which only two had a body of
 * their own; the rest opened the same generic court-petition scaffold with the
 * card's title pasted on top. Those cards were removed: a card exists only when
 * it opens its own document.
 *
 * 2026-10-14: 24 templates with real bodies were added from the reference
 * library (lawyerTemplateLibrary.js, GENERATED -- see the generator named in its
 * header). Their Word formatting is kept: centred bold court headings, numbered
 * "That ..." paragraphs, bold clause headings, nested lists. The generator
 * corrects the legal errors found in the reference text (Dissolution under
 * DMMA 1939 s.2, not MFLO s.7; the Guardians and Wards Act; FIR registration
 * under CrPC s.22-A(6); plaint valuation and verification). They are starting
 * points: a lawyer reviews each before filing.
 *
 * Kept out of the component so it can be tested by import. */
import { escapeHtml } from "./escapeHtml.js";
import { LIBRARY } from "./lawyerTemplateLibrary.js";

export const BLANK_TEMPLATE = {
    id: 0,
    name: "Blank legal draft",
    cat: "General",
    // The law a card names: taken from what the body itself is drafted under.
    law: "Generic scaffold — no statute",
    desc: "A generic court-filing scaffold — introduction, facts, grounds, prayer. Not specific to any instrument; adapt it yourself.",
    icon: "📄",
    popular: false,
};

// The plaint is the instrument the pleading-requirements rules are keyed by.
const TEMPLATE_TYPE = { 2: "plaint_civil" };
const POPULAR = new Set([1, 2, 3, 4, 10]);

// Card fields only; the body is looked up by id in buildContent.
export const TEMPLATES = [
    ...LIBRARY.map(({ id, name, cat, law, desc, icon }) => ({
        id, name, cat, law, desc, icon, popular: POPULAR.has(id),
        ...(TEMPLATE_TYPE[id] ? { template_type: TEMPLATE_TYPE[id] } : {}),
    })),
    BLANK_TEMPLATE,
];

// Derived, so a category pill can never lead to an empty grid.
export const CATEGORIES = ["All", ...new Set(TEMPLATES.map(t => t.cat))];

const BODY = new Map(LIBRARY.map(t => [t.id, t.html]));

/* The editor's starting HTML for a template. Library bodies are fixed,
   generator-escaped HTML; anything else (the blank card, an unknown id) gets the
   generic scaffold, built from ESCAPED case data. */
export function buildContent(tmpl, caseObj) {
    const body = BODY.get(tmpl?.id);
    if (body) return body;

    const caseRef = escapeHtml(caseObj?.id || "[Case No.]");
    const clientRef = escapeHtml(caseObj?.client || "[Client Name]");
    const court = escapeHtml(caseObj?.court || "[Court Name]");
    const title = escapeHtml(tmpl?.name || BLANK_TEMPLATE.name);
    const today = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
    return `IN THE COURT OF [COURT]\n\nCase Reference: ${caseRef}\n\n${title.toUpperCase()}\n\nIN THE MATTER OF: ${clientRef}\n\nBefore: ${court}\n\nDate: ${today}\n\n${"─".repeat(60)}\n\n1. INTRODUCTION\n\n[Nature of this filing and on whose behalf it is made.]\n\n2. FACTS\n\nThe relevant facts are as follows:\n\n   a) [State first material fact]\n   b) [State second material fact]\n   c) [State third material fact]\n\n3. GROUNDS\n\n   i.  [Ground one — legal basis]\n   ii. [Ground two — factual basis]\n\n4. PRAYER\n\n[Relief sought.]\n\n${"─".repeat(60)}\n\nDate: ${today}\t\t\t_______________________\n\t\t\t\t\t[Advocate Name]\n\t\t\t\t\tBar Council Enrollment No.: [__________]`;
}
