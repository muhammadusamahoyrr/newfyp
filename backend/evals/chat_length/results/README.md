# Chat-length evaluation artifacts

Dataset: `../questions_v1.jsonl` — 30 silver items, 37 turns
(sha256 `91376b718754f46ca2b741b84cb3ae7ecfd2227ea877eea237b1ebcb1dda2af8`).
Labels are silver: "complete" is a word-presence check, and it has known false passes
(see `false_passes` and `complete_strict` in each `*_assessment.json`).

| file | method | status |
|---|---|---|
| `baseline.jsonl` | thread (fresh graph thread per turn), legacy prompts | historical: old behaviour, run 1 |
| `legacy_rerun.jsonl` | thread, legacy prompts (policy code present, client surface not set) | historical: old behaviour, run 2 (noise reference) |
| `after_full.jsonl` | thread, policy on | historical: before the follow-up fixes |
| `after2.jsonl` | thread, policy on | historical: before the classifier/triage follow-up fixes |
| `after6_followups.jsonl` | thread, policy on, c21–c27 only | historical: partial |
| `final.jsonl` | **MIXED**: `after2` rows + `after6_followups` rows | historical only. Not a single run. Do not cite it as a final full run |
| `fresh_2026-10-14.jsonl` (+ `.manifest.json`) | socket-v1 (real `chat_endpoint`) | **superseded**: code fingerprint `927ab3ae…`, before the schedule-article period rule; its c23.1 still shows an unsupported cheque deadline |
| `final_2026-10-14.jsonl` (+ `.manifest.json`) | socket-v1 | **superseded** (`ce16cb49…`): before the c19 / c01 / period-guard release-blocker batch |
| `release_on/off_2026-10-14.jsonl` | socket-v1 | **superseded**: harness lacked the server warmup (c01 timed out); "489‑F" non-breaking-hyphen citation bug |
| `final_on/off_2026-10-14.jsonl` | socket-v1 | **superseded**: period guard over-removed true periods (half-terms rule, hyphen, Act-name stemming, split chunks) |
| `final2_on/off_2026-10-14.jsonl` | socket-v1 | **superseded** (`18ab735f…`): "twenty-five years" read as five |
| `final3_on/off_2026-10-14.jsonl` | socket-v1 | **superseded** (`fef6271b…`): cheque offence named "Section 489" (base-index label copied) |
| `final4_on_2026-10-14.jsonl` / `final4_off_2026-10-14.jsonl` (+ manifests, assessments) | socket-v1, flag on / off | **CURRENT**: one complete 37-turn run each, same code (`28ae7c03…`), same dataset hash. Removed period sentences are recorded per turn (`periods_removed`) and were judged by hand |
| `adversarial_v1_score.json` | `scripts/eval_adversarial.py` on `../adversarial_v1.jsonl` | 33 hand-labelled cases from real corpus text (`scripts/build_adversarial_set.py`) |

NOTE (2026-10-14): Cerebras was added to the shared LLM failover chain AFTER the final4
runs. It is used only when every Groq key fails, so final4 does not measure it.

The `thread` method starts a new graph thread for each turn. The real socket uses one thread
per session, so its follow-up turns behave differently, and the two methods are not identical
for multi-turn items (c21–c27). Single-turn items are comparable.

Regenerate an assessment with:
`python scripts/eval_chat_length.py assess --runs evals/chat_length/results/<run>.jsonl --out <file>`
