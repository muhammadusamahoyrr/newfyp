/* A matter's title, made fit for a card, a menu or a heading (2026-11-25).
 *
 * WHY. Older matters are titled with the client's whole intake question --
 * several lines, sometimes mixed English and Urdu ("My name is Imran Ali and
 * I live in Village Chak 45, …"). Printed whole, it broke My matters cards,
 * the case switcher and the agreement builder. CSS ellipsis alone is not
 * enough: a <select> option, a dialog sentence and an accessible label are
 * text, not boxes, so the text itself is shortened here.
 *
 * The FULL title is never lost: callers keep it for `title=` (tooltip) and
 * `aria-label`, via `fullMatterTitle`. */

/** Whitespace collapsed; never empty. */
export function fullMatterTitle(title, fallback = "Untitled matter") {
    const t = String(title ?? "").replace(/\s+/g, " ").trim();
    return t || fallback;
}

/** At most `max` characters, cut at a word where possible, ending in "…". */
export function shortMatterTitle(title, max = 60, fallback = "Untitled matter") {
    const t = fullMatterTitle(title, fallback);
    if (t.length <= max) return t;
    const cut = t.slice(0, max - 1);
    const space = cut.lastIndexOf(" ");
    // Prefer a word boundary, unless that would throw away most of the text.
    const base = space >= max * 0.6 ? cut.slice(0, space) : cut;
    return `${base.replace(/[\s,.;:–—-]+$/, "")}…`;
}

/** "Title · CASE-NO" with the title shortened; the number is never cut. */
export function matterLabel(title, caseNumber = null, max = 60) {
    const short = shortMatterTitle(title, max);
    return caseNumber ? `${short} · ${caseNumber}` : short;
}
