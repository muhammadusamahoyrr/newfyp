# Holdout v3 -- labelling instructions (for an independent labeller)

The 14 requests in `requests.jsonl` have NO labels. They must be labelled by someone who has NOT seen any
model output for them and did not build the guard (ideally a practising Pakistani lawyer), BEFORE the run.

For each request, record in `labels.jsonl` (one line per id):

- `required`: the parts a correct draft must contain.
- `allow`: authorities a correct draft may cite -- Act, section or Order/Rule, and the **official source URL**
  with its retrieval date (pakistancode.gov.pk, punjabcode.punjab.gov.pk, sindhlaws.gov.pk, kpcode.kp.gov.pk,
  balochistancode.gob.pk, molaw.gov.pk). A label without an official URL is `provisional`.
- `forbid`: authorities or claims a correct draft must NOT make, each with a one-line reason.
- `expect`: draft | clarify_or_placeholder | abstain.
- `review`: anything practice-dependent or uncertain -- these are reported, never scored as correctness.

Then lock `labels.jsonl` (sha256) before the evaluation is run. The developer must not edit labels after
outputs exist. Holdout v1 (cases_v2.jsonl split=holdout) was opened on 2026-10-15 and is historical evidence only.
