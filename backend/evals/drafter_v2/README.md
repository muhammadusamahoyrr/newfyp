# Lawyer Draft Assistant evaluation V2 (2026-10-15)

A **separate benchmark** from V1 (`evals/drafter`, 29 cases on aiattorney templates). Never compare V1 and V2 scores.
**Silver labels by one developer, not reviewed by a lawyer.** Scores are checklist matches on the final visible
proposal; they do not show that any draft is legally correct or court-ready.

## Files

| File | Contents |
|---|---|
| `source_audit.json` | Local audit of the source collection (`Desktop/error`): 116 originals (64 legaldocs.pk DOCX, 50 DOCX + 2 DOC practitioner drafts). Per document: collection, category, template name, sha256, normalised-text hash, format, Urdu flag, **counts** of personal-data shapes, blanks, jurisdiction mentions, risk, duplicates. **No text, names or numbers.** |
| `legal_sources.json` | Official sources behind the labels: URL, retrieval date, version note, and the sections whose heading was read from the official text. CPC, Specific Relief Act and MFLO have **no official source recorded**. |
| `cases_v2.jsonl` | 31 synthetic cases: `free_drafting` 25 (18 dev / 7 holdout), `template_fill` 6 (4 dev / 2 holdout); English 27, Urdu 4; Punjab 12, Sindh 11, federal 4, unknown 3, KP 1. |
| `holdout.lock.json` | sha256 of each holdout case line, locked 2026-10-15 before any model run. |
| `transmit_preview.json` | Exactly what a model run would send (see below). |

## Rules

- **Privacy.** Cases are synthetic; `inspired_by` names a category, never a file. The 4 files flagged `exclude` (filled case numbers; one deed with names/addresses) and the 48 `manual_review` practitioner drafts are used for nothing that leaves this machine. Automated zero counts are not proof of no personal data.
- **Licence.** Third-party documents: no source wording in cases, results, prompts or product templates. `validate --src` checks that no 8-word run of any source document appears in a case (in memory; nothing stored).
- **Labels.** `definitive` only when every section label's source has an official URL, the heading was read from that text, and no review flag. Otherwise `provisional` (reported separately, never as correctness) or `no_authority_labels`. Currently 7 definitive, 16 provisional, 8 without authority labels.
- **Holdout.** Never tune on it. A fix developed from a holdout failure makes that case dev: re-lock and say so.
- **Tracks.** Free drafting and template filling are scored separately and never combined.

## Commands

    python scripts/eval_drafter_v2.py audit             # local; re-hash and re-screen the source folder
    python scripts/eval_drafter_v2.py validate          # integrity, holdout lock, privacy, copied wording
    python scripts/eval_drafter_v2.py transmit-preview
    python scripts/eval_drafter_v2.py run --label X --approved   # only after the user approves the preview
    python scripts/eval_drafter_v2.py score results/X.jsonl

## Baseline

No valid pre-fix baseline exists: HEAD (af960e3, 2026-10-12) has no draft modes, no selection rewrite and no legal
check, so it measures a different product; the state between the safeguards and the four guard fixes was never
committed. A V2 run on the current worktree is a **current-state baseline only**.

## Labels needing a lawyer

All CPC labels (V01-V07, V16, V23: no official CPC source recorded; Order/Rule vs section near-misses); V05 (s.12(2)
vs Order IX r.13); V08 (Limitation Act s.5/s.3, text not checked); V11 (pre-arrest bail under CrPC s.498 rests on
case law); V14 (khula: DMMA s.2 / Family Courts Act s.10(4), MFLO s.7 forbidden); V15 (GWA ss.17/25, text not
checked); V16 (Family Courts Act s.5 and Sindh amendments; s.9 CPC forbidden); V17/V21 (whether TPA lease
sections are displaced; which labour law governs); V19 (TPA s.54, text not checked); V24 (PPC s.489 without "F").

## Holdout status (2026-10-15)

- **Holdout v1** (`cases_v2.jsonl`, split `holdout`, 9 cases) was OPENED on 2026-10-15: its aggregate replay counts
  were printed once before the fresh run (`v2_r2_holdout`), and its proposals were then inspected. It is HISTORICAL
  evidence only -- never tuned against, and never again called a blind holdout.
- **Holdout v3** (`holdout_v3/`, 14 new synthetic requests, locked) is the next final evaluation. Its labels are
  empty on purpose and must be filled by an independent labeller (`holdout_v3/LABELLING.md`) before it is run.
- Scorer: `--scorer v2` (Unicode hyphens/Urdu digits; blank emptied vs fact invented). v1 is kept for reproducibility.

## Dev label changes after outputs

- 2026-10-15 V09 (dev): `forbid` gained an `invented_fact` text label (the accused's mental state, a fact the request
  does not give), after it appeared in `v2_r3_dev` rep 1. Scored as `invented_facts` -- input-fact fidelity, reported
  separately from citation errors. Earlier results re-scored with it change only where that text appears.
