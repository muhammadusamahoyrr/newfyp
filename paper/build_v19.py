"""build_v19.py -- camera-ready revision of FIT_paper_v18.docx -> FIT_paper_v19.docx.

Edits v18 in place (copy) rather than regenerating, so the hand-made Word
formatting of the reviewed version is kept. v18 itself is never written.

Every number introduced here comes from a re-evaluation of the two fine-tuned
retrievers at their pinned revisions (sha256-verified), computed from
per-question ranks:  backend/data + paper/reeval/fit_reeval_result.json,
analysed by paper/reeval/analyse.py (output: paper/reeval/analysis.txt).

Usage:  backend/venv/Scripts/python.exe paper/build_v19.py
"""
from copy import deepcopy
from pathlib import Path

import docx
from docx.oxml.ns import qn

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "FIT_paper_v18.docx", HERE / "FIT_paper_v19.docx"

d = docx.Document(str(SRC))
P = list(d.paragraphs)          # indices as in v18 (see dump in reeval/README)
T = list(d.tables)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ── helpers ──────────────────────────────────────────────────────────────────
def _template_rpr(p, i):
    runs = p.runs
    if not runs:
        return None
    r = runs[min(i, len(runs) - 1)]._r
    rpr = r.find(qn("w:rPr"))
    return deepcopy(rpr) if rpr is not None else None


def set_text(p, segments):
    """Replace a paragraph's content with `segments`: [(text, bold, italic, tpl_run_index)].
    bold/italic None keeps the template run's setting."""
    tpls = [_template_rpr(p, s[3] if len(s) > 3 else i) for i, s in enumerate(segments)]
    for child in list(p._p):
        if child.tag in (W + "r", W + "hyperlink", W + "bookmarkStart", W + "bookmarkEnd"):
            p._p.remove(child)
    for (seg, tpl) in zip(segments, tpls):
        text, bold, italic = seg[0], seg[1], seg[2]
        run = p.add_run(text)
        if tpl is not None:
            old = run._r.find(qn("w:rPr"))
            if old is not None:
                run._r.remove(old)
            run._r.insert(0, deepcopy(tpl))
        if bold is not None:
            run.bold = bold
        if italic is not None:
            run.italic = italic


def plain(p, text):
    set_text(p, [(text, None, None, 0)])


def lead(p, head, body):
    """Bold-italic lead-in + plain body (the v18 'Scope of claims.' pattern)."""
    set_text(p, [(head, None, None, 0), (body, False, False, 1)])


def remove(el):
    el.getparent().remove(el)


def clone_after(anchor_el, src_p):
    new = deepcopy(src_p._p)
    anchor_el.addnext(new)
    return docx.text.paragraph.Paragraph(new, src_p._parent)


def cell_text(cell, text, bold=None):
    p = cell.paragraphs[0]
    for extra in cell.paragraphs[1:]:
        remove(extra._p)
    set_text(p, [(text, bold, None, 0)])


def fill_table(t, rows):
    """Resize t to len(rows) rows by cloning/removing body rows, then fill."""
    trs = t._tbl.findall(qn("w:tr"))
    while len(trs) < len(rows):
        trs[-1].addnext(deepcopy(trs[-1]))
        trs = t._tbl.findall(qn("w:tr"))
    for tr in trs[len(rows):]:
        t._tbl.remove(tr)
    for r, values in zip(t.rows, rows):
        for c, v in zip(r.cells, values):
            cell_text(c, v, bold=True if r is t.rows[0] else None)


# ── title block ──────────────────────────────────────────────────────────────
# As submitted: authors separated by a comma.
set_text(P[1], [("Muhammad Usama", None, None, 0), ("¹", None, None, 1), (", ", None, None, 2),
                ("Muhammad Amir Zarmaan Ullah Khan", None, None, 3), ("²", None, None, 4)])

set_text(P[5], [("Abstract", None, None, 0), ("—", None, None, 1), (
    "Retrieval interventions for legal question answering are usually evaluated on questions from the "
    "same distribution as their training data. We test what happens otherwise, for Pakistani statutory "
    "law. Fine-tuning a multilingual retriever on 4,692 verified citation pairs "
    "gains +26.5 Hit@1 (95% CI 23.5 to 29.6) on held-out questions from its own generator, but +2.3 "
    "(CI −6.2 to +10.9, p = 0.72, n = 128) on English questions written by a different generator, "
    "against +23.3 on in-distribution questions of the same domain and script. A second model, trained "
    "on 471 pairs from the other source, shows the mirror pattern: +15.7 on its own held-out split, −0.3 "
    "(p = 0.85, n = 1,191) on the first source’s questions, most of which lie outside its domain, and +5.3 "
    "within its own legal domain. Rewriting the questions in five styles, content fixed (1,345 queries), "
    "leaves the gains largely in place: what fails to transfer is tied to the source, not the "
    "wording. The first model gains +40.0 on a third, developer-written source (n = 25) and +24.2 on the "
    "second source’s Urdu questions; zero-shot BGE-M3 trails it by 16.1 points on the first source’s held-out questions. We "
    "also report three evaluation defects, none visible in the metrics: an index containing its own test "
    "answers, a wrong gold-label join, and target leakage between the two models. Deterministic "
    "interventions that encode legal structure, such as a statutory-scope rule, cannot fail this way by "
    "construction; their generality is a hypothesis supported by one worked case.", None, None, 2)])

# ── I. Introduction ──────────────────────────────────────────────────────────
remove(P[11]._p)                 # merged into P[10] below (repeated the result)
set_text(P[12], [("• ", None, None, 0), ("Transfer measurement of retrieval fine-tuning ", None, None, 1),
                 ("for two independently trained models at a tenfold scale difference, with paired significance "
                  "tests, confidence intervals, a domain- and script-matched comparison, a 1,345-query style grid, "
                  "and a zero-shot BGE-M3 baseline (Section V-B).", None, None, 2)])
set_text(P[13], [("• ", None, None, 0), ("Three evaluation defects and how each was found: ", None, None, 1),
                 ("a leaking index, a wrong gold-label join, and target leakage between one model’s training "
                  "data and another’s test set, none visible in the metrics (Section V-D).", None, None, 2)])

plain(P[10],
      "When no independent evaluation set exists, developers build one, tune against it, and report the "
      "number. We set out to improve retrieval for this jurisdiction and measured both fine-tuned retrievers "
      "twice: on questions from the distribution each was developed against, and on questions from other "
      "sources. We report this as a largely negative result. Fine-tuned gains largely survived rewording of "
      "the same questions, but on a second generator’s English questions they vanished, even with domain and "
      "script held fixed. The same questions rendered in Urdu or Roman Urdu, and a third, developer-written "
      "source, kept a gain: the in-distribution number did not predict which. Deterministic interventions that "
      "encode a property of the law, such as statutory scope, have no training distribution to overfit and so "
      "cannot fail this way; whether they generalise is a question one worked case does not settle. Our "
      "contributions:")
lead(P[15], "Scope of claims. ",
     "The defects below were found in our own system and are reported as findings: each was invisible to the "
     "metric meant to catch it, and these failure modes are not specific to a single model configuration. We "
     "claim no end-to-end improvement in answer correctness and no Pakistan-wide coverage; Section VII states "
     "each limit.")

# ── III-A. Corpus and Retrieval (Reviewer 3) ─────────────────────────────────
plain(P[22],
      "The statute corpus is drawn from 969 Pakistani legal documents [16] (Ministry of Law and Justice PDFs, "
      "ODC-BY licence), supplemented by instruments from the official consolidated legislation service [17] "
      "(accessed Aug. 2026), including the Code of Civil Procedure 1908 and 20 family-law statutes absent from "
      "the public collection: 10,042 statutory chunks in four collections (civil, criminal, family, "
      "constitutional; Fig. 1). The bulk dataset is assigned to collections by keyword rules on file names; "
      "directly fetched statutes are assigned, with their jurisdiction, by an explicit registry, and "
      "unregistered files are skipped. Text is split at section boundaries; sections longer than 800 "
      "characters are windowed (800 characters, 100 overlap). Every chunk records its statute, section number, "
      "province, legal domain and source file; registry-ingested chunks also record a content hash, the parser "
      "version and the provision’s status (e.g. omitted, schedule), and have contents pages and "
      "table-of-contents stubs removed before indexing. Enactment and amendment dates are not modelled; the corpus "
      "is a snapshot. A bilingual constitutional Q&A set [18] supplies evaluation questions only and is not "
      "indexed (Section V-D). A separate judgment corpus of 7,529 chunks from six courts supports case-law "
      "retrieval.")
set_text(P[25], [(
    "Retrieval is hybrid: BM25 and dense multilingual-e5-base [7] embeddings, chosen over larger multilingual "
    "encoders because the system is deployed on CPU (a larger encoder is compared zero-shot in Section V-B), "
    "combined by weighted ensemble (0.6 lexical, 0.4 dense). The lexical channel is weighted "
    "higher because exact statute and section references carry disproportionate signal. Both channels are "
    "filtered by province: a query for a given province retrieves only that province’s provisions or federal "
    "ones. A rule-based alias layer rewrites cross-jurisdictional references (e.g. Indian Penal Code → "
    "Pakistan Penal Code) before retrieval.", None, None, 0)])
lead(P[26], "Reproducibility. ",
     "Both fine-tuned retrievers are public at pinned revisions (see Code and Data Availability), and every "
     "number in Section V-B was recomputed from per-question ranks on those weights (BGE-M3 at revision "
     "5617a9f).")

# ── III-B. Verified Citation Supervision (duplicates: Reviewer 3) ────────────
plain(P[29],
      "Four sequential filters are applied. (1) LEGAL-UQA rows dropped (911), since that dataset provides our "
      "evaluation set. (2) Citations naming an unindexed section dropped (720). (3) Citations validated by "
      "rarity-weighted vocabulary overlap with the answer; wrong citations dropped (203). (4) Exact duplicates "
      "removed. 5,883 pairs survive (52.6%), split 80/20 into 4,692 training and 1,191 held-out pairs so that no "
      "gold passage appears on both sides. No held-out query occurs verbatim in training; 47 (3.9%) have a "
      "training query with embedding cosine ≥ 0.95, and excluding them leaves the gain of Section V-B at +25.9. "
      "32% of the pairs join an Urdu-script query to English statute, the code-switched case for which no training data "
      "previously existed. Validation also caught a corpus defect: 164 constitutional Schedule paragraphs had "
      "been indexed as Articles 1–8 (fundamental rights and the high-treason provision).")
plain(P[30], "TABLE I.  TRAINING AND EVALUATION DATA FOR THE TWO MODELS")
fill_table(T[0], [
    ("Property", "Constitutional model", "General model"),
    ("Training pairs", "471", "4,692"),
    ("Own held-out split", "121 (LEGAL-UQA)", "1,191 (citation)"),
    ("Out-of-distribution set", "1,191 (citation)", "128 (LEGAL-UQA)"),
    ("Legal domains / Urdu-script", "1 / 0%", "5 / 32%"),
    ("Source dataset", "LEGAL-UQA [18]", "Verified citation corpus"),
])
remove(P[32]._p)                 # "Note on dataset partitioning" (superseded by Table I + IV)

# ── IV. Evaluation Protocol ──────────────────────────────────────────────────
remove(P[34]._p)                 # pooled-traffic protocol: not used for any reported number
plain(P[35],
      "Two models are trained independently (Table I), both fine-tuning multilingual-e5-base in the "
      "Sentence-BERT bi-encoder architecture [19] with multiple-negatives ranking loss [20], hard negatives "
      "mined from the deployed retriever, two epochs, batch 12, lr = 2 × 10⁻⁵, max-length 224, one run each. "
      "Both splits group questions by connected components over shared gold chunks, so no gold chunk appears "
      "in both halves of a model’s own split. For Table II each model is evaluated on its own held-out split "
      "and on the other source’s questions, ranking the 9,042-passage corpus of the training bundle (a gold "
      "passage below rank 10 counts as a miss). Significance is McNemar’s exact test [21] on paired Hit@1 outcomes; intervals are 95% bootstrap "
      "confidence intervals (10,000 resamples).")
plain(P[36], "Retrieval is reported by Hit@k, mean reciprocal rank over the top 10 (MRR), and nDCG@k [22]:")

# ── V. Results ───────────────────────────────────────────────────────────────
# Page budget (style grid, BGE-M3 added): the corpus-history note is dropped and
# V-A / future work are tightened; no result or claim is removed.
remove(P[42]._p)
plain(P[46],
      "Reporting this as a uniform failure would overstate it. Across six queries the reranker improved three, "
      "left two unchanged, and badly worsened one, but the one it worsens is the case that motivated it, and "
      "those it improves were already nearly correct. It sharpens rankings that did not need sharpening while "
      "inverting the one that did.")
plain(P[47],
      "We attribute this to train/test domain mismatch rather than model capacity. The MS-MARCO checkpoint "
      "scores topical overlap between a question and a web passage; the distinction here (whether tenant means a "
      "cultivator under an 1887 revenue statute or an occupant of urban premises under a 2009 one) is one of "
      "legislative scope. Prior work reports the same direction of effect in U.S. legal case retrieval [24]; "
      "that this reproduces on statutory retrieval in a different jurisdiction and script indicates that these "
      "failure modes are not specific to a single model configuration.")
plain(P[85],
      "Second, 20 % to 27 % of each collection is fragments under 200 characters, and 11 % of failures are "
      "recall rather than ranking; chunking aligned to statutory structure, with instrument and section "
      "metadata prepended before embedding, addresses both [27].")
_fig1 = d.inline_shapes[0]
_fig1.width, _fig1.height = int(_fig1.width * 0.85), int(_fig1.height * 0.85)

# V-B. Domain fine-tuning: the corrected, reproduced numbers
plain(P[51],
      "Table II reports both models on both sources. The general model gains +26.5 Hit@1 on its own 1,191 "
      "held-out citation pairs (41.5% → 68.0%; 377 base misses fixed against 61 base hits lost, McNemar "
      "p < 10⁻⁵⁰) and +2.3 on 128 LEGAL-UQA questions written by a different generator, none of which shares a "
      "gold passage with its training data (CI −6.2 to +10.9; 17 fixed, 14 lost, p = 0.72). Part of the "
      "in-distribution gain is script: +47.3 on Urdu-script queries and +16.5 on English ones, while the "
      "out-of-distribution set is English. Holding domain and script fixed, English constitutional questions "
      "gain +23.3 in-distribution (n = 236, p < 10⁻¹¹) against +2.3 out of it.")
plain(P[52],
      "The constitutional model shows the mirror pattern. On its own held-out split (121 questions sharing no "
      "gold passage with its training data) it gains +15.7 (CI 7.4 to 24.0, p = 0.0005); on the citation "
      "questions it changes by −0.3 (CI −2.9 to +2.3, p = 0.85). Within its own domain (the 337 constitutional "
      "citation questions) it keeps +5.3 (CI 0.6 to 10.1, p = 0.036), a third of its in-distribution gain, and "
      "on evidence-law questions it loses 9.2 points (p = 0.009). Ten times the data, five domains and two "
      "scripts bought a larger in-distribution gain and no measurable out-of-distribution one: at 95% "
      "confidence the general model’s out-of-distribution gain is below +11 points, against +23.3 on matched "
      "in-distribution questions.")
remove(P[53]._p)
# Fig. 3 (image + caption) is replaced by Table II, which carries the intervals.
cap2 = clone_after(P[52]._p, P[30])
plain(cap2, "TABLE II.  ΔHIT@1 OVER BASE (POINTS), 95% BOOTSTRAP CI, McNEMAR EXACT p")
t2 = deepcopy(T[0]._tbl)
cap2._p.addnext(t2)
spacer = deepcopy(P[31]._p)
t2.addnext(spacer)
T2 = docx.table.Table(t2, P[52]._parent)
fill_table(T2, [
    ("Evaluated on", "General model", "Constitutional model"),
    ("Own held-out split", "+26.5 [23.5, 29.6] p<10⁻⁵⁰ (n=1,191)", "+15.7 [7.4, 24.0] p=0.0005 (n=121)"),
    ("Other source", "+2.3 [−6.2, 10.9] p=0.72 (n=128)", "−0.3 [−2.9, 2.3] p=0.85 (n=1,191)"),
    ("Matched domain", "+23.3 own vs +2.3 other (English const.)", "+5.3 [0.6, 10.1] p=0.036 (n=337)"),
    ("MRR, own → other", "0.516→0.758 | 0.605→0.632", "0.568→0.690 | 0.516→0.516"),
])
remove(P[54]._p)
remove(P[55]._p)

# Fig. 2 (one case's rank per pipeline stage) is dropped for page budget: the
# prose of V-A and Table V carry its result (rank 3 -> 10).
P[45].runs[0].text = P[45].runs[0].text.replace(" (Fig.\xa02)", "")
assert "Fig" not in P[45].runs[0].text
remove(P[48]._p)
remove(P[49]._p)

# Style grid and BGE-M3 (paper/reeval:analysis_stylegrid.txt, analysis_bgem3.txt,
# analysis_thirdstyle.txt). The grid separates wording from source.
set_text(P[50], [("B.  Domain Fine-Tuning: Gains Tied to the Question Source", None, None, 0)])
sg = clone_after(spacer, P[52])
set_text(sg, [("Style or source? ", True, True, 0), (
     "To separate the wording of the other source’s questions from their content, three sets were rewritten "
     "in four further styles with content and gold passage fixed (Table III; 1,345 queries): the 128 LEGAL-UQA "
     "questions, the constitutional model’s own 121, and 23 developer-written queries, a third source whose gold "
     "sections are absent from the general model’s training data. Urdu LEGAL-UQA comes from the dataset; other "
     "rewrites are LLM-generated and rejected if they add a number or a provision reference. For example, "
     "the LEGAL-UQA question “How long is the term for the Chairman or Deputy Chairman of the Senate?” "
     "becomes “What is the length of the term for the Senate’s Chairman or Deputy Chairman?” in layperson "
     "English, “Senate ke Chairman ya Deputy Chairman ka term kitna lamba hota hai?” in Roman Urdu, and "
     "“Senate Chairman term length” as keywords. Rewording does not remove a gain: the constitutional "
     "model keeps +11.8 to +17.4 in four of five styles, and the general model keeps +22.7 to +39.1 on the "
     "developer-written queries (+40.0 on all 25 clean ones, p = 0.002). On English LEGAL-UQA no wording yields "
     "a significant gain, so what fails to transfer is tied to the source, not the style. Cross-script alignment "
     "does transfer: Urdu and Roman Urdu renderings of those questions gain +24.2 and +17.5 (p < 0.001).",
     False, False, 0)])
cap3 = clone_after(sg._p, P[30])
plain(cap3, "TABLE III.  ΔHIT@1 OVER BASE BY QUESTION STYLE, CONTENT AND GOLD FIXED")
t3 = deepcopy(T[1]._tbl)
cap3._p.addnext(t3)
spacer3 = deepcopy(P[31]._p)
t3.addnext(spacer3)
T3 = docx.table.Table(t3, P[52]._parent)
fill_table(T3, [
    ("Style", "General, dev.-written", "General, LEGAL-UQA", "Const., own split"),
    ("Original", "+39.1*", "+2.3", "+15.7*"),
    ("Urdu", "+30.0*", "+24.2*", "+17.4*"),
    ("Layperson English", "+22.7", "+6.3", "+15.0*"),
    ("Roman Urdu", "+27.3*", "+17.5*", "+11.8*"),
    ("Keyword", "+36.4*", "+7.1", "+6.7"),
    ("n per cell", "20–23", "126–128", "119–121"),
])
bg = clone_after(spacer3, P[52])
set_text(bg, [("A larger encoder. ", True, True, 0), (
     "Zero-shot BGE-M3 [25] (dense, sequence length 512) reaches 51.9% Hit@1 on the citation test set, against 41.5% for "
     "base e5 and 68.0% for the general model (p < 10⁻²³), and 28.0% against 60.0% on the 25 developer-written "
     "queries (p = 0.021); its lead over base e5 is Urdu script (+29.8; English +1.0). On LEGAL-UQA it matches "
     "the general model in Urdu (41.4% vs 42.2%) and English (51.6% vs 54.7%, p = 0.56). No encoder that has "
     "not seen these English questions improves significantly on base e5 (52.3%); only memorisation does "
     "(Section V-D).",
     False, False, 0)])

# V-C. Fusion
plain(P[57],
      "The deployed retriever fuses BM25 at 0.6 with dense at 0.4. On the constitutional model’s own held-out "
      "split, searched over the deployed constitutional collection with both models’ indexes rebuilt at the "
      "same sequence length, its dense-only gain (+16.5; +15.7 in the Table II reproduction, one question "
      "apart) becomes +6.6 under fusion: the hybrid base already scores 52.1% Hit@1 against 43.8% dense, so BM25 "
      "supplies 8.3 points that overlap with what fine-tuning teaches the dense channel. Fusion also repairs "
      "the characteristic regression: four exact-citation lookups that fell from rank 1 to absent under "
      "dense-only retrieval fall at worst to rank 3 under fusion. A system reporting only its dense ablation "
      "would overstate both the benefit and the harm.")

# V-D. Contaminations (corrected attribution of the leakage)
set_text(P[61], [("(b) Gold labels were systematically wrong. ", None, None, 0), (
    "Joining evaluation questions to gold passages by section heading produced an off-by-one: heading stubs "
    "extracted from the source PDF matched section headings, not the chunks holding their body text. "
    "Retrieval returned the correct chunk and the evaluation script scored it a miss: MRR 0.114 under the "
    "broken join, 0.581 after rebuilding it on verbatim body n-grams, with no change to the retriever. This "
    "defect deflated the result; the other two inflated theirs.", False, False, 1)])
set_text(P[62], [("(c) Target leakage across models. ", None, None, 0), (
    "The constitutional model’s 121 held-out questions are clean for it, but 99 of them share a gold passage "
    "with the general model’s training positives: there the general model gains +28.3, on the other 22 +9.1 "
    "(not significant). Conversely, 106 of the 128 LEGAL-UQA questions are training questions of the "
    "constitutional model, whose apparent 76.6% Hit@1 on that set is memorisation (+29.2 on the 106, 0.0 on "
    "the 22 it never saw). Each set is therefore used only for the model it is clean for (Table II).",
    False, False, 1)])
# Plain (a)/(b)/(c): the circled digits came from a non-template font (MS PGothic).
set_text(P[60], [("(a) Index contained test answers. ", None, None, 0), (P[60].runs[1].text, None, None, 1)])
remove(P[63]._p)
plain(P[64], "TABLE IV.  CONTAMINATIONS: WHAT EACH DISTORTED AND THE CORRECTION")
fill_table(T[1], [
    ("Mechanism", "Affected metric", "Distorted value", "Handling"),
    ("(a) Index Q&A pairs", "Hit@1, constitutional", "own answer at rank 1", "pairs removed from index"),
    ("(b) Wrong gold join", "MRR, constitutional", "0.114", "0.581 (join rebuilt)"),
    ("(c) Leak into general model", "Hit@1 on 121-set", "+24.8 (99/121 leaked)", "set used for constitutional only"),
    ("(c) Leak into constitutional", "Hit@1 on 128-set", "76.6% (106/128 seen)", "set used for general only"),
])
set_text(P[59], [(
    "The fine-tuning results above were subjected to contamination checks that changed several earlier "
    "numbers; Table IV summarises them.", None, None, 0)])
remove(P[66]._p)                 # table note superseded

# ── VI. Discussion (Reviewer 4: the taxonomy) ────────────────────────────────
subA = clone_after(P[67]._p, P[56])
set_text(subA, [("A.  What Transferred, and What Was Measured", None, None, 0)])
plain(P[68],
      "Table V states, for each intervention, what it encodes and what evidence we have under a change of "
      "question source or style. Only the learned interventions were measured: their gains survived rewording, held on a developer-written source and across scripts, and "
      "vanished on English questions of the other generator, even within the same legal domain. The deterministic "
      "ones were not measured, and their “transfer” is true by construction: a statutory-scope rule or a corpus "
      "repair has no training distribution to overfit, so what remains open for them is coverage, which one "
      "worked case cannot establish. The supported conclusion is narrower than a taxonomy: an in-distribution "
      "gain does not predict which of these outcomes a new source will produce. Our data do not explain why "
      "English LEGAL-UQA resists every encoder we tried while its Urdu rendering does not; register alone is "
      "ruled out, since rewording leaves the gains intact (Table III).")
plain(P[69], "TABLE V.  INTERVENTIONS: WHAT EACH ENCODES, AND THE EVIDENCE UNDER A CHANGE OF SOURCE OR STYLE")
fill_table(T[2], [
    ("Intervention (encodes)", "Evidence under a change of question source or style"),
    ("Fine-tuned retriever, general (citation pairs)",
     "Measured: +26.5 own; other source +2.3, its Urdu +24.2; developer-written +40.0"),
    ("Fine-tuned retriever, constitutional (LEGAL-UQA pairs)",
     "Measured: +15.7 own, kept in 4 of 5 styles; other source −0.3; same domain +5.3"),
    ("MS MARCO cross-encoder (topicality)", "Six queries; on the motivating case rank 3 → 10"),
    ("Statutory-scope rule (legal scope)", "One worked case, rank 3 → 1; deterministic, not measured"),
    ("Corpus repairs (documents)", "Deterministic; not measured under a style change"),
])
for el in (P[71]._p, P[72]._p, T[3]._tbl, P[73]._p):   # cumulative ablation (mixed sets/metrics)
    remove(el)
for el in (P[76]._p, P[77]._p):                       # Fig. 4: a confidence result, not transfer
    remove(el)
plain(P[75],
      "We do not claim fine-tuning cannot work for legal retrieval, only that a gain measured on one generator’s "
      "questions is not evidence of a gain on another’s: the same model gained +40.0 on one new source and +2.3 on "
      "another, and neither outcome is visible when the test set shares the generator. A natural "
      "counterargument is rule scalability: deterministic rules require domain engineering per conflict, whereas "
      "statistical models promise zero-shot coverage. Our evidence for rules is one conflict (Section V-A), where "
      "a rule fixed what an off-the-shelf model inverted; how many conflicts such rules can cover is open.")

plain(P[79],
      "Each headline number changed when it was checked: two contaminations inflated a result, one deflated "
      "it, and none was visible in the metric. We draw three practical conclusions.")
set_text(P[81], [("A generated evaluation set is a single source. ", None, None, 0), (
    "Both datasets supplying our labels were LLM-generated against statute: usable as training signal since "
    "the citation is checkable, but unreliable as benchmarks, since a model trained on one generator is then "
    "tested on that generator’s choice of questions. The +23.3 to +2.3 drop on matched questions shows how much "
    "that choice can matter; rewording the questions (Table III) does not substitute for a second source.",
    False, False, 1)])
set_text(P[82], [("The protocol determined the conclusions more than any technique did. ", None, None, 0), (
    "Out of distribution, gains appeared on one new source and on Urdu-script questions and not on another "
    "source, and no in-distribution number predicted which. Reporting unverified in-distribution metrics "
    "yields unfalsifiable claims.", False, False, 1)])
plain(P[84],
      "Three items address open threats. First, 3,852 independently sourced Pakistani legal questions remain "
      "unused in training. Labelling a subset with two annotators, reporting Krippendorff’s α [26], and "
      "freezing half before development begins would yield the first evaluation set this work could not have "
      "tuned against; pre-registering the predicted effect and opening the frozen half once converts a "
      "measurement into evidence.")
fw3 = clone_after(P[85]._p, P[84])
plain(fw3,
      "Third, why English LEGAL-UQA resists every encoder we tried while its Urdu rendering does not should be "
      "tested directly, for instance by training on several generators or with a structure-aware objective. "
      "Fine-tuning BGE-M3 [25] is the obvious next model, within the CPU budget of Section III-A.")


# ── VII. Threats (Reviewer 1: table shortened into prose) ────────────────────
plain(P[87],
      "The limits are stated together so they can be weighed as a set. (i) Every evaluation set is "
      "generator-derived or developer-built; 3,852 independently sourced questions are identified, and a "
      "two-annotator, frozen benchmark is future work. (ii) The out-of-distribution sets are small (128) or "
      "partly off-domain (1,191 for the constitutional model), so intervals, not point estimates, carry the "
      "claims. (iii) Each model was trained once; seed variance is unmeasured. (iv) Provincial coverage is "
      "Punjab only (1,608 of 10,042 chunks), the corpus has no amendment dates, and statute is weighted over "
      "case law. (v) Generation correctness is unmeasured: all claims are retrieval-level, relevance judgements "
      "are the authors’ own, and a spot check of 20 retrieved passages found the governing section in 17. "
      "(vi) The scope-rule and cross-encoder results rest on one worked case and are reported as mechanisms, "
      "not rates. (vii) Splits separate gold passages, not whole statutes or source documents; a statute-level "
      "split would be stricter. (viii) Style rewrites other than LEGAL-UQA’s Urdu are LLM-generated and "
      "filtered automatically, not by native speakers. Threats concerning evaluation provenance would, "
      "if anything, inflate the in-distribution "
      "numbers we argue against.")
for el in (P[88]._p, T[4]._tbl, P[89]._p, P[90]._p):
    remove(el)

# ── VIII. Conclusion ─────────────────────────────────────────────────────────
plain(P[92],
      "Retrieval for a low-resource, code-switched jurisdiction is not adequately measured by a single number "
      "on a developer-built evaluation set. Fine-tuning a retriever on domain data gained +26.5 Hit@1 on its own "
      "distribution and +2.3 (95% CI −6.2 to +10.9) on another generator’s English questions, yet +40.0 on a "
      "third, developer-written source and +24.2 on the second source’s Urdu questions; rewording did not "
      "remove a gain, and the in-distribution number did not predict transfer. A second "
      "model gained +15.7 on its own split and −0.3 on the first model’s questions. Three contaminations, none "
      "visible in "
      "the metrics, had distorted these numbers until they were checked.")

# ── Code and data availability (camera-ready: no anonymous links) ────────────
plain(P[97],
      "The fine-tuned retrievers are public: huggingface.co/usama1111/e5-pakistani-legal (revision 0efe7b2b) "
      "and huggingface.co/usama1111/e5-pak-legal-constitutional (revision 6aec3e7a). Ingestion pipelines, "
      "contamination-detection and evaluation scripts, per-question ranks, the 1,345 style-grid queries and the "
      "5,883-pair citation corpus "
      "are available from the authors on request. The underlying statute and judgment corpora are third-party "
      "datasets cited in [16]–[18]; we do not redistribute raw source files.")

# ── References ───────────────────────────────────────────────────────────────
plain(P[122],
      "[24] A. B. Hou et al., “CLERC: A dataset for U.S. legal case retrieval and retrieval-augmented analysis "
      "generation,” in Findings of NAACL, 2025. [Online]. Available: https://arxiv.org/abs/2406.17186")
plain(P[125],
      "[27] S. Maniyar, D. Singh, and R. K. Reddy, “Enhancing legal LLMs through metadata-enriched RAG "
      "pipelines and direct preference optimization,” 2026, arXiv:2603.19251. [Online]. Available: "
      "https://arxiv.org/abs/2603.19251")
# v18 reference errors found in the final check (each verified at the source):
plain(P[100],
      "[2] I. Chalkidis, M. Fergadiotis, P. Malakasiotis, N. Aletras, and I. Androutsopoulos, “LEGAL-BERT: The "
      "muppets straight out of law school,” in Findings of EMNLP, 2020, pp. 2898–2904. [Online]. Available: "
      "https://doi.org/10.18653/v1/2020.findings-emnlp.261")
plain(P[102],
      "[4] Y. Ma et al., “LeCaRD: A legal case retrieval dataset for Chinese law system,” in Proc. ACM SIGIR, "
      "2021. [Online]. Available: https://doi.org/10.1145/3404835.3463250")
plain(P[110],
      "[12] I. Magar and R. Schwartz, “Data contamination: From memorization to exploitation,” in Proc. ACL "
      "(Short Papers), 2022, pp. 157–165. [Online]. Available: https://doi.org/10.18653/v1/2022.acl-short.18")
plain(P[111],
      "[13] O. Sainz, J. A. Campos, I. García-Ferrero, J. Etxaniz, O. L. de Lacalle, and E. Agirre, “NLP "
      "evaluation in trouble: On the need to measure LLM data contamination for each benchmark,” in Findings of "
      "EMNLP, 2023, pp. 10776–10787. [Online]. Available: https://arxiv.org/abs/2310.18018")
plain(P[113],
      "[15] C. Deng, Y. Zhao, X. Tang, M. Gerstein, and A. Cohan, “Investigating data contamination in modern "
      "benchmarks for large language models,” in Proc. NAACL, 2024, pp. 8706–8719. [Online]. Available: "
      "https://aclanthology.org/2024.naacl-long.482")
plain(P[119],
      "[21] Q. McNemar, “Note on the sampling error of the difference between correlated proportions or "
      "percentages,” Psychometrika, vol. 12, no. 2, pp. 153–157, 1947. [Online]. Available: "
      "https://doi.org/10.1007/BF02295996")

# Geifman (selective answering) was cited only by the removed IDF aside.
remove(P[123]._p)
r28 = clone_after(P[122]._p, P[122])
plain(r28,
      "[25] J. Chen, S. Xiao, P. Zhang, K. Luo, D. Lian, and Z. Liu, “M3-Embedding: Multi-linguality, "
      "multi-functionality, multi-granularity text embeddings through self-knowledge distillation,” 2024, "
      "arXiv:2402.03216. [Online]. Available: https://arxiv.org/abs/2402.03216")

# ── table geometry ───────────────────────────────────────────────────────────
# v18's grids summed to 10,440 dxa against a 5,040-dxa column, so every table
# overflowed into the gutter. Fit each to the column (total 4,968 dxa).
def fit_widths(t, widths):
    tbl = t._tbl
    pr = tbl.tblPr
    w = pr.find(qn("w:tblW"))
    w.set(qn("w:type"), "dxa")
    w.set(qn("w:w"), str(sum(widths)))
    grid = tbl.find(qn("w:tblGrid"))
    for gc, wd in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(wd))
    for tr in tbl.findall(qn("w:tr")):
        for tc, wd in zip(tr.findall(qn("w:tc")), widths):
            tcw = tc.find(qn("w:tcPr")).find(qn("w:tcW"))
            tcw.set(qn("w:type"), "dxa")
            tcw.set(qn("w:w"), str(wd))


fit_widths(T[0], [1700, 1634, 1634])          # Table I
fit_widths(T2, [1000, 1984, 1984])            # Table II
fit_widths(T[1], [1328, 1160, 1180, 1300])    # Table III
fit_widths(T[2], [1868, 3100])                # Table V
fit_widths(T3, [1170, 1266, 1266, 1266])      # Table III (style grid)


def keep_with_next(p):
    ppr = p._p.get_or_add_pPr()
    if ppr.find(qn("w:keepNext")) is None:
        k = ppr.makeelement(qn("w:keepNext"), {})
        ppr.insert(0, k)


for cap in (P[30], cap2, cap3, P[64], P[69]):
    keep_with_next(cap)
# A table never splits across a column/page break (Table I did).
for t in (T[0], T2, T3, T[1], T[2]):
    for row in t.rows[:-1]:
        for cell in row.cells:
            for para in cell.paragraphs:
                keep_with_next(para)
# Headings never end a column alone ("IV. EVALUATION PROTOCOL" did).
import re
for para in d.paragraphs:
    if re.match(r"^([IVX]+|[A-H])\.\s{2}\S", para.text) or para.text in (
            "ETHICAL CONSIDERATIONS", "CODE AND DATA AVAILABILITY", "REFERENCES"):
        keep_with_next(para)
# Long unbreakable URLs justify badly; left-align the availability paragraph.
P[97].alignment = 0

# ── FIT 2026 camera-ready checklist: IEEE template formatting ────────────────
# Matched against paper/conference-template-letter.docx (the official template).
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_BREAK
from docx.shared import Pt

COPYRIGHT = "979-8-3195-0206-3/26/$31.00 ©2026 IEEE"
TEMPLATE_LR_MARGIN = 893          # 44.65 pt, the template's left/right margin


def run_flags(r, bold=None, italic=None, small_caps=None):
    if bold is not None:
        r.bold = bold
    if italic is not None:
        r.italic = italic
    if small_caps is not None:
        r.font.small_caps = small_caps


# A. Links: unwrap every hyperlink (citations, e-mail, reference URLs) into plain
# runs, and drop underline, so links are neither coloured nor underlined.
body = d.element.body
for h in list(body.iter(W + "hyperlink")):
    parent = h.getparent()
    idx = parent.index(h)
    for r in list(h):
        parent.insert(idx, r)
        idx += 1
    parent.remove(h)
for u in list(body.iter(W + "u")):
    u.getparent().remove(u)

# A. Author block: one column per author, template lines, no numbering, plain
# e-mail. Order unchanged from the accepted manuscript.
AUTHORS = [("Muhammad Usama", "muhammadusamahoyrr@gmail.com"),
           ("Muhammad Amir Zarmaan Ullah Khan", "kzari898@gmail.com")]
title_p, a1, a2, sect_p = P[0], P[1], P[2], P[4]
remove(P[3]._p)
for p_auth, (name, mail), first in ((a1, AUTHORS[0], True), (a2, AUTHORS[1], False)):
    for child in list(p_auth._p):
        if child.tag != W + "pPr":
            p_auth._p.remove(child)
    p_auth.alignment = 1
    # Word keeps space-before at the top of column 1 but drops it at the top of
    # column 2, so the gap under the title is the title's space-after instead.
    p_auth.paragraph_format.space_before = Pt(0)
    p_auth.paragraph_format.space_after = Pt(12)
    lines = [(name, False), ("Department of Computer Science", True), ("COMSATS University Islamabad", True),
             ("Islamabad, Pakistan", False), (mail, False)]
    for i, (text, ital) in enumerate(lines):
        r = p_auth.add_run(text)
        r.font.size = Pt(9)                # template: Author runs are 9 pt (style says 11)
        r.italic = ital
        r.bold = False
        r.add_break()                    # after the e-mail too: blank lines before the abstract,
                                         # since space-after is dropped at a section break
    # Measured on Word renders: the template has 36 pt from the top of the last
    # author line to the top of the abstract; one blank line gave 21.5 pt here.
    # Word ignores space-before at the top of the abstract's section, so the
    # second blank line is set in 12 pt instead of 9 pt to reach 36 pt.
    gap = p_auth.add_run()
    gap.font.size = Pt(12)
    gap.add_break()
    # No column break: the continuous section balances its two columns, and a
    # paragraph kept whole lands one author per column (a break offset author 2).
    p_auth.paragraph_format.keep_together = True
# Section structure (as in the template): title 1-col | authors 2-col (continuous)
# | body 2-col (continuous) | closing 1-col (continuous) that balances page 6.
title_p.paragraph_format.space_after = Pt(24)      # template: 6 pt after title + 18 pt before authors
title_sect = deepcopy(sect_p._p.pPr.find(qn("w:sectPr")))
title_p._p.get_or_add_pPr().append(title_sect)
auth_sect = sect_p._p.pPr.find(qn("w:sectPr"))
a2._p.get_or_add_pPr().append(auth_sect)            # moves it out of the empty paragraph
remove(sect_p._p)
t_ = auth_sect.find(qn("w:type"))
if t_ is None:
    t_ = auth_sect.makeelement(qn("w:type"), {})
    auth_sect.insert(0, t_)
t_.set(qn("w:val"), "continuous")
cols = auth_sect.find(qn("w:cols"))
cols.set(qn("w:num"), "2")
cols.set(qn("w:space"), "216")                       # 10.8 pt, as the template's author columns

final_sect = body.find(qn("w:sectPr"))
body_sect = deepcopy(final_sect)
last_p = d.paragraphs[-1]
end_p = deepcopy(last_p._p)
for child in list(end_p):
    if child.tag != W + "pPr":
        end_p.remove(child)
last_p._p.addnext(end_p)
end_pPr = end_p.find(qn("w:pPr"))
if end_pPr is None:
    end_pPr = end_p.makeelement(qn("w:pPr"), {})
    end_p.insert(0, end_pPr)
end_pPr.append(body_sect)
ft = final_sect.find(qn("w:type"))
if ft is None:
    ft = final_sect.makeelement(qn("w:type"), {})
    final_sect.insert(0, ft)
ft.set(qn("w:val"), "continuous")
fc = final_sect.find(qn("w:cols"))
fc.set(qn("w:num"), "1")

for s in d.sections:
    s.left_margin = s.right_margin = docx.shared.Twips(TEMPLATE_LR_MARGIN)
# The template's two-column body section is narrower than its title/author
# sections: 45.35 pt left/right (907 dxa), 18 pt between columns.
TEMPLATE_BODY_LR_MARGIN = 907
assert len(d.sections) == 4                       # title | authors | body | closing
d.sections[2].left_margin = d.sections[2].right_margin = docx.shared.Twips(TEMPLATE_BODY_LR_MARGIN)

# C. Copyright notice: first page only, bottom-left, 8 pt (template footer style).
s0 = d.sections[0]
s0.different_first_page_header_footer = True
fp = s0.first_page_footer.paragraphs[0]
fp.text = ""
fr = fp.add_run(COPYRIGHT)
fr.font.size = Pt(8)
fr.font.name = "Times New Roman"
fp.alignment = 0
for s in d.sections[1:]:
    s.different_first_page_header_footer = False

# B. Abstract text bold, not italic ("Abstract" alone italic); keywords bold italic.
ab = P[5]
for i, r in enumerate(ab.runs):
    run_flags(r, bold=True, italic=(i == 0))
for r in P[6].runs:
    run_flags(r, bold=True, italic=True)

# D. Table captions: small caps, not bold. Section headings: small caps, not bold.
CAPTIONS = {
    P[30]: "Table I.  Training and Evaluation Data for the Two Models",
    cap2: "Table II.  ΔHit@1 over Base (Points), 95% Bootstrap CI, McNemar Exact p",
    cap3: "Table III.  ΔHit@1 over Base by Question Style, Content and Gold Fixed (* p < 0.05)",
    P[64]: "Table IV.  Contaminations: What Each Distorted and the Correction",
    P[69]: "Table V.  Interventions: What Each Encodes, and the Evidence under a Change of Source or Style",
}
for cp, text in CAPTIONS.items():
    set_text(cp, [(text, False, False, 0)])
    for r in cp.runs:
        run_flags(r, small_caps=True)
HEADS = {"INTRODUCTION": "Introduction", "RELATED WORK": "Related Work",
         "EXPERIMENTAL SETUP": "Experimental Setup", "EVALUATION PROTOCOL": "Evaluation Protocol",
         "RESULTS": "Results", "DISCUSSION": "Discussion", "THREATS TO VALIDITY": "Threats to Validity",
         "CONCLUSION": "Conclusion", "ETHICAL CONSIDERATIONS": "Ethical Considerations",
         "CODE AND DATA AVAILABILITY": "Code and Data Availability", "REFERENCES": "References"}
for para in d.paragraphs:
    m = re.match(r"^([IVX]+\.\s{2})?([A-Z][A-Z ]+)$", para.text)
    if m and m.group(2) in HEADS:
        set_text(para, [((m.group(1) or "") + HEADS[m.group(2)], False, False, 0)])
        for r in para.runs:
            run_flags(r, small_caps=True)
# Figure captions: justified, as the template's figure caption.
for para in d.paragraphs:
    if para.text.startswith("Fig.\xa0") or para.text.startswith("Fig. "):
        para.alignment = 3

# ── Proofreading pass (camera-ready recheck, 2026-10-25) ─────────────────────
def para_starting(prefix):
    hits = [p for p in d.paragraphs if p.text.startswith(prefix)]
    assert len(hits) == 1, (prefix, len(hits))
    return hits[0]


def fix(p, pairs):
    """String fixes on a paragraph whose first run may be a bold lead-in."""
    full = p.text
    for old, new in pairs:
        assert old in full, (old, full[:60])
        full = full.replace(old, new)
    head = p.runs[0].text if p.runs[0].bold else ""
    if head:
        set_text(p, [(head, None, None, 0), (full[len(head):], False, False, len(p.runs) - 1)])
    else:
        set_text(p, [(full, None, None, 0)])


# Related work: the "no analogue ..." clause appeared in two consecutive paragraphs.
fix(para_starting("Low-resource and hybrid retrieval."), [
    ("[8],[9]", "[8], [9]"),
    (" BEIR [10] and MTEB [11] evaluate zero-shot generalisation across datasets but have no analogue for a "
     "low-resource jurisdiction where the developer must build the only evaluation set that exists.", "")])
fix(para_starting("Generalisation and contamination in evaluation."), [("[12],[13],[14],[15]", "[12]–[15]")])

# One percent style throughout ("52.6%", not "20 %").
for para in d.paragraphs:
    for r in para.runs:
        if "\u202f%" in r.text:
            r.text = r.text.replace("\u202f%", "%")

# Equations (1)-(3): the sum runs over q in Q, not "p".
for para in d.paragraphs:
    r0 = para.runs[0] if para.runs else None
    if r0 is not None and "Σₚ" in r0.text:
        before, after = r0.text.split("Σₚ", 1)
        r0.text = before + "Σ"
        sub = deepcopy(r0._r)
        r0._r.addnext(sub)
        sub_run = docx.text.run.Run(sub, para)
        sub_run.text = "q∈Q"
        sub_run.font.subscript = True
        rest = deepcopy(r0._r)
        sub.addnext(rest)
        docx.text.run.Run(rest, para).text = after

# Second recheck: claims narrowed to what Table III shows (2 of 10 cells are
# not significant), V-B no longer says "no measurable out-of-distribution gain"
# (Table III has two), "both retrieval depths" defined now that Fig. 2 is gone.
fix(para_starting("The constitutional model shows the mirror pattern."), [
    ("bought a larger in-distribution gain and no measurable out-of-distribution one: at 95% confidence the "
     "general model’s out-of-distribution gain is below +11 points, against",
     "bought a larger in-distribution gain and none measurable on the other source’s English questions: at "
     "95% confidence it is below +11 there, against")])
fix(para_starting("Style or source?"), [
    ("Rewording does not remove a gain:", "Rewording leaves the gains largely intact:"),
    ("(+40.0 on all 25 clean ones, p = 0.002)",
     "(+40.0, p = 0.002, on the 25 with unseen gold passages)")])
fix(para_starting("Table V states, for each intervention"), [
    ("their gains survived rewording", "their gains largely survived rewording"),
    ("since rewording leaves the gains intact", "since rewording leaves the gains largely intact")])
fix(para_starting("The cross-encoder does not merely fail to help"), [
    ("at both retrieval depths.", "at both retrieval depths (10 and 50 candidates)."),
    ("MS-MARCO model", "MS MARCO model")])
fix(para_starting("We attribute this to train/test domain mismatch"), [
    ("The MS-MARCO checkpoint", "The MS MARCO checkpoint")])
fix(para_starting("The limits are stated together"), [
    ("(ii) The out-of-distribution sets are small (128) or",
     "(ii) The out-of-distribution sets are small (128; 25 developer-written) or")])
fix(para_starting("Retrieval for a low-resource, code-switched jurisdiction"), [
    ("rewording did not remove a gain, and", "rewording left the gains largely intact, and")])
assert not any("MS-MARCO" in para.text for para in d.paragraphs)

# Reviewer-eye layout pass.
# Table I sits where it is first cited (Section IV), not at the end of III-B,
# where it did not fit and left the bottom of page 2 empty.
_anchor = P[35]._p                                 # "Two models are trained independently (Table I) ..."
for _el in (P[30]._p, T[0]._tbl, P[31]._p):        # caption, table, spacer
    _anchor.addnext(_el)
    _anchor = _el
# Equations as in the template: centred, number flush right on a tab.
from docx.enum.text import WD_TAB_ALIGNMENT
_col = docx.shared.Twips((12240 - 2 * TEMPLATE_BODY_LR_MARGIN - 360) // 2)
for para in d.paragraphs:
    if para.runs and re.match(r"^\s*\(\d\)$", para.runs[-1].text) and "Σ" in para.runs[0].text:
        para.alignment = 0
        para.paragraph_format.first_line_indent = 0
        para.paragraph_format.left_indent = 0
        para.paragraph_format.tab_stops.add_tab_stop(int(_col / 2), WD_TAB_ALIGNMENT.CENTER)
        para.paragraph_format.tab_stops.add_tab_stop(_col, WD_TAB_ALIGNMENT.RIGHT)
        para.runs[0].text = "\t" + re.sub(r"\s{2,}", " ", para.runs[0].text)
        para.runs[-1].text = "\t" + para.runs[-1].text.strip()
# The line after the equations could not break (non-breaking spaces) and was
# stretched across the column.
fix(para_starting("where IDCG(q)"), [
    ("where IDCG(q)\xa0=\xa0Σᵢ 1/log₂(i+1) summed over i\xa0=\xa01…min(|G(q)|,\xa0k).",
     "where IDCG(q) = Σᵢ 1/log₂(i+1) for i from 1 to min(|G(q)|, k)."),
    ("\xa0", " ")])
# Every body paragraph carries the template's first-line indent, including the
# three that follow an unnumbered or section heading directly.
_indent = P[6].paragraph_format.first_line_indent
for _prefix in ("The limits are stated together", "The system provides legal information",
                "The fine-tuned retrievers are public"):
    para_starting(_prefix).paragraph_format.first_line_indent = _indent

# ── Final pass (2026-10-25, user-approved): layout, method detail, proofreading ──
# Fig. 1 follows the "Retrieval is hybrid" paragraph: as an anchor after the
# III-A corpus paragraph it did not fit the left column of page 2 and left 7
# lines empty there; it still opens the right column.
_fig = [p for p in d.paragraphs if p._p.xpath(".//w:drawing")]
assert len(_fig) == 1
_fig_p = _fig[0]._p
_cap_p = _fig_p.getnext()
assert "".join(_cap_p.itertext()).startswith("Fig.")
_hyb = para_starting("Retrieval is hybrid:")._p
_hyb.addnext(_fig_p)
_fig_p.addnext(_cap_p)
# Fusion stated exactly (backend/app/ai/pipelines/retriever.py: FIRST_STAGE_K = 10,
# LangChain EnsembleRetriever weights [0.6, 0.4] = weighted RRF with c = 60).
fix(para_starting("Retrieval is hybrid:"), [
    ("(a larger encoder is compared zero-shot in Section V-B), combined by weighted ensemble (0.6 lexical, 0.4 dense).",
     "(a larger encoder is compared zero-shot in Section V-B). Each channel returns its top 10, and the two lists "
     "are merged by weighted reciprocal rank fusion [9] (weights 0.6 lexical and 0.4 dense, constant 60)."),
    ("(e.g. Indian Penal Code", "(e.g., Indian Penal Code")])
# What Tables II and III measure (paper/reeval/*_colab.py: dense only, normalised,
# query:/passage: prefixes, length 224; BGE-M3 no prefixes, length 512).
fix(para_starting("Two models are trained independently"), [
    ("(a gold passage below rank 10 counts as a miss).",
     "(a gold passage below rank 10 counts as a miss). Tables II and III score dense retrieval alone, not the "
     "deployed fusion (Section V-C): embeddings are L2-normalised and ranked by cosine similarity, with the e5 "
     "prefixes “query: ” and “passage: ” at sequence length 224; BGE-M3 uses no prefixes and length 512.")])
# Grammar, punctuation and IEEE style.
fix(para_starting("Retrieval-augmented generation (RAG)"), [
    ("Queries arrive in English, Urdu script, and most commonly in Roman Urdu;",
     "Queries arrive in English, in Urdu script, and, most commonly, in Roman Urdu;")])
fix(para_starting("Legal NLP and RAG."), [("showed legal text benefits", "showed that legal text benefits")])
fix(para_starting("The statute corpus is drawn"), [
    ("legal domain and source file", "legal domain, and source file"),
    ("the parser version and the provision", "the parser version, and the provision"),
    ("(e.g. omitted, schedule)", "(e.g., omitted, schedule)")])
fix(para_starting("Fine-tuning a retriever requires"), [("(e.g.\xa0PPC", "(e.g.,\xa0PPC")])
fix(para_starting("Four sequential filters"), [
    ("removed. 5,883 pairs survive", "removed. In total, 5,883 pairs survive"),
    ("+25.9. 32% of the pairs join", "+25.9. Of the pairs, 32% join")])
fix(para_starting("Reporting this as a uniform failure"), [
    ("but the one it worsens is the case that motivated it, and those it improves were",
     "but the one it worsened is the case that motivated it, and those it improved were")])
fix(para_starting("We attribute this to train/test"), [("(whether tenant means", "(whether “tenant” means")])
fix(para_starting("The constitutional model shows the mirror"), [
    ("Ten times the data, five domains and two scripts", "Ten times the data, five domains, and two scripts")])
fix(para_starting("A larger encoder."), [("its lead over base e5 is Urdu script", "its lead over base e5 comes from Urdu script")])
# The cross-encoder is learned too but has no gains to speak of (Table V): name
# the measured interventions exactly, as the introduction now does.
fix(para_starting("Table V states, for each intervention"), [
    ("Only the learned interventions were measured:", "Only the fine-tuned retrievers were measured:"),
    ("The deterministic ones were not measured", "The deterministic interventions were not measured")])
fix(para_starting("The errors agree with the aggregates."), [
    ("‘What was omitted by S.R.O. No.", "“What was omitted by S.R.O. No."), ("85?’", "85?”")])
fix(para_starting("A generated evaluation set is a single source."), [
    ("usable as training signal", "usable as a training signal")])
fix(para_starting("The protocol determined the conclusions"), [
    ("Urdu-script questions and not on another source", "Urdu-script questions but not on another source")])
fix(para_starting("Three items address open threats."), [
    ("converts a measurement into evidence", "convert a measurement into evidence")])
fix(para_starting("Second, 20% to 27%"), [("of each collection is fragments under", "of each collection consists of fragments under")])
fix(para_starting("Every evaluation asset used here"), [
    ("frozen before development, and practitioner", "frozen before development and practitioner")])
fix(para_starting("The fine-tuned retrievers are public"), [
    ("style-grid queries and the 5,883-pair", "style-grid queries, and the 5,883-pair")])
fix(para_starting("[16]"), [("HuggingFace", "Hugging Face")])
fix(para_starting("[17]"), [
    ("2026. [Online]. Available: https://pakistancode.gov.pk/ (accessed Aug. 2026)",
     "2026. Accessed: Aug. 2026. [Online]. Available: https://pakistancode.gov.pk/")])
# IEEE reference style: journal, proceedings and book titles in italics.
_VENUES = {
    "[1]": "Proc. NeurIPS", "[2]": "Findings of EMNLP", "[3]": "Proc. NeurIPS", "[4]": "Proc. ACM SIGIR",
    "[5]": "Proc. EMNLP", "[6]": "Proc. ICLR", "[8]": "Found. Trends Inf. Retr.", "[9]": "Proc. ACM SIGIR",
    "[10]": "Proc. NeurIPS Datasets and Benchmarks Track", "[11]": "Proc. EACL",
    "[12]": "Proc. ACL (Short Papers)", "[13]": "Findings of EMNLP", "[14]": "Proc. ICLR", "[15]": "Proc. NAACL",
    "[19]": "Proc. EMNLP", "[21]": "Psychometrika", "[22]": "ACM Trans. Inf. Syst.",
    "[24]": "Findings of NAACL", "[26]": "Content Analysis: An Introduction to Its Methodology",
}
for _num, _venue in _VENUES.items():
    _p = para_starting(_num + " ")
    _t = _p.text
    assert _t.count(_venue) == 1, (_num, _venue)
    _i = _t.index(_venue)
    set_text(_p, [(_t[:_i], None, False, 0), (_venue, None, True, 0), (_t[_i + len(_venue):], None, False, 0)])

# Table II ends a column, so its spacer paragraph opened the next column as a
# blank line (and Word keeps space-before at a column top): no gap at all.
remove(spacer)
sg.paragraph_format.space_before = Pt(0)

d.save(str(OUT))
print("wrote", OUT.name)
