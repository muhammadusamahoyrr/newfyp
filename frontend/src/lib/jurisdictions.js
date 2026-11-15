/* The jurisdictions a lawyer can choose (2026-10-14).
 *
 * Values are the backend's own allowlist (app/ai/jurisdiction.py
 * VALID_PROVINCES) and the labels are the ones the Cases page already used; this
 * module only stops the two from drifting apart. NEUTRAL is the backend's
 * UNSPECIFIED value: a jurisdiction-neutral draft on federal law, with
 * placeholders where provincial law governs (app/ai/draft_jurisdiction.py).
 */

export const PROVINCES = [["punjab", "Punjab"], ["sindh", "Sindh"], ["kpk", "Khyber Pakhtunkhwa"], ["balochistan", "Balochistan"], ["federal", "Federal / Islamabad"]];

export const NEUTRAL = "unknown";

/** Provinces whose own statutes the library holds (jurisdiction.PROVINCES_WITH_CORPUS). */
export const WITH_PROVINCIAL_LAW = new Set(["punjab"]);

/** The display name of a stored province value, or null when it is not one. */
export function provinceLabel(value) {
    const v = String(value || "").trim().toLowerCase();
    const hit = PROVINCES.find(([key]) => key === v);
    return hit ? hit[1] : null;
}

/** What a lawyer is told about the law a draft for `value` can draw on. */
export function coverageNote(value) {
    const v = String(value || "").trim().toLowerCase();
    if (v === NEUTRAL) return "Federal law only. Where provincial law governs, the draft leaves a placeholder and names no provincial Act.";
    if (v === "federal") return "Federal law only; provincial Acts are withheld.";
    const label = provinceLabel(v);
    if (!label) return "";
    return WITH_PROVINCIAL_LAW.has(v)
        ? `Federal and ${label} law; other provinces' Acts are withheld.`
        : `The library holds no ${label} provincial statutes yet: federal law only, with placeholders for ${label} law.`;
}
