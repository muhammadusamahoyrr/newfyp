# Drafter -- open issues and final-text safeguard plan (2026-10-15)

Status: **OPEN**. None of these is fixed. A prompt instruction and a scorer metric exist for #3; neither stops an
invented fact from reaching the insertable text, so #3 stays open until a final-text safeguard passes the tests below.
No model run or holdout run is planned for this step.

## Open issues (evidence: results/v2_r3_dev, replay_guard8_from_v2_r3_dev)

| # | Row | Final text (abridged) | Why it is wrong | Today |
|---|---|---|---|---|
| 1 | V04 rep 1 | "under Order XIV Rule 5 CPC, the Court may amend the **parties** ..." | O.XIV r.5 lets the Court amend or strike out **issues** ("amend the issues or frame additional issues"); it says nothing about amending parties | SUPPORTED |
| 2 | V09 rep 1 | "... contravenes Section 341 CrPC, **rendering the proceedings invalid**" | s.341's text says the opposite: if the accused cannot be made to understand, "the Court **may proceed** with the trial" (with a report to the High Court) | SUPPORTED |
| 3 | V09 rep 1 | "the accused, **though not insane, is unable to understand** the proceedings" | a fact the request never gave; its wording is copied from s.341's text in the law context, not from the lawyer | insertable; scorer flags it (`invented_facts`) |

Why the current checks pass #1 and #2: both match on words (r.5's heading has "amend"; s.341's heading has "accused does
not understand proceedings"). Word agreement shows the provision is ABOUT the topic, not that it supports the claim's
OBJECT (#1) or its stated LEGAL EFFECT (#2).

## Proposed safeguards (all on the FINAL guarded text, before anything is insertable)

### S1 -- claim object (for #1)
For a relied-on citation whose clause has an action verb with an object ("amend the parties", "set aside the decree",
"strike out the plaint", "return the plaint"), the provision's own text (its rule slice) must contain the same verb with
the same object within a few words ("amend the issues" does not cover "amend the parties"). Missing -> NOT VERIFIED with
the reason ("its text provides for amending issues, not parties"); never withheld on this ground alone (a lexical check
cannot prove the claim wrong). Verb list = procedural verbs already in visible_authority; objects = nouns of the clause.

### S2 -- stated legal effect (for #2)
A sentence that attributes a legal CONSEQUENCE to a provision -- invalid / void / null / vitiated / without jurisdiction /
barred / abates / must be set aside -- is supported only if the provision's own text states that consequence (or its
negation is absent). If the text states a contrary course ("may proceed", "shall not be invalid", "shall not vitiate"),
the sentence is WITHHELD with that text quoted as the reason; if the text is silent, NOT VERIFIED.

### S3 -- input-fact fidelity (for #3)
Before the proposal is insertable, each sentence's factual assertions are compared with the lawyer's INPUT ONLY
(instruction, selected passage, current document, and the case record when a case is bound) -- never with the law
context, which is where #3 came from. Flag a sentence that asserts, about a party or event, a fact of these kinds not
present in the input:
  * a condition or state of a person (mental or physical condition, age/minority, absconding, illness, threats);
  * a date, period, amount, number, place or name;
  * an event (arrest, service, payment, dishonour, hearing outcome).
A flagged sentence is NOT insertable as is: it is listed with "states a fact you did not give: <words>" and offered back
with the fact replaced by a [placeholder] only as a separate, visible proposal the lawyer must choose. Facts given in the
input, [placeholders], and quotations of the law marked as such are never flagged.
Known limit: lexical; paraphrased or implied facts can escape. Measured, not assumed (below).

## Test plan -- what must pass before any of these is called fixed

Unit (fixtures, final text):
* S1: O.XIV r.5 "amend the parties" -> not verified; O.XIV r.5 "amend the issues" -> supported; O.VI r.17 "amend the
  plaint/pleadings" -> supported; O.I r.10 "add/strike out a party" -> supported; O.VII r.10 "return the plaint" ->
  supported (no regression of the V01/V02 fixes).
* S2: s.341 "renders the proceedings invalid" -> withheld, reason quotes "may proceed with the trial"; a provision whose
  text states the effect -> supported; silent text -> not verified; a sentence with no effect claim -> unaffected.
* S3: the V09 sentence -> not insertable, reason names "not insane / unable to understand"; the same words present in the
  instruction -> not flagged; names/dates from a filled template (T01-T04) -> not flagged; [placeholders] -> not flagged;
  a fact present only in the law context -> flagged; Urdu and Roman-Urdu inputs.
* UI: a flagged sentence never reaches "Insert"/"Replace"; the placeholder version is a separate proposal; reasons shown.
* Mutation: each safeguard's decisive line broken once must fail a test.

Regression on saved outputs (no model call): replay v2_r2_dev and v2_r3_dev. Must hold:
* #1 and #2 not SUPPORTED; #3 not insertable;
* no currently-valid Supported entry lost (O.VII r.10/11/13, s.151, s.561-A, s.489-F, s.499, s.502, s.54 ...);
* false withholds stay 0; every newly flagged sentence judged by hand and reported (false-flag count, not hidden).

Measurement (only after separate approval): a dev-only fresh run; later the locked holdout v3 once an independent
labeller has added fact and authority labels.

Done = unit + mutation + replay criteria above all pass, with the false-flag count reported. Until then #1-#3 stay open.

## Status after implementation (2026-10-15, dev-only, uncommitted; no model or holdout run)

Implemented in `app/ai/draft_claims.py`, wired into `visible_authority` (sections) and `draft_guard` (CPC rules, S3),
and the drafter panel (placeholder version as a separate proposal).

| # | Result on the saved outputs (replay_guard10_from_v2_r3_dev / _from_v2_r2_dev) | Status |
|---|---|---|
| 1 O.XIV r.5 "amend the parties" | NOT VERIFIED: "its text provides for amending issues ..., not parties" (S1; never withheld) | resolved for this case; S1 is lexical |
| 2 s.341 "rendering the proceedings invalid" | WITHHELD: "Section 341 CrPC's own text says otherwise: ... the Court may proceed with the trial" (S2). Root cause also fixed: "contravenes Section N" was read as a mere mention and never judged | resolved for this case |
| 3 invented facts | the V09 sentence is not insertable; V20's invented non-compete period ("twelve (12) months", 4 rows) is withheld and offered back as a separately checked "[placeholder]" version | **partly open**: lexical recall is limited (below) |

Measured:
* Replay, both runs (88 rows): S2/S3 withheld 5 sentences, all correct by hand (0 false flags) -- after fixing 7
  false flags of the first version (clause numbers "2.1"/"2.2"; Urdu section numbers split from "Section").
  False withholds of allowed authorities 0; empty proposals unchanged (3 / 5); valid Supported entries kept.
* `fact_fidelity_probe.json` (synthetic, not tuned on): invented facts caught **9 / 16** (56%); missed 7 -- paraphrased
  conditions ("lacks the capacity to comprehend"), events ("was in hospital", an alibi), motive, a family
  circumstance, "no previous criminal record", a hyphenated age. Given-fact controls falsely flagged **0 / 10**.
* Tests: tests/test_draft_guard_v2.py 124 (S1-S3, false-flag and quantity cases, Urdu); frontend
  lawyer_draft_assist 44 (invented fact never in the proposal; placeholder version separate and insertable only as
  checked). Mutation: 14 / 14 decisive lines caught.

What would close #3: a semantic check of factual assertions against the input (not lexical), measured on the probe and
on an independently labelled holdout. Until then the panel's guarantee is narrower: facts of the listed kinds that the
lawyer did not give never reach the insertable text; paraphrased facts can.

## Semantic fact-fidelity batch (2026-10-15, dev-only; nothing wired; no model or holdout run)

Dev set `fact_fidelity_dev.json`: the 157 sentences the model actually wrote in v2_r2_dev + v2_r3_dev (free drafting),
each labelled by hand against its request (developer labels, provisional): **22 state a case fact or term the lawyer
did not give** (e.g. "the fraud was discovered within three years", "complied with all conditions of the bond", the
offence charged, "twelve (12) months", "the language of the arbitration shall be English"); plus 7 Urdu probe rows and
4 Urdu sentence-boundary cases. Method `app/ai/fact_semantic.py` (local multilingual-e5-base; factual clauses only;
NOT wired). Results `fact_fidelity_eval.json` (`scripts/eval_fact_fidelity.py`):

| method | real outputs: caught / 22, false flags / 135 | probe: / 16, / 10 | Urdu: / 4, / 3 |
|---|---|---|---|
| lexical S3 (the guard today) | 5, 0 | 8, 0 | 1, 0 |
| semantic @0.82 | 0, 3 | 9, 2 | 2, 0 |
| semantic @0.84 | 8, 17 | 13, 2 | 4, 0 |
| semantic @0.86 | 9, 38 | 16, 3 | 4, 0 |
| lexical + semantic @0.84 | 12, 17 | 14, 2 | 4, 0 |

* The synthetic probe flatters the semantic method; on real outputs it buys recall with 13-28% false flags. Embedding
  similarity cannot tell "the lawyer said X" from "the draft adds a detail near X" -- not fit to BLOCK insertion.
* The lexical guard is precise (0 false flags on 148 clean sentences) but misses most real invented facts (17 of 22).
* Urdu sentence boundaries: fixed (no break after the normaliser's "Sec."), 4 / 4 cases correct; Urdu reliance phrases
  (کے تحت, بموجب, کی رو سے, کے مطابق) and a small Urdu legal-term glossary now let Urdu citations be judged
  (s.497 for bail supported; s.526 for bail not).
* No threshold was chosen. Issue #3 stays OPEN. Options that need a decision: an NLI / entailment model (new local
  model download), or a provider-based claim check on synthetic text only (privacy-gated) -- each to be measured on this
  set and an independently labelled one before any release claim.
