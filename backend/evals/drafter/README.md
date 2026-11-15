# Lawyer drafter evaluation (v1, 2026-10-14)

Measures the lawyer-side Draft Assistant (`/ai/draft/stream`): the real route, the
live `draft_stream` model, the real statute corpus, and the legal check
(`app/ai/draft_guard.py`). **Silver labels by one developer, not reviewed by a
lawyer. Scores are checklist matches, not a finding that any draft is legally
correct or court-ready.**

## Files

| File | What it is |
|---|---|
| `provenance.json` | Inventory of the source collection: 24 DOCX templates exported from the aiattorney.com.pk drafter on 2026-10-14 (third-party, user-authorised copy). sha256, size, word count, blanks, jurisdiction mentions, PII **counts** (all zero). No template text. |
| `cases_v1.jsonl` | 29 synthetic drafting requests (21 dev / 8 holdout) on those templates: bail/criminal 8, family 5, civil 5, tenancy 5, notices 2, agreements 4. Each has `required`, `support` (permissible authorities), `forbid` (claims that must not appear in the final text), `expect_placeholder`, and per-label `basis` / `review`. |
| `subject_adversarial_v1.jsonl` | 37 sentences for fix 1 (real section of the right Act, cited for its subject or not): 24 valid, 11 invalid, 2 for lawyer review. Used to DEVELOP fix 1 -- its score is optimistic. |
| `results/<label>.jsonl` | One row per case per repeat: synthetic request, model output, guard frame, citation-check record, metrics. No template text, no client data. |
| `results/<label>.manifest.json` | Dataset hash, code-file hashes, what was stubbed. |

## Run

    python scripts/eval_drafter.py inventory               # re-hash the DOCX source (Downloads)
    python scripts/eval_drafter.py run --label X --repeat 2 # real model; ~4 s per call
    python scripts/eval_drafter.py score results/base_r1.jsonl results/after_r1.jsonl --cases
    python scripts/eval_drafter.py subject                 # fix 1 on the real index, no model

Stubbed in `run`: the audit write (`provenance.record_answer`) and case-law
retrieval (it reads the hosted citator store). Settings come from the local
overlay. Stop the backend first: the corpus is an embedded Chroma store.

## Metrics (per row, final visible proposal unless stated)

- `unsupported` -- a `forbid` claim in the final text (`unsup_raw`: in the raw model output).
- `unlisted_authorities` -- a cited provision the case does not list as permissible. **For review**, not automatically wrong; most observed ones were wrong sections (e.g. CPC s.8 for review).
- `wrongly_withheld` -- a withheld sentence citing a permissible authority.
- `jurisdiction_mistakes` -- another province's Act, or no placeholder where provincial law governs.
- `checker_disagreement` -- the guard counted a citation as supported that the citation checker could not verify, or the reverse.
- `missing_required` -- a required part absent. `empty` -- nothing left to insert.

## Labels that still need a lawyer

Official-text checked (pakistancode.gov.pk CrPC 1898 / PPC 1860 PDFs): CrPC ss.154, 420, 426, 437-438 [Omitted], 491, 496-500; PPC ss.406, 420, 506.
Everything else is corpus text or statute knowledge only. Needs a lawyer:

- **B2** pre-arrest bail under CrPC s.498 (rests on case law).
- **B4** "prohibitory clause" = CrPC s.497(1).
- **B7** whether citing s.497 for suspension pending appeal is wrong (forbid label).
- **C1** CPC ss.15-20 as permissible for a jurisdiction paragraph.
- **C2** CPC Order XLVII r.1 with s.114 for review; s.114 is **absent from the corpus**.
- **C3, A1, A2** Specific Relief Act ss.42/54, Registration Act s.17, Contract Act ss.73/74: not in the corpus.
- **C4** which Limitation Act provision/Article governs; whether s.5 is wrongly cited for a suit.
- **F4** Family Courts Act 1964 s.5 as the neutral-draft authority (provincial amendments).
- **T1-T5** whether the TPA lease sections (105-117) are displaced by provincial rent law for eviction -- the basis of fix 2.
- **T3** Sindh Rented Premises Ordinance 1979 s.15 (not in the corpus).
- **N1** CPC s.80 (corpus heading garbled). **N2** PPC s.489-F (heading not extracted; shown absent by the index).
- **A3, A4** which labour / standing-orders law governs termination in Punjab, and in a neutral draft.
- Adversarial **R01** (bail bonds under CrPC s.76) and **R02** (custody petitions under GWA s.7 -- the guard withholds this; common practice may say otherwise).
