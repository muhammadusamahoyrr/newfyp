/* The lawyer template library (2026-10-14): 24 reference templates with their
 * Word formatting, plus the blank scaffold; 20 more added on 2026-10-19
 * (deeds, tenancy, notices, consumer / regulator complaints, tax appeal).
 *
 * What these tests hold:
 *   * every card opens a body of its own, in HTML the server's draft sanitiser
 *     keeps (document_service._DRAFT_ALLOWED_TAGS; style = text-align only);
 *   * the legal errors found in the reference text stay corrected;
 *   * the editor can load the HTML as it is (no raw newlines to re-break).
 */
import test from "node:test";
import assert from "node:assert/strict";

const { TEMPLATES, CATEGORIES, BLANK_TEMPLATE, buildContent } = await import("../src/lib/lawyerDraftTemplates.js");
const { LIBRARY } = await import("../src/lib/lawyerTemplateLibrary.js");

const ALLOWED = new Set(["p", "div", "br", "span", "b", "strong", "i", "em", "u", "s", "strike", "sub", "sup",
                         "font", "ul", "ol", "li", "h1", "h2", "h3", "blockquote", "hr",
                         "table", "thead", "tbody", "tr", "th", "td"]);
const body = name => buildContent(TEMPLATES.find(t => t.name === name), null);
const all = () => LIBRARY.map(t => t.html).join("\n");

test("44 library templates plus the blank scaffold, unique ids, every one with its own body", () => {
    assert.equal(LIBRARY.length, 44);
    assert.equal(TEMPLATES.length, 45);
    assert.ok(TEMPLATES.includes(BLANK_TEMPLATE));
    assert.equal(new Set(TEMPLATES.map(t => t.id)).size, TEMPLATES.length);
    const generic = buildContent(BLANK_TEMPLATE, null);
    for (const t of TEMPLATES.filter(t => t !== BLANK_TEMPLATE)) {
        const html = buildContent(t, null);
        assert.ok(html.length > 300, `${t.name} body too short`);
        assert.notEqual(html, generic, `${t.name} opens the generic scaffold`);
        assert.ok(t.law && t.desc && t.cat, `${t.name} card fields`);
    }
});

test("the categories match the reference library, and none is empty", () => {
    for (const c of ["Application / Petition", "Agreement / Contract", "Business / Commercial", "Notice / Letter", "General", "Property"]) {
        assert.ok(CATEGORIES.includes(c), `missing category ${c}`);
        assert.ok(TEMPLATES.some(t => t.cat === c), `empty category ${c}`);
    }
});

test("bodies use only tags the draft sanitiser keeps, and no style but text-align", () => {
    for (const t of LIBRARY) {
        for (const [, tag] of t.html.matchAll(/<\/?([a-z0-9]+)/g)) {
            assert.ok(ALLOWED.has(tag), `${t.name}: <${tag}> would be stripped on save`);
        }
        for (const [, style] of t.html.matchAll(/style="([^"]*)"/g)) {
            assert.match(style, /^text-align:(center|right|justify|left)$/, `${t.name}: style ${style}`);
        }
        assert.doesNotMatch(t.html, /<script|on[a-z]+=|javascript:/i, `${t.name}: unsafe markup`);
        // The editor converts "\n" to <br>; a library body carries its own breaks.
        assert.ok(!t.html.includes("\n"), `${t.name}: raw newline`);
    }
});

test("the Word layout is kept: centred bold court heading, numbered paragraphs, PRAYER", () => {
    const bail = body("Bail Application");
    assert.match(bail, /^<p style="text-align:center"><strong>IN THE COURT OF/);
    assert.match(bail, /<p style="text-align:center"><strong>VERSUS<\/strong><\/p>/);
    assert.match(bail, /<strong>Respectfully Sheweth:<\/strong>/);
    assert.match(bail, /<ol><li>That the Applicant has been implicated/);
    assert.match(bail, /<strong>PRAYER<\/strong>/);
    const lease = body("Lease Agreement");
    assert.match(lease, /<strong>1\. Premises Description<\/strong>/);
});

/* ── the legal corrections (each was wrong in the reference text) ───────── */

test("dissolution is under DMMA 1939 s.2, not MFLO s.7 (talaq notice)", () => {
    const d = body("Dissolution of Marriage Application");
    assert.match(d, /SECTION 2 OF THE DISSOLUTION OF MUSLIM MARRIAGES ACT, 1939/);
    assert.match(d, /Section 2 of the Dissolution of Muslim Marriages Act, 1939/);
    assert.doesNotMatch(d, /Section \[?7\]? of the Muslim Family Laws Ordinance/i);
    assert.doesNotMatch(d, /UNDER THE MUSLIM FAMILY LAWS ORDINANCE/);
});

test("the Guardians and Wards Act is named correctly, with its sections", () => {
    assert.doesNotMatch(all(), /Guardian and Wards Act/i);
    assert.match(body("Custody Application"), /SECTION 25 OF THE GUARDIANS AND WARDS ACT, 1890/);
    assert.match(body("Guardianship Application"), /SECTIONS 7 AND 10 OF THE GUARDIANS AND WARDS ACT, 1890/);
});

test("the custody prayer appears once", () => {
    const c = body("Custody Application");
    assert.equal((c.match(/PRAYER/g) || []).length, 1);
    assert.doesNotMatch(c, /Prayer for Relief/);
});

test("an FIR registration petition is under CrPC s.22-A(6), with the SHO as a respondent", () => {
    const f = body("Petition for Registration of FIR");
    assert.match(f, /SECTION 22-A\(6\) OF THE CODE OF CRIMINAL PROCEDURE, 1898/);
    assert.match(f, /JUSTICE OF THE PEACE/);
    assert.match(f, /Station House Officer/);
    assert.doesNotMatch(f, /SECTION \[RELEVANT\]/);
});

test("the plaint states valuation and is verified", () => {
    const p = body("Plaint — Civil Suit");
    assert.match(p, /ORDER VII RULE 1, C\.P\.C\./);
    assert.match(p, /purposes of court fee/);
    assert.match(p, /purposes of jurisdiction/);
    assert.match(p, /VERIFICATION/);
    assert.match(p, /Order VI Rule 15, C\.P\.C\./);
    assert.equal(TEMPLATES.find(t => t.id === 2).template_type, "plaint_civil");
});

/* ── the second batch's corrections (2026-10-19) ─────────────────────────── */

test("a sale deed is a bai nama, not a bayana (agreement to sell)", () => {
    const d = body("Sale Deed (Bai Nama)");
    assert.match(d, /\(BAI NAMA\)/);
    assert.doesNotMatch(all(), /BAYNA/);
});

test("a consumer complaint is under Pakistan's provincial Acts, after a notice", () => {
    const c = body("Consumer Court Complaint");
    assert.match(c, /PUNJAB CONSUMER PROTECTION ACT, 2005/);
    assert.match(c, /ISLAMABAD CONSUMERS PROTECTION ACT, 1995/);
    assert.doesNotMatch(c, /CONSUMER PROTECTION ACT, 2019/, "India's Act is cited");
    assert.match(c, /3-A\. That before filing this complaint the Complainant served a written notice/);
});

test("eviction goes to the Rent Tribunal / Controller, and rent laws are named by province", () => {
    assert.match(body("Eviction / Vacation Notice"), /eviction application[\s\S]*Rent Tribunal \/ Rent Controller/);
    assert.doesNotMatch(body("Eviction / Vacation Notice"), /file a suit for eviction/);
    for (const name of ["Commercial Tenancy Agreement", "Sub-Lease Agreement"]) {
        assert.match(body(name), /Punjab Rented Premises Act, 2009/, name);
        assert.doesNotMatch(body(name), /\[Province\]/, name);
    }
});

test("a NEPRA complaint cites section 39 of the NEPRA Act, not unconfirmed rules", () => {
    const n = body("NEPRA Consumer Complaint");
    assert.match(n, /SECTION 39 OF THE REGULATION OF GENERATION, TRANSMISSION AND DISTRIBUTION OF ELECTRIC POWER ACT, 1997/);
    assert.doesNotMatch(n, /CONSUMER PROTECTION\) RULES, 2022/);
});

test("no abolished office is named as a respondent", () => {
    assert.doesNotMatch(all(), /District Coordination Officer/);
});

test("case data never reaches the library bodies, and the scaffold still escapes it", () => {
    const evil = { id: "<b>x</b>", client: "<img src=x onerror=1>", court: "\"c\"" };
    for (const t of TEMPLATES) assert.doesNotMatch(buildContent(t, evil), /<img|<b>x/);
});
