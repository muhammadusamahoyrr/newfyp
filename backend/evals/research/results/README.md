# Lawyer AI Research eval — results

Set: `../questions_v1.jsonl` (29 items, 33 turns; SILVER labels by one developer, not lawyer-reviewed).
Harness: `scripts/eval_research.py` — the real `ai_research` route, real graph, live providers,
in-memory conversation/turn stores, synthetic case through the real access rule, result cache OFF.

| File | Flag `RESEARCH_ANSWER_SAFEGUARDS` | Status |
|---|---|---|
| `off_r1_2026-10-14` | off | CURRENT (1 run per flag — reduced from 2 at the user's request) |
| `on_r1_2026-10-14` | on | CURRENT |
| `on_r1_R1recheck_2026-10-14` | on | R1 only, re-run of the ON timeout (did not reproduce: 27.5 s, 489-F matched) |

`*_score.json` = automatic scoring (`eval_research.py score`). The automatic `expected_hit` is a
regex over the answer: it credits a WRONG answer that happens to contain the expected words and
an abstention that names the section. Hand judgement below overrides it.

## Automatic (single run per flag — one sample, not a repeated measurement)

| | OFF | ON |
|---|---|---|
| expected authority string present | 21/27 | 19/27 |
| known-wrong authority in answer (`forbid`) | 3 | 0 |
| known-wrong statement marked supported | 2 | 0 |
| Indian-law markers presented as authority | 2 | 0 |
| follow-up turned into a clarification | 3 | 0 |
| claims marked "supported" | 91 / 115 | 58 / 140 |
| errors | 0 | 1 (R1, 503 deadline; likely provider 429 pressure — not reproduced) |

By language: en hit 16→14/22, forbid 3→0; roman_ur follow-up clarification 1→0; ur follow-up
clarification 1→0.

## Hand judgement (what the answers actually say)

ON better:
- E4 / E5 / E6 — OFF named "PPC Section 337" (for 337-A), "CPC Section 1" (for Order XXXIX
  Rule 1), "CPC Section 13" (for Order VII Rule 13), all marked supported. ON names them correctly.
- R2 / R5 — OFF "hits" were wrong: R2 built the cheque limitation on Limitation Act s.24; R5
  applied Punjab Tenancy Act appeal periods to a civil decree and invented a "two-year rule".
  All supported. ON withheld the unverified period with a visible notice. Neither gives the
  right period (the schedule Article was not retrieved).
- J1 — ON cites 489-F (matched); OFF cited "PPC Section 489".
- C1 — OFF imported Indian s.138; ON did not.
- N1 / N2 (statute not in corpus) — ON opens with "text not found … not verified"; OFF N2 cited
  Punjab Land Revenue Act s.53 as a matched source for the Specific Relief Act.
- U2 / RU2 / F1 follow-ups — OFF asked a clarification; ON answered.

Still wrong or weak with ON:
- R3 turn 2 "make it short" → generic "unable to provide a reliable answer" (no clarification
  and no s.138 any more, but not a shortened answer). Turn 1 retrieval poor in both
  (CPC Order XXX Rule 5, QSO 127); 489-F absent in both.
- E1 — engine reported "no offence matches Section 420 PPC"; ON says none (wrong). OFF used s.417
  (also wrong). Cause not established.
- U2 "مختصر کریں" — answered, but barely shorter (1957 → 1933 chars).
- RU2 — period guard withheld 420's "seven years" in an Urdu answer (Urdu over-removal).
- F1 / RU1 — 337-A / 489-F not retrieved in that turn (E4 / R1 did retrieve them): safe refusal,
  but a miss. Retrieval is not deterministic enough.
- E9, E11 — no answer / no period in both.
- N1 / N2 note truncates the Act name ("Section 73 Contract").

---

# Tool-contract batch (2026-10-14, later) — `scripts/eval_research.py score2`

Labels: `../questions_v2.jsonl` = the SAME 29 questions + proposition-level labels (`expect_facts`,
`abstain_expected`) + adversarial A1–A4. **All SILVER (developer); no GOLD (lawyer-reviewed) labels exist.**
score2 reads each claim, the sources it cites and the provisions it names (not keyword presence).
PPC 417 / 420 / 406 punishments checked against the official Pakistan Code PDF (last amended 2017).

| File | Code | Status |
|---|---|---|
| `on_c1`, `on_c2` | contract fix, BEFORE the E11 / 337-A fixes | superseded (found the two bugs below) |
| `focus*_on_contract` | focused 6-item live checks | supporting |
| `on_d1`, `on_d2` | final code | **CURRENT ON** |
| `off_r1` | flag off | **CURRENT OFF baseline** |

Same 29 items (score2):

| | OFF r1 | ON r1 (before batch) | ON d1 | ON d2 |
|---|---|---|---|---|
| exact provision retrieved | 6/14 | 9/14 | 11/14 | 11/14 |
| complete (all expected facts) | 5/8 | 4/8 | 7/8 | 6/8 |
| false "not found" | 0* | 3 | 0 | 0 |
| contradiction (denied provision whose text was in evidence) | 0 | 2 | 0 | 0 |
| items with a false-supported claim | 5 | 1 | 0 | 0 |
| missed answers (abstained, answerable) | 5 | 6 | 4 | 2 |
| turn errors / provider-error spans | 0 / 8 | 1 / 13 | 0 / 8 | 0 / 11 |
| median latency s | 12.3 | 12.8 | 15.2 | 14.6 |

\* OFF has no exact-provision guard, so it cannot say "couldn't find"; it answered 337-A as "PPC Section 337" instead.

Found by `on_c1`/`on_c2` and fixed before `d`: (1) the answer backstop withheld a TRUE E11 answer
("No provision on pre-emption time limits is found in the supplied sections (… s.75; s.24)") — the denial
check is now scoped to the provision being denied; (2) E4 answered "couldn't find the text of Section 337-A"
beside its own chunk — OCR-split lettered headings ("337- Punishment…\nA.", "120- A …", "138-A …") are now
recognised (254 lettered criminal chunks: 0 wrong matches; all headed chunks recognised except one footnote).

Live proof of the tool path: `on_d2` A1 — `find_offence_sections("Section 417 PPC")` → `not_in_table`,
superseded by 417's own retrieved text, correct answer (one year / fine / both).

Remaining misses are not the tool contract: R3/E9/J2 generic "unable to provide a reliable answer"
(answerability gate); F1/RU2 follow-up refused when turn 1 had `case_type=unknown`; C1 does not name 489-F;
A3/U1 Urdu periods withheld (period guard); PPC 406 corpus text "160[seven] 160 years" (OCR artefact).
Two runs is a variability check, not a statistical proof.

---

# Visible-authority batch (2026-10-14, latest) — E11 / RU2 release blockers

Labels: `../questions_v3.jsonl` = v2 (same 33 items) + V1–V6 adversarial (EN/UR/Roman UR). All SILVER.
score2 now scores the FINAL visible answer: whole-Act silence, invalid authority visible (omitted /
absent / mispaired), unverified authority asserted, period notice contradicting a shown period,
governing-provision hit/rank. Sources: CrPC 1898 official Pakistan Code PDF (437/438 [Omitted]; 406 =
appeal from security order; Sch. II: PPC 420 not bailable); Punjab Pre-emption Act s.30 (four months) —
corpus text = statutory text as quoted (both government PDF copies refused automated download).

| File | Status |
|---|---|
| `on_e1`, `on_e2` | **CURRENT ON** (final code except the partial-notice wording, added after; unit-tested) |
| `focus4/5_on_visible` | focused live checks (focus5 = final code minus partial notice) |
| `off_r1` | OFF baseline (v1 items only) |

Same 29 items:

| | OFF r1 | ON d2 (prev batch) | ON e1 | ON e2 |
|---|---|---|---|---|
| whole-Act silence visible | 1 | 2 | 0 | 0 |
| invalid authority visible | 3 | 1 | 0 | 0 |
| unverified authority asserted | 3 | 0 | 0 | 0 |
| items with false-supported claim | 5 | 0 | 0 | 0 |
| exact provision retrieved | 6/14 | 11/14 | 10/14 | 9/14 |
| complete | 5/9 | 6/9 | 7/9 | 8/9 |
| missed answers | 5 | 2 | 4 | 6 |

All 39 items, e1 / e2: governing provision retrieved 4/4 and 4/4 (rank 1); notice contradiction 2 / 1
(partial overlap — fixed afterwards, see below); turn errors 4 / 7; provider-error spans 342 / 330;
median latency 72 s / 50 s. **Provider conditions were degraded**: the Groq keys hit the 200k
tokens-per-day limit during the runs (429 TPD) and Groq structured output returned `tool_use_failed`
(400); the turn errors are 503 deadlines, one Gemini 429 and one length error. Missed answers and
completeness in e1/e2 are confounded by this; the visible-answer violations are not.

E11 — both runs: four months, s.30 matched and retrieved first, no "Act is silent", no contradictory notice.
RU2 — both runs: no 438/437/406 CrPC visible (e2 turn 1 was a 503 timeout). Urdu "seven years" still
withheld by the period guard (Urdu over-removal; 420's punishment is not the limitation issue).

After the runs: when withheld periods are only PARTLY shown elsewhere, the notice now names exactly the
withheld-and-not-shown period(s) (unit-tested + mutation-killed; not yet in a live run).
