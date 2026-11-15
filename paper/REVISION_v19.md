# FIT 2026 paper #628: camera-ready revision (v18 → v19)

**Files**
- `FIT_paper_v19.docx`: generated from `FIT_paper_v18.docx` by `build_v19.py`. v18 is not modified.
- `FIT_paper_v19.pdf`: exported with Microsoft Word, **6 pages** including references.
- `reeval/`: the evidence behind every new number:
  - `fit_reeval_colab.py`: the Colab T4 run on pinned, sha256-verified weights;
  - `fit_reeval_result.json`: the per-question ranks it produced;
  - `analyse.py` → `analysis.txt`: Hit@1, MRR@10, nDCG@5, bootstrap CIs, McNemar;
  - `analyse_subsets.py`: subset analyses. Run it from `backend/data` with the result JSON as its argument.

## 1. Corrections found while answering the reviews

These changes go beyond what the reviewers asked for. They were found by re-running the evaluation from per-question ranks, because the original runs had saved only aggregates.

| v18 said | Re-measured | Change in v19 |
|---|---|---|
| The constitutional model's +16.5 was "memorisation" of its training set and was excluded; only 22 questions were clean. | Its own 121-question split has **gold overlap 0** (`backend/data/finetune/split_manifest.json`). The 99/121 overlap is with the **general** model's training positives. | +15.7 [7.4, 24.0], p = 0.0005 is reported as a clean in-distribution gain. The leakage is attributed correctly (V-D ③, Table III). |
| The "apparent 0.766 Hit@1 was memorisation", attributed to the 121-question set. | 0.766 is the constitutional model on the **128-question** set: 106 of those 128 are its training questions. | Stated with the correct set (V-D ③). |
| "531 improved, 123 worsened … p ≈ 0.0005"; "31 improved vs 22 worsened". | These count questions whose rank moved in either direction, not Hit@1 flips. The Hit@1 discordant pairs are 377 vs 61 (p ≈ 10⁻⁵⁶) and 17 vs 14 (p = 0.72). | McNemar is now computed on paired Hit@1 outcomes. |
| MRR 0.438→0.612, nDCG 0.482→0.648 (general model). | MRR@10 0.516→0.758, nDCG@5 0.542→0.781. | Reproduced values are used. |
| "+6.6 under fusion is the largest improvement that remains after leakage and distribution-shift checks." | +6.6 is the constitutional model's **in-distribution** fusion gain. | Reported as an in-distribution number (V-C). The claim is removed. |
| Scope rule "rank 12→1" (Table III) and "Rank 10 → Rank 1" (Table IV). | The figure data (`build_figures.py`) shows rank 3→1 (k = 10) and 4→1 (k = 50). | Changed to rank 3 → 1. |
| Cumulative ablation table (Table IV). | Its layers mixed different sets and metrics, and its MRR 0.114→0.581 row was an evaluation-script repair, not a pipeline gain. | Removed. |
| Abstract: "the flattering version was wrong every time". | The wrong gold join *deflated* the score (0.114 vs 0.581). | Changed to "two inflated, one deflated". |
| Ref [27]: "A. B. Hou et al." | The authors of arXiv:2603.19251 are S. Maniyar, D. Singh and R. K. Reddy. | Corrected. |
| Ref [24]: "in Proc. NAACL". | CLERC appeared in Findings of NAACL 2025. | Corrected. |
| Tables: grid widths summed to 10,440 dxa against a 5,040-dxa column. | The tables overflowed the column. | Widths are now fitted to the column. |

## 2. Response to reviewers

**Reviewer 1**
- *Page limit.* The paper is now 6 pages including references (it was 7). The threats table is replaced by prose (§VII). Also removed: the cumulative-ablation table, Fig. 4, and the duplicated partition notes.
- *Paired significance for the out-of-distribution results.* Both now carry McNemar exact tests on paired Hit@1 outcomes with 95% bootstrap CIs:
  - +2.3 [−6.2, 10.9], 17 vs 14 discordant pairs, p = 0.72 (n = 128);
  - −0.3 [−2.9, 2.3], 121 vs 125, p = 0.85 (n = 1,191).
  - The "53 discordant pairs" in v18 were rank changes, not Hit@1 flips.
- *N = 22 in the abstract.* On re-checking, the 22-question limitation was a misattribution: the constitutional model's own held-out split is clean (121 questions). The abstract now states the sample sizes and reports intervals.
- *Why e5-base.* One sentence in §III-A (CPU deployment). BGE-M3 [25] is now **measured** zero-shot in §V-B (see §7): it trails the fine-tuned model by 16.1 points in-distribution and matches it only on Urdu LEGAL-UQA.
- *Typos.* v18 contains "query/passage" and "fine-tuning". "query/assage" and "finetuning" appear only in text extracted from the Word PDF, where hyphenated and ligature glyphs are dropped. Cross-references were checked: V-C is fusion and V-D is the contaminations. A wrong "V-C" in §V was fixed, and the missing subsection "A." in §VI was added.

**Reviewer 2.** External validity is addressed through intervals, sample sizes and a domain- and script-matched comparison:
- English constitutional questions gain +23.3 in-distribution against +2.3 out of distribution.
- Limits are listed in §VII: generator-derived sets, a single training run per model, and no practitioner adjudication.

**Reviewer 3.** Corpus construction (§III-A) now covers:
- sources and access date;
- collection assignment: keyword rules on file names for the bulk dataset, an explicit registry (with province) for directly fetched statutes;
- section-aware chunking (800/100);
- removal of contents pages and TOC stubs (registry pipeline);
- per-chunk metadata (statute, section, province, domain, source; registry chunks also content hash, parser version, provision status);
- the fact that enactment and amendment dates are not modelled.

Duplicates (§III-B):
- 0 exact train/test duplicates;
- 47 test queries (3.9%) with cosine ≥ 0.95 to a training query; excluding them leaves the gain at +25.9;
- the group split keeps gold passages from appearing in both train and test (source-level separation).

**Reviewer 4.** Table III (now Table V) is rewritten as *what each intervention encodes and what evidence exists under a change of source or style*:
- Only the learned interventions are measured. A 1,345-query style grid (new Table III, §7) shows their gains survive rewording; what fails is one source (English LEGAL-UQA), within the same domain and script.
- The deterministic interventions are stated to transfer *by construction* and to rest on one worked case.
- Local IDF is moved out of the table: it is a confidence result.
- The unsupported "fusion-weight tuning" row is removed.
- The structural explanation is labelled an interpretation. The suggested experiments (paraphrase augmentation, multi-generator training, a structure-aware objective) are added to Future Work.

## 3. Still for the authors to decide
- **Code availability.** v19 links the two public Hugging Face models (pinned revisions) and states that scripts and data are "available from the authors on request". Replace this with a repository URL if one will be public.
- **Docx check.** Open `FIT_paper_v19.docx` in Word once, check that the layout matches the PDF, then upload the PDF.

## 4. FIT 2026 camera-ready compliance checklist (checked against `conference-template-letter.docx`)
| Item | Status in v19 |
|---|---|
| A. Authors | Laid out column-wise in their own continuous two-column section, one author per column: name; department and university in italic; country; e-mail. No numbering. E-mails are not hyperlinked. Author order and affiliation wording are as accepted. |
| B. Abstract and keywords | Abstract body is bold and not italic, with "Abstract" in italic; keywords are bold italic (template styles). |
| C. Copyright | `979-8-3195-0206-3/26/$31.00 ©2026 IEEE` is in the first-page footer only, bottom left, 8 pt Times New Roman, added in the source before the PDF export. |
| D. Figures and tables | Figure captions are below the figures and justified; table captions are above the tables in small caps and not bold. All tables fit the column. No coloured text (only `000000`). |
| E. Layout | Two columns throughout. Margins follow the template: 54 pt top, 72 pt bottom, 44.65 pt left and right. No headers, no page numbers. A closing continuous section balances the columns on page 6. |
| F. References | No hyperlinks, underlines or colour anywhere in the document (0 / 0 / black). |
| G. Length and PDF | 6 pages including references. All fonts are embedded (TrueType subsets: Times New Roman, Cambria Math, MS PGothic for ①②③). The PDF is exported directly from the .docx by Word with no later edits. |
| Similarity (≤15% overall, <5% per source) | **Not checkable here.** Run iThenticate or Turnitin (through the COMSATS library) on `FIT_paper_v19.pdf` before uploading. |
| Affiliation city | v18 named no city. The template's line 4 is "City, Country"; add the campus city if you want it. |

## 5. Final check (reference errors carried over from v18, verified at source)
| Ref | v18 | Corrected |
|---|---|---|
| [2] LEGAL-BERT | DOI …findings-emnlp.138 | DOI 10.18653/v1/2020.findings-emnlp.261 (pp. 2898–2904); all five authors |
| [4] LeCaRD | "S. Ma et al.", "…for Chinese law", DOI …3462875, pp. 2348–2354 | "Y. Ma et al.", "…for Chinese law system", DOI 10.1145/3404835.3463250; pages dropped (not verifiable) |
| [12] Magar & Schwartz | DOI …acl-long.539 | ACL Short Papers, DOI 10.18653/v1/2022.acl-short.18 |
| [13] Sainz et al. | pp. 10746–10756 | pp. 10776–10787; arXiv link (DOI not verifiable) |
| [15] "C. Deng et al.", Findings of EMNLP 2024, arXiv:2404.00699 | arXiv:2404.00699 is a different paper (Ravaut et al.) | Deng, Zhao, Tang, Gerstein, Cohan, Proc. NAACL 2024, pp. 8706–8719, aclanthology 2024.naacl-long.482 |
| [21] McNemar | DOI …BF02289257 | DOI 10.1007/BF02295996 |

The circled digits ①②③ (rendered from MS PGothic, a non-template font) became (a)(b)(c). The PDF now uses only Times New Roman and Cambria Math, both embedded.

"finetuning" in extracted text is a line-end hyphen ("fine-" / "tuning") that text-extraction tools drop. The typeset PDF is correct.

## 6. Reviewer-eye pass
- **Abstract (R1, asymmetry):** now states that the constitutional model's out-of-distribution set mostly lies outside its domain.
- **§III-A (R1):** e5-base is described as "chosen over larger multilingual encoders because the system is deployed on CPU (Section VI-C)".
- **§VII (R3):** new limit (vii): splits separate gold passages, not whole statutes or documents.
- **§VI-A (R4):** the rule-scalability paragraph no longer generalises from one case.
- **§I:** "exceeded the gap between any two techniques" was untrue after the re-run. It now reads "erased nearly all of the gain".

**Partly addressed** (not doable without new data or experiments, so stated as limits and future work):
- **R2:** larger clean evaluation sets.
- **R3:** removing near-duplicates from training. They are measured instead: 47, and excluding them leaves +25.9.
- **R3:** a statute-level split.
- **R4:** the paraphrase-augmentation and multi-generator experiments.

## 7. New experiments integrated (style grid, cross-script, BGE-M3)

All numbers come from `reeval/analysis_stylegrid.txt`, `analysis_bgem3.txt` and `analysis_thirdstyle.txt`. Each model is evaluated only on sets that are clean for it. Still 6 pages; fonts embedded; citations [1]–[27] in first-cite order; Tables I–V first mentioned in order.

**What the experiments showed**
- *Rewording does not remove a gain.*
  - Constitutional model, own 121: original +15.7, Urdu +17.4, layperson +15.0, Roman Urdu +11.8 (all p < 0.05); keyword +6.7 (ns).
  - General model, 23 developer-written queries: +39.1 / +30.0 / +22.7 (p = 0.062) / +27.3 / +36.4.
- *What fails is the source.* General model on English LEGAL-UQA: original +2.3, layperson +6.3, keyword +7.1, all ns.
- *Cross-script transfers.* General model on LEGAL-UQA Urdu +24.2 (p = 1.6e-6) and Roman Urdu +17.5 (p = 0.00031).
- *Third source.* General model +40.0 on the 25 clean developer-written queries (p = 0.002).
- *BGE-M3 zero-shot (dense, max_seq 512, rev 5617a9f):*
  - citation set: 51.9 vs base e5 41.5 vs general 68.0 (p = 3.6e-24);
  - developer-written: 28.0 vs 60.0 (p = 0.021);
  - its lead over e5 is Urdu script: +29.8 (English +1.0);
  - LEGAL-UQA Urdu 41.4 vs 42.2; English 51.6 vs 54.7 (p = 0.56).

**Changes in the paper**
- §V-B is retitled "Gains Tied to the Question Source". It adds two paragraphs, "Style or source?" and "A larger encoder", plus the new **Table III** (style grid).
- Tables renumbered: contaminations III → IV; interventions IV → V.
- References: BGE-M3 is **[25]**, first cited in §V-B.
- Rewritten: abstract, introduction (negative-result paragraph and contribution 1), §VI-A, Table V, §VI-B ("A generated evaluation set is a single source"; "The protocol determined…"), Future Work item 3, Threats (viii) and the Conclusion.
- The interpretation changed: v18's "register/phrasing" explanation is ruled out by the grid and now appears only as ruled out.

**Removed for the page budget:**
- *Fig. 2* (one case's rank per stage): its result stays in the §V-A prose and Table V.
- *The local-IDF confidence aside* and its reference (Geifman & El-Yaniv): the paper itself called it "not part of" the transfer argument.
- *The corpus-history paragraph* at the start of §V.
- *The 10→50 depth sentence and the list of three improved reranker queries* in §V-A.
- *Fig. 1* is shrunk to 85%.
- No reported transfer result or claim was dropped.

**Title.** "In-Distribution Gains Do Not Transfer" is unchanged. It is now only partly supported: the gain did not transfer to one source (English LEGAL-UQA), but did transfer to a developer-written source and across scripts. The text says this plainly. Changing the title would need the chair's approval.


## 8. Checklist re-check after §7 (2026-10-25)

**PDF engine.** Every earlier PDF came from **WPS Office**, not Microsoft Word. On this laptop the `Word.Application` COM ProgID is registered to WPS (Creator field: "WPS Docs").
- `FIT_paper_v19.pdf` is now exported by Microsoft Word 365 through `paper/export_pdf_msword.ps1`. The script starts WINWORD.EXE, takes Word from the Running Object Table, exports in a separate job with a time limit, and closes its own Word afterwards.
- Word gives the same layout: 6 pages, US Letter.

**Proofreading fixes (all in the `build_v19.py` "Proofreading pass"):**
- Abstract cut from 279 to 246 words (≤ 250); same claims.
- Related Work repeated "BEIR/MTEB … no analogue …" in two consecutive paragraphs; the first copy was removed.
- Citations: "[8],[9]" → "[8], [9]"; "[12],[13],[14],[15]" → "[12]–[15]".
- Percent style made consistent ("20 %" → "20%").
- Equations (1)–(3): Σₚ → Σ with subscript q∈Q (the sum runs over the queries).
- Wording: "The bulk dataset is assigned…", "32% of the pairs join…", "(dense, sequence length 512)", "Our data do not explain why…", "neither outcome is visible…".
- The spacer paragraph after Table II, which opened the next column with a blank line, was removed.

**Checklist, verified on the Word PDF:**

| Item | Result |
|---|---|
| A. Authors | column-wise, no numbering, plain e-mail, order unchanged |
| B. Keywords | present, bold italic |
| C. Copyright | only page 1, bottom-left, 8 pt Times New Roman, in the source docx |
| D. Captions | table captions above, Fig. 1 caption below; none bold or italic; all tables 4,968 dxa (within the column) |
| E. Layout | 2 columns, margins 893 dxa as the template; no headers, page numbers or lines; last page balanced |
| F. References | black, no link annotations, no underline |
| G. Fonts | Times New Roman and Cambria Math, all embedded |
| G. Pages | 6 |
| G. Citations | [1]–[27] in first-cite order; Tables I–V in order |

**Still user-side:** similarity report (≤ 15% overall, < 5% per source).

## 9. Second re-check of the final PDF text (2026-10-25)

Claims were brought into line with what the new results support (`build_v19.py`, "Second recheck" block).

| Where | Change |
|---|---|
| V-B, mirror-pattern paragraph | v18's "no measurable out-of-distribution [gain]" became false once Table III showed +40.0 (developer-written) and +24.2 (Urdu LEGAL-UQA). It is narrowed to "none measurable on the other source's English questions". |
| Rewording claims | Now "largely" in the abstract, introduction, V-B, VI-A and Conclusion, because 2 of 10 cells are not significant (constitutional keyword +6.7; developer-written layperson +22.7, p = 0.062). Table V: "kept in 4 of 5 styles". |
| Abstract | "trails it by 16.1 points on the first source's held-out questions" (was "on its own held-out set", which was ambiguous). |
| V-A | "both retrieval depths (10 and 50 candidates)": the definition was lost when Fig. 2 and the depth sentence were removed. |
| V-B, style grid | "+40.0, p = 0.002, on the 25 with unseen gold passages" (was "all 25 clean ones", unclear next to the 23). |
| Naming | "MS MARCO" used throughout (was "MS-MARCO" in places). |
| Threats (ii) | Now lists the 25-query developer-written source as small. |
| Future Work, item 3 | Shortened so the paper stays at 6 pages. |

**Result.** Microsoft Word PDF: 6 pages; all fonts embedded; black only; no link annotations; copyright on page 1 only. Abstract is 248 words. Citations [1]–[27] are in first-cite order, and Tables I–V are first mentioned in order.

## 10. Author block matched to the IEEE template (2026-10-25)

- Author lines are now **9 pt**. The template's `Author` style says 11 pt, but every author run in the template overrides it to 9 pt; v19 had taken the style value.
- Line 4 now reads **"Islamabad, Pakistan"**, the template's "City, Country"; the user supplied the city.
- Still 6 pages, exported by Microsoft Word.
- Desktop copies updated: `FIT2026_paper628_camera_ready/`.

## 11. Full style comparison with the IEEE template (2026-10-25)

FIT's submission page names no template of its own: "must follow the IEEE conference proceeding format". The authority is therefore IEEE's `conference-template-letter.docx`.

Every style matched except one. Matching styles:
- page, top/bottom margins, column gap;
- title, authors, abstract, keywords;
- Heading 1 (small caps, not bold) and Heading 2 (italic);
- body, table captions (small caps, not bold), table head and copy, figure caption, references.

**The one fix: body margin.** The template's two-column body section has left/right margins of 45.35 pt (907 dxa); v19 had 44.65 pt everywhere. The body section now uses 907 dxa; the title, author and closing sections stay at 44.65 pt, as in the template. The column is now 5,033 dxa, and the tables (4,968 dxa) still fit. Still 6 pages, Word-exported, last page balanced.

## 12. Reviewer-eye layout pass (2026-10-25)

- **Table I** now follows its first citation (the first paragraph of §IV) instead of the end of §III-B. It did not fit there and left about 3 and 5 empty lines at the bottom of page 2's two columns; page 2 is now full.
- **Equations (1)–(3)** are centred, with the number flush right on a tab, as in the template. Before, the number sat next to the equation.
- **The line after the equations** ("where IDCG(q) = …") was stretched, because non-breaking spaces made "1…min(|G(q)|, k)" unbreakable. It is rewritten as "for i from 1 to min(|G(q)|, k)".
- **First-line indent** added to the Threats, Ethical Considerations and Code Availability paragraphs, as for every other body paragraph.
- **Not changed:** wide gaps in some justified reference lines. That is the template's justified `references` style.
- **Result:** 6 pages, Word-exported, fonts embedded, last page balanced; Desktop copies updated.

## 13. Spacing below the author block (2026-10-25)

Checklist A requires spacing above and below the author block to follow the IEEE template. Both were measured on Microsoft Word renders of the template and of v19, at 144 dpi, by row scan:

| Distance | Template | v19 before | v19 now |
|---|---|---|---|
| Title → first author line | ≈ 24 pt (6 pt after + 18 pt before) | 26.5 pt | 26.5 pt |
| Author line pitch | 10.5 pt | 10.5 pt | 10.5 pt |
| Top of last author line → top of abstract | 36 pt | 21.5 pt | 36 pt |

The fix adds a second blank line at the end of the author paragraph, set in 12 pt. Word ignores space-before at the top of the abstract's section, so that route did not work. Still 6 pages, Word-exported, fonts embedded, last page balanced.

`export_pdf_msword.ps1` now takes `-Src`; the template was exported with it for the measurement.

## 14. Introduction tightened; style-grid example added (2026-10-25, user-approved text)

- **Introduction paragraphs 3 and 4 merged** (160 → 135 words). They stated the result twice. The merged paragraph also fixes a v18 overclaim: "measured each intervention twice" became "measured both fine-tuned retrievers twice". Table V marks the scope rule and corpus repairs "not measured", and the cross-encoder was run on six queries only. The Urdu result now names Roman Urdu as well (+17.5) and is placed after the second-source result.
- **Scope of claims** shortened (70 → 52 words). It keeps every claim: "in our own system", "not specific to a single model configuration", no end-to-end improvement, no Pakistan-wide coverage.
- **V-B, "Style or source?"** gains one real LEGAL-UQA item from `reeval/stylegrid_test.json` (uqa128_008) in its original, layperson-English, Roman-Urdu and keyword forms. No ranks are given for it, since one item must not stand in for the averages.
- Every sentence was checked against Tables II, III and V and the data before it went in.
- **Result:** still 6 pages, Word-exported, fonts embedded, citations in order, abstract 248 words; Desktop copies updated.

## 15. Final pass: layout, method detail, proofreading (2026-10-25, user-approved)

**Layout.** Fig. 1 now follows the "Retrieval is hybrid" paragraph. Anchored after the §III-A corpus paragraph, it did not fit page 2's left column and left 82.5 pt (about 7 lines) empty; the gap is now 7.5 pt, and the figure still opens the right column.

**Method detail (each verified in code):**
- §III-A says how the channels are fused: "Each channel returns its top 10, and the two lists are merged by weighted reciprocal rank fusion [9] (weights 0.6 lexical and 0.4 dense, constant 60)". Sources: `retriever.py` (`FIRST_STAGE_K = 10`, `EnsembleRetriever(weights=[0.6, 0.4])`) and LangChain 0.3.30 `ensemble.py` (weighted RRF, `c = 60`).
- §IV says what Tables II and III score: "dense retrieval alone, not the deployed fusion (Section V-C)", with L2-normalised embeddings, cosine ranking, e5 prefixes at length 224, and BGE-M3 with no prefixes at length 512. Source: the three Colab eval scripts; none uses BM25.

**Proofreading (17 items, as listed to the user):**
- Grammar:
  - "in English, in Urdu script, and, most commonly, in Roman Urdu";
  - "showed that legal text benefits";
  - "worsened" / "improved" (consistent tense);
  - "tenant" in quotes;
  - "as a training signal";
  - "but not on another source";
  - "convert" (compound subject);
  - "consists of fragments";
  - comma removed in "frozen before development and practitioner adjudication";
  - "comes from Urdu script".
- No sentence starts with a numeral: "In total, 5,883 pairs survive"; "Of the pairs, 32% join".
- "e.g.," three times.
- Serial commas added in five places.
- Double quotes for the S.R.O. lookup.
- §VI-A: "Only the fine-tuned retrievers were measured" and "The deterministic interventions were not measured". The same overclaim was fixed in the introduction; the cross-encoder is learned too.
- References: journal, proceedings and book titles in italics (IEEE); "Hugging Face"; [17] gives "Accessed: Aug. 2026." before "[Online]".

**Result.** 6 pages, Word-exported, 9 fonts embedded, citations in order, Tables I–V first mentioned in order, abstract 248 words. No column has more than about 1.5 empty lines at the bottom except the balanced last page. Desktop copies updated.
