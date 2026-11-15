# Batch 4 (corrective, code-only): Constitution omission gate, non-Punjab CPC policy, snapshot plan (2026-10-16)

**Not done, by instruction:** no live-store access, snapshot, scratch embedding, ingestion, index switch, model or provider call, cleanup or commit. All changes are uncommitted; existing uncommitted work was not reverted.

**Legal interpretation in this file is the developer's reading of the Gazette.** A Pakistani lawyer must review it before any court-ready claim. The 2012 Constitution text on file is **not** made current by anything here.

## 1. Evidence: Constitution (Twenty-seventh Amendment) Act, 2025

**The source:**
- Gazette of Pakistan, Extraordinary, Part I, Islamabad, Thursday 13 Nov 2025 ([2307(2025)/Ex. Gaz.]); Act No. XXXII of 2025; assent 13 Nov 2025.
- URL: https://www.na.gov.pk/uploads/documents/691ec19a6a212_270.pdf. Fetched once in batch 2 (single document, 200 application/pdf); sha256 `303d09fab0516c1fd723f36f5a401fbab872091fe1b5213a192e172b39b275d1`; 23 PDF pages.
- The PDF is a **scanned image with a poor OCR text layer**.

**How it was read:**
- All 56 section headings, plus the operative clause of every section containing "shall be omitted", were extracted page by page and read. OCR misreadings were resolved from context (e.g. "Omission of Article l8,l" in s.29 = Art. 184; "1751" = Art. 175I).
- Page numbers are **PDF pages**; the Gazette's printed page numbers run from 775.

**Correction to batch 3:** **Article 186 is omitted WHOLE** by s.31 (PDF p.13: "31. Omission of Article 186 of the Constitution.- In the Constitution, Article 186 shall be omitted."). Batch 3 listed only 184, 186A and 191A.

**Whole-Article omissions, the complete list:**

| Article | Section | Page |
|---|---|---|
| 184 | s.29 | 12 |
| 186 | s.31 | 13 |
| 186A | s.32 | 13 |
| 191A | s.37 | 15 |

No other section of the Act omits a whole Article.

**Part-only omissions** (the Article survives, so it is never withheld):

| Article | What was omitted | Section | Page |
|---|---|---|---|
| 130 | a proviso | s.14 | 3 |
| 175A | provisos | s.20 | 4–7 |
| 183 | clause (3) | s.28 | 12 |
| 193 | clause (3) | s.39 | 15 |
| 207 | paragraph (c) | s.46 | 16–17 |

The Fifth Schedule also loses words (s.56, p.23).

**Substituted, so the Article still exists with new text:** 185 (s.30), 189 (s.34), 191 (s.36), 200 (s.41).

**Inserted:** new Chapter 1A, "The Federal Constitutional Court" (s.21, pp.7–11). It adds Articles 175B, 175C, 175D, 175E, 175F, 175G, 175H, **175I** (OCR "1751", p.10), 175J, 175K and 175L.

**Full table.** The code's `source_currency.GAZETTE_27TH` holds exactly these rows; this table was generated from it.

| Gazette s. | Article | Effect | PDF page(s) | Gate effect in drafter |
|---|---|---|---|---|
| 1 | — | Short title and commencement; s.1(2) "shall come into force at once" | 1–2 | — |
| 2 | 6 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 3 | 10 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 4 | 17 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 5 | 59 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 6 | 63A | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 7 | 68 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 8 | 78 | Amended (words/clauses inside a surviving Article) | 2 | never Supported; Not checked + note |
| 9 | 81 | Amended (words/clauses inside a surviving Article) | 2-3 | never Supported; Not checked + note |
| 10 | 93 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 11 | 100 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 12 | 105 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 13 | 114 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 14 | 130 | Amended: **part** omitted (Article survives): a proviso | 3 | never Supported; Not checked + note |
| 15 | 146 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 16 | 152 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 17 | 159 | Amended (words/clauses inside a surviving Article) | 3 | never Supported; Not checked + note |
| 18 | 165A | Amended (words/clauses inside a surviving Article) | 3-4 | never Supported; Not checked + note |
| 19 | 175 | Amended (words/clauses inside a surviving Article) | 4 | never Supported; Not checked + note |
| 20 | 175A | Amended: **part** omitted (Article survives): provisos | 4-7 | never Supported; Not checked + note |
| 21 | 175B | Inserted (new Article, Chapter 1A) | 7 | never Supported; Not checked + note |
| 21 | 175C | Inserted (new Article, Chapter 1A) | 8 | never Supported; Not checked + note |
| 21 | 175D | Inserted (new Article, Chapter 1A) | 8 | never Supported; Not checked + note |
| 21 | 175E | Inserted (new Article, Chapter 1A) | 9 | never Supported; Not checked + note |
| 21 | 175F | Inserted (new Article, Chapter 1A) | 9 | never Supported; Not checked + note |
| 21 | 175G | Inserted (new Article, Chapter 1A) | 10 | never Supported; Not checked + note |
| 21 | 175H | Inserted (new Article, Chapter 1A) | 10 | never Supported; Not checked + note |
| 21 | 175I | Inserted (new Article, Chapter 1A) | 10 | never Supported; Not checked + note |
| 21 | 175J | Inserted (new Article, Chapter 1A) | 10 | never Supported; Not checked + note |
| 21 | 175K | Inserted (new Article, Chapter 1A) | 11 | never Supported; Not checked + note |
| 21 | 175L | Inserted (new Article, Chapter 1A) | 11 | never Supported; Not checked + note |
| 22 | 176 | Amended (words/clauses inside a surviving Article) | 11-12 | never Supported; Not checked + note |
| 23 | 177 | Amended (words/clauses inside a surviving Article) | 12 | never Supported; Not checked + note |
| 24 | 178 | Amended (words/clauses inside a surviving Article) | 12 | never Supported; Not checked + note |
| 25 | 179 | Amended (words/clauses inside a surviving Article) | 12 | never Supported; Not checked + note |
| 26 | 180 | Amended (words/clauses inside a surviving Article) | 12 | never Supported; Not checked + note |
| 27 | 182 | Amended (words/clauses inside a surviving Article) | 12 | never Supported; Not checked + note |
| 28 | 183 | Amended: **part** omitted (Article survives): clause (3) | 12 | never Supported; Not checked + note |
| 29 | 184 | **WHOLE ARTICLE OMITTED** | 12 | withheld if relied on; history kept as not checked |
| 30 | 185 | Substituted (whole Article replaced; still exists) | 12-13 | never Supported; Not checked + note |
| 31 | 186 | **WHOLE ARTICLE OMITTED** | 13 | withheld if relied on; history kept as not checked |
| 32 | 186A | **WHOLE ARTICLE OMITTED** | 13 | withheld if relied on; history kept as not checked |
| 33 | 187 | Amended (words/clauses inside a surviving Article) | 14 | never Supported; Not checked + note |
| 34 | 189 | Substituted (whole Article replaced; still exists) | 14 | never Supported; Not checked + note |
| 35 | 190 | Amended (words/clauses inside a surviving Article) | 14 | never Supported; Not checked + note |
| 36 | 191 | Substituted (whole Article replaced; still exists) | 14-15 | never Supported; Not checked + note |
| 37 | 191A | **WHOLE ARTICLE OMITTED** | 15 | withheld if relied on; history kept as not checked |
| 38 | 192 | Amended (words/clauses inside a surviving Article) | 15 | never Supported; Not checked + note |
| 39 | 193 | Amended: **part** omitted (Article survives): clause (3) | 15 | never Supported; Not checked + note |
| 40 | 199 | Amended (words/clauses inside a surviving Article) | 15 | never Supported; Not checked + note |
| 41 | 200 | Substituted (whole Article replaced; still exists) | 15-16 | never Supported; Not checked + note |
| 42 | 202A | Amended (words/clauses inside a surviving Article) | 16 | never Supported; Not checked + note |
| 43 | 204 | Amended (words/clauses inside a surviving Article) | 16 | never Supported; Not checked + note |
| 44 | 205 | Amended (words/clauses inside a surviving Article) | 16 | never Supported; Not checked + note |
| 45 | 206 | Amended (words/clauses inside a surviving Article) | 16 | never Supported; Not checked + note |
| 46 | 207 | Amended: **part** omitted (Article survives): paragraph (c) | 16-17 | never Supported; Not checked + note |
| 47 | 208 | Amended (words/clauses inside a surviving Article) | 17 | never Supported; Not checked + note |
| 48 | 209 | Amended (words/clauses inside a surviving Article) | 17-19 | never Supported; Not checked + note |
| 49 | 210 | Amended (words/clauses inside a surviving Article) | 19-20 | never Supported; Not checked + note |
| 50 | 239 | Amended (words/clauses inside a surviving Article) | 20 | never Supported; Not checked + note |
| 51 | 243 | Amended (words/clauses inside a surviving Article) | 20-21 | never Supported; Not checked + note |
| 52 | 248 | Amended (words/clauses inside a surviving Article) | 21 | never Supported; Not checked + note |
| 53 | 260 | Amended (words/clauses inside a surviving Article) | 21-22 | never Supported; Not checked + note |
| 54 | — | Third Schedule (oaths) amended | 22–23 | — (not an Article) |
| 55 | — | Fourth Schedule amended | 23 | — (not an Article) |
| 56 | — | Fifth Schedule amended (words omitted in second paragraph) | 23 | — (not an Article) |

**Limits of this reading:**
- **Not read:**
  - every operative word of every amendment (only headings, plus the omission clauses in full);
  - the new Articles' full text;
  - the 26th Amendment;
  - any amendment after the 27th.
- **Scope of the gate:**
  - **Supported:** never, for any Constitution citation.
  - **Annotated:** whole-Article omissions and every Article listed above.
  - **Withheld:** whole-Article omissions only.

## 2. Code changes (this batch; uncommitted)

| File | Change |
|---|---|
| `app/ai/source_currency.py` | **The evidence table:**<br>• `GAZETTE_27TH` holds 62 rows covering all of ss.2–53; derived `OMITTED_ARTICLES` = {184, 186, 186A, 191A}, `INSERTED_ARTICLES` = 175B–175L, and `CLAUSE_OMITTED`.<br><br>**Finding citations:** `article_refs` reads:<br>• Article / Art. / ARTICLE / lists ("Articles 184 and 186");<br>• hyphenated or attached suffixes;<br>• Roman Urdu ("aain ke article 186a");<br>• Urdu script and Urdu digits ("آرٹیکل ۱۸۶").<br><br>**`omitted_article_check`**:<br>• Citations are found in the whole text and mapped back to units, because the sentence splitter cuts after "Art.".<br>• Reliance ("under / in exercise of / pursuant to …", "… کے تحت", "ke tehat") is **withheld**, even when the sentence also says "omitted".<br>• History ("before its omission …", "formerly", "was omitted") is kept and listed as a historical reference, never supported.<br>• Any other mention is withheld.<br><br>**Notes on what is not checked:**<br>• `constitution_note` says, per Article, omitted / substituted / inserted / amended / part-omitted, with Gazette section and page.<br>• `annotate_not_checked` makes every not-checked Constitution entry, and every CPC entry outside Punjab, say why.<br><br>**Prompt and claim helpers:**<br>• `research_rider`: an omitted Article is answered as history, "no longer in force".<br>• `downgrade_wrong_province_cpc` (chat and research claims). |
| `app/ai/draft_guard.py` | Uses `omitted_article_check`. A historical mention replaces the generic entry for the same Article. A historical note for a unit withheld for another reason is dropped. Not-checked entries are annotated. |
| `app/ai/nodes/hallucination_node.py` | Every surface: in a turn whose province is **known** to be Sindh, KP, Balochistan or Islamabad/federal, a claim resting only on the (Punjab) CPC goes from "supported/partial" to "unassessed", with the reason. Downgrade-only. |
| `tests/test_constitution_gate.py` (new) | 51 tests (§4) |
| `evals/legal_sources/BATCH3_BASELINE_AND_FALLBACK.md` | §1d replaced by revision 2 (§5 here); the batch-3 omitted list corrected |

## 3. Non-Punjab CPC: what can be inserted today, and the two options (AWAITING YOUR CHOICE)

**Trace:** a Sindh draft (or ICT, KP, Balochistan, or neutral) where the model writes "That this Court has jurisdiction under Section 9 of the Code of Civil Procedure, 1908."
1. The `draft_guard` result keeps the sentence in `guard.text`. `supported` contains no CPC entry (verified on every route in this batch). `not_checked` contains:
   > "Section 9 CPC 1908 (… ) (the CPC text on file is the Punjab version; the Sindh text has not been verified)"
2. The panel (`DocAutomationPage.jsx`, unchanged) shows the proposal text, then one line: *"Not verified — check these yourself: Section 9 CPC 1908 (…Punjab version; the Sindh text has not been verified)."*
3. **"Insert at cursor" is the primary button and is enabled. "Copy" is too. The inserted text carries no marker.** Once inserted, nothing in the document shows that the citation was unverified for Sindh.

So today the sentence is **never shown as Supported, but it is insertable.** That is not fail-closed.

**Option A: withhold the AI sentence and offer a guarded placeholder version.**
- **Main proposal:** units relying on the CPC outside Punjab are **withheld**, with the reason "the CPC text on file is the Punjab version; the Sindh text has not been verified". This works like a provincial Act in a jurisdiction-neutral draft.
- **Second proposal,** built deterministically and checked again in full: the same text with the CPC citation replaced by a placeholder. It uses the existing `placeholder_alternative` path, which the panel already renders as a separate insertable proposal.
  - Example main: *(withheld)*.
  - Example alternative: "That this Court has jurisdiction under [CPC provision as applicable in Sindh — verify against the Sindh text]."
- **Pros:**
  - fail-closed;
  - no Punjab wording reaches a Sindh filing by one click;
  - consistent with how foreign-province Acts are already handled;
  - **backend-only, no lawyer-UI change.**
- **Cons:**
  - Over-withholds: most CPC provisions are probably worded the same across provinces, but we cannot show which.
  - Lawyers outside Punjab lose CPC-grounded sentences until federal or other-province text is ingested and verified.

**Option B: keep it insertable with a conspicuous unverified warning.**
- The sentence stays insertable.
- The panel shows a prominent warning banner on that proposal, e.g. "⚠ Contains CPC wording verified only against the PUNJAB text — check against the Sindh CPC before filing". It could also require a confirm click before Insert, or wrap the inserted citation in a visible highlight.
- **Pros:** keeps the lawyer's flow; the lawyer decides.
- **Cons:**
  - Fail-open: one click can still put unverified wording into a filing.
  - A plain-text warning cannot travel *inside* the document (a note in the text would land in the filing).
  - **Needs a lawyer-UI change**, which your standing rule forbids without approval.

**Recommendation: Option A.**
- It matches the platform's fail-closed rule for legal authority.
- It is backend-only, so the lawyer UI is untouched.
- The placeholder alternative keeps the lawyer productive.
- It can be relaxed **per jurisdiction** later, once a verified federal or Sindh CPC text is in the corpus.
- **Not implemented. Awaiting your choice.**
- The current test (`test_a_wrong_province_cpc_citation_is_never_supported_in_the_panel`) pins today's behaviour. Its last assertion changes with the policy.

**Chat and research:** a CPC-only claim for a known non-Punjab province is now "unassessed" with the reason (§2), so it is never shown as "supported".
- **Consequence:** an answer for a Sindh question that rests **only** on CPC claims now trips the existing `grounding_veto` ("no claim positively supported"). The user then gets the existing caution, and generation may retry once. This is the same behaviour `issue_relevance` already causes.
- **Left as it was:** an **unknown** province. Client chat sends `province: null`, so most client CPC answers are unaffected. Whether "unknown" should also be gated is your call.

## 4. Tests

**How the tests were run**
- 25 files, one at a time, under the temporary-Chroma isolation guard; `AAI_ALLOW_LIVE_CHROMA` was not set.
- `-m "not integration and not llm and not network"`.
- Run window: 15:44–16:00 UTC. Logs and JUnit XML are in the session scratchpad (`iso/b4`).

**First pass: 2 failures**, both in the batch-3 `test_source_currency.py`. They asserted the old note wording ("amended after", "omitted by the 27th Amendment"). The notes now cite the Gazette section and page. Both assertions were updated to the new wording, and Article 186 was added. The file was rerun alone: 29 passed.

**Final:**
- **Results:** **1,126 passed, 0 failed**, 92 skipped, 2 xfailed, 3 deselected.
- **Skipped (92):** `test_template_citation_binding` templates that print no provision (by design).
- **Expected failures (xfail, 2):** gloss-list citations, unreadable by design.
- **Deselected (3):** MongoDB `integration` tests in `test_v2_stage5`.
- **Real-corpus (`corpus`) tests:** none of these 25 files contains any. They were **not run** in this batch, and they are **not counted as passes**. Batch 3 lists 31 of them across five files, skipped by the isolation guard.

**New, `tests/test_constitution_gate.py`: 51 passed.**
- **Evidence table:**
  - the whole-Article omissions are exactly {184 s.29 p12, 186 s.31 p13, 186A s.32 p13, 191A s.37 p15};
  - part-only omissions (130, 175A, 183, 193, 207) and substitutions (185, 189, 191, 200) are not treated as Article omissions;
  - the inserted Articles are 175B–175L, including 175I;
  - sections 2–53 are all present.
- **Citation forms (11):** Article / Art. / ARTICLE / lists / 184(3) / Roman Urdu / Urdu script and digits. "section 186 PPC" and "Section 186 CrPC" yield no Article.
- **Drafter legal check** (real `draft_guard`, fake library):
  - every omitted Article relied on is withheld, citing its Gazette section;
  - Articles 199, 193 (clause only) and 185 (substituted) are kept, never Supported, and Not checked with the Gazette note;
  - Article 186 of the Constitution is withheld, while section 186 PPC is not touched by this gate;
  - headings, parentheses, "Art.", lists and Roman Urdu are caught; Urdu script reliance is withheld;
  - a historical sentence is kept as "historical reference … s.31", while "under Article 186, which was omitted …" is still withheld.
- **Research prompt:** an omitted Article is answered as history, "no longer in force".
- **Final insertable text** (real `/ai/draft/stream` route, stubbed model):
  - Article 199 is kept and Article 186 removed from `guard.text`;
  - Supported is empty;
  - the Not checked entry names s.40 and the Withheld entry names s.31;
  - the verification and audit records read the guarded text.
- **Wrong-province CPC:**
  - **Drafter:** for Sindh, KP, Balochistan and federal, no CPC entry appears in Supported, and the Not checked entry names the province. The current insertability is pinned; this awaits your choice (§3).
  - **Chat and research badge:** the real `hallucination_node` with a stubbed judge gives "unassessed" for Sindh and "supported" for Punjab.
  - **What the downgrade leaves alone:** Punjab, an unknown province, mixed sources, and non-CPC claims.
- **Mutation tests (3), all caught:**
  - the batch-3 list without 186 fails the Article-186 regression tests;
  - treating clause omissions (193, 183, 130, 207) as whole-Article omissions fails the amended-Article test and the evidence-table test;
  - removing the CPC downgrade fails the chat/research badge test.

**Isolation:** 0 accesses to the live path refused, apart from the guard test's own 15 deliberate probes. Only `test_live_chroma_guard` opened a persistent client, and on the temporary store.

## 5. Snapshot plan

**Where:** BATCH3 §1d was replaced in place by **revision 2**. It now:
- keeps failed or partial copies;
- stops if handles cannot be verified (Resource Monitor check by you; ports and process names are not enough);
- handles WAL/SHM files;
- states exact paths, manifest format, pass/fail per step and free-space requirement;
- says exactly what can and cannot be concluded without a pre-incident hash;
- has **no restart**, restore, swap, delete or rebuild.

**The separate approval it needs:**
> "Approved: I have stopped the backend and frontend. Run BATCH3 §1d revision 2, steps 2–7: verify handles with me, copy backend/chroma_data to C:\Users\The Laptop Hut\Desktop\chroma_snapshots, write the SHA-256 manifest, and inspect the COPY only. Keep any failed or partial copy. No restore, swap, delete, rebuild or restart."

## 6. Untouched in this batch
- Live `backend/chroma_data`: not opened, copied, hashed, listed or modified. Its last-known write remains the Run A incident (BATCH2 §0) and it must **not** be assumed unchanged.
- The two orphan folders and all backups: not touched or listed.
- Active indexes and constants: unchanged; no switch. Parser v3: still opt-in.
- Models and providers: none called. Test judges and models are stubs.
- `backend/.env`: not read or changed. `AAI_ALLOW_LIVE_CHROMA` was not set.
- Lawyer UI and frontend: no change.
- Commits: none.
