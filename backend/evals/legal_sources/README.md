# Legal sources: coverage audit, registry design and isolated pilot (2026-10-16)

> **Batch 2 (2026-10-16)** corrects this file — ident_v2 wording, KP Code status, CPC amendment — and adds the v3 parser, URL-status taxonomy and source checks: see [BATCH2_PARSER_STATUS_INDEX.md](BATCH2_PARSER_STATUS_INDEX.md). Its §0 records that two test files opened the live Chroma store during regression testing.

Status: **audit + design + parsing pilot only.** Nothing was ingested. No live
store, orphan folder, backup, active index or feature flag was touched. No
model or provider was called. Every legal label here is **provisional
(developer)**; no Pakistani lawyer has reviewed any of it. Nothing here makes
the corpus "current", "complete" or "court-ready".

Files:
- `backend/data/legal_sources/candidate_registry_v0.json` — 31 feeds + 19 candidate documents, families A–G, each with URL status, licence, commencement evidence and blockers
- `backend/app/ai/legal_sources/{identity,registry}.py` — pure parsing and registry rules (no Chroma/DB/network)
- `backend/scripts/pilot_legal_sources.py` — isolated parsing pilot (scratch output only; refuses store paths)
- `evals/legal_sources/pilot_questions_v0.jsonl` + `HOLDOUT.lock.json` — 24 questions (16 dev / 8 locked holdout)

## 1. How the audit was done (and its limits)

- Code, scripts, manifests and plain-text exports only. **No Chroma client, no SQLite
  open, no listing inside `backend/chroma_data`, its backups or the two orphan
  folders.** The store's size (897 MB) was read from directory totals only.
- "Indexed" therefore means: present in `corpus_instruments.json` (2026-10-12),
  in `data/general_bundle.json` (plain-text export, 9,042 statute chunks, dated
  2026-08-29) and in the ingestion code. The live store reportedly holds ~10.7k
  statute chunks (later than the export), so **absence is confirmed from those
  three sources, not from the live store**. Confirming against the store needs an
  isolated byte copy — see §8.
- Official URLs were fetched automatically (no login, no forms). 403/JS-only pages
  are recorded as blocked/unverified, never filled from secondary sources.

## 2. Current state in one table

| Collection | Chunks (2026-10-14 manifests) | Read by | Provenance per chunk |
|---|---|---|---|
| criminal / civil / family / constitutional (base) | 3,306 / 4,648 / 989 / 1,736 | Intake, client chat, research (flag off) | statute, section, province, law_type, chunk hash. **No source URL, document hash, retrieval date, commencement, amended-up-to, licence** |
| `criminal__sec_v2`, `civil__ident_v2` (code-referenced by the drafter; research only with `RESEARCH_ANSWER_SAFEGUARDS` on; switch uncommitted; health NOT verified since the 2026-10-15 build), `civil__ident_v1` (kept; NOT a fallback: a missing ident_v2 falls back to base) — see BATCH2 §1 | 3,305 / 4,648 / 4,648 | drafter, research (flag on), exact-provision | + provision kind/label; ident_basis "official_pakistancode_2026-10-15" |
| judgments_collection | 23,978 | chat, research, drafter case law | court, province, authority string, year. **No case no., citation, bench, reported/overruled** |
| constitutional (incl. 305 LEGAL-UQA extracts + 619 synthetic Q&A, excluded at retrieval) | — | — | Constitution text is **"as modified up to 28 Feb 2012"** |

Manifest: 44 instruments (not 43 — the West Pakistan Family Courts Act appears
twice; Contract Act is in the REGISTRY but not indexed). A runtime reader exists:
the Intake evidence gate uses it to flag named-but-missing Acts.

## 3. Coverage matrix (families A–G)

Legend: **IDX** indexed · **MISS** not indexed · **STALE** indexed but out of date · **?** uncertain.

| Fam | Source | Type | Jurisdiction | Corpus | URL status 2026-10-16 | Blocker summary |
|---|---|---|---|---|---|---|
| A | Pakistan Code portal | feed | federal | partial (PPC, CrPC, CPC…) | ok | "information only, under review"; PPC "last amended 2017-02-16"; CPC/CrPC/PPC "(Under Review)" |
| A | Constitution | constitution | federal | **STALE** (2012 text) | current text not located | no 18th–27th-amendment-era consolidation; FCCP absent |
| A | NA enacted Acts | feed | federal | n/a | ok | lists Act II of 2025 (PECA amendment), latest Act XLVII of 2026 |
| A | Punjab Laws | feed | punjab | 13 Punjab Acts | ok | `laws/2706.html` 404 ×3 same day = not_found_unconfirmed (user saw a timeout); reuse terms "all rights reserved" |
| A | Sindh Laws | feed | sindh | **MISS** (none) | ok | — |
| A | KP Code | feed | kp | **MISS** | ok — 200 on 2026-10-16 13:35Z (batch-1 '404' was one failed fetch; withdrawn) | contents and licence not read |
| A | Balochistan Code | feed | balochistan | **MISS** | ok | — |
| A | Court-Fees Act 1870 | statute | federal (+provincial rates) | **MISS** (only a hard-coded fee estimator) | **ok, text verified, hashed** | amended-up-to unknown; provincial rates separate |
| A | CPC (Punjab Amendment) | amendment | punjab | **MISS**; indexed CPC is the *Punjab Code* text labelled federal | bill record ok; Act text page 404 (unconfirmed) | Act XIV of 2018, Punjab Gazette (Extra.) 20 Mar 2018 pp. 6695-6698 — per the Punjab Code's own footnotes; Gazette not read |
| A | PECA 2016 (+ Act II of 2025) | statute | federal | **MISS** (a doc claims it is indexed — stale) | **ok, text verified incl. 2025, hashed** | commencement unread; petitions reported |
| A | Punjab Labour Code 2026 (Act IX of 2026) | statute | punjab | **MISS** | official text not located | **commencement not established** |
| B | FCCP judgments / notifications | judgment / rules | federal | **MISS** (no FCCP identity in code) | ok | upload ≠ decision date; reuse terms unstated |
| B | FCCP (Practice & Procedure) Rules 2026 | court rules | federal | **MISS** | **ok — S.R.O. 1580(I)/2026, notified 14 Sep 2026, Gazette 16 Sep 2026 (read from PDF)** | commencement clause unread |
| B | Federal Shariat Court judgments / rules | judgment / rules | federal | **MISS**; code maps FSC to "binding_national" like the SC | ok | rules undated; authority mapping questionable |
| B | IHC Practice & Procedure Rules 2025 | court rules | ICT | **MISS** | notice ok; **text not found** | S.R.O. 169(I)/2025, w.e.f. 04-02-2025 per notice |
| B | LHC Rules & Orders I–V | court rules | punjab | **MISS** | ok | **"not to be downloaded without prior agreement"** |
| B | IHC forms | forms | ICT | **MISS** | JS-only | forms "may be drafts" |
| C | Sindh labour laws (25) & rules (26) | statute/rules | sindh | **MISS** | ok | rules undated; placeholder links |
| C | NIRC | tribunal | federal/ICT | **MISS** | ok | — |
| C | FOSPAH | ombudsman | federal | **MISS** | ok | two Act titles on site |
| C | NEPRA | regulator | federal | **MISS** | ok | consultation notices mixed in |
| C | Competition Commission | regulator decisions | federal | **MISS** | ok | PDFs on plain http |
| C | Federal Tax Ombudsman | ombudsman | federal | **MISS** | ok | complaint no. only, no dates |
| D | SBP circulars / consumer / Sunwai | circular / service | federal | **MISS** | **403** | — |
| D | SECP | regulator | federal | **MISS** | **403** | — |
| D | FBR SROs | SRO | federal | **MISS** | ok (rows JS-loaded) | terms unread |
| E | NCCIA guidance/forms | service | federal | **MISS** | **403** | — |
| E | Banking Mohtasib | service + s.82D BCO | federal | **MISS** | form ok; procedure/FAQ **404** | **30 vs 45 days unresolved** |
| E | NADRA | service | federal | **MISS** | **403** | no CNIC collection |
| E | PLRA / LAJA | service | punjab / federal | **MISS** | JS-only | — |
| E | Punjab e-stamping | service | punjab | **MISS** | **Dastak** (`dastak.punjab.gov.pk`) per BOR; old URLs dead | steps JS-loaded |
| F | Punjab / Islamabad Bar Council verification | marketplace | — | not RAG | ok | inputs/terms not visible — **never scrape, never auto-verify** |
| G | Zenodo 21672295 (SC+IHC judgment–headnote, 429 pairs) | eval dataset | — | not RAG | ok — **CC-BY-4.0** | headnote origin unnamed; eval-only |

## 4. Ranked backlog (specific instruments, not bulk)

1. **Court-Fees Act 1870** (federal) — verified + hashed; needs amended-up-to date and the Punjab/ICT rate instruments as *separate* records.
2. **PECA 2016 consolidated + Act II of 2025** — verified + hashed; cyber intake.
3. **Constitution — current consolidated text** (replace the 2012 text; FCCP articles).
4. **FCCP (Practice & Procedure) Rules 2026** — S.R.O. 1580(I)/2026 verified.
5. **CPC (Punjab Amendment) — enacted Act** — find the Act number and text; keep apart from federal CPC; **re-source the indexed CPC** (it is the Punjab Code text labelled federal).
6. **IHC Practice & Procedure Rules 2025** — locate the S.R.O. text.
7. **Banking Companies Ordinance s.82D** + the amending instrument (30/45 days).
8. **Contract Act 1872, Specific Relief Act 1877, Registration Act 1908, Stamp Act 1899** — absent but repeatedly needed (drafter, intake, analyzer).
9. **Punjab Labour Code 2026** — only after its commencement notification is found.
10. **Industrial Relations Act 2012** (+ provincial IR Acts as separate records).
11. **Protection against Harassment … Act 2010** (+ 2022 amendment; provincial variants).
12. **Sindh labour Acts/rules** — per instrument, not as a set.
13. **FCCP judgments** (feed) — after an authority rule is agreed with a lawyer.
14. **FSC procedure rules + judgments** — with FSC as its own forum.
15. **NIRC judgments** (tribunal lane).
16. **SBP circulars** (once accessible) — department-keyed numbering.
17. **FBR SROs** — SRO-keyed, with amendment links.
18. **NEPRA SROs/decisions** — excluding consultation notices.
19. **CCP orders**, 20. **FOSPAH / FTO decisions** (non-precedential lane).
21–25. Service data: **NCCIA**, **Banking Mohtasib**, **Dastak e-stamping**, **LAJA**, **NADRA succession** — 90-day recheck.
26. LHC Rules & Orders — **only with written LHC permission.**
— Marketplace verification (F) and the Zenodo dataset (G) are **outside** the corpus by design.

## 5. Registry design

Record fields (implemented in `registry.SourceRecord`): `source_id`, `title`,
`issuer`, `source_type`, `country` (always PK), `jurisdiction`, `forum`,
`official_url`, `url_status`, `document_hash` (sha256 of the exact bytes),
`publication_date`, `commencement_date`, `commencement_evidence`,
`effective_to`, `amendment_of`, `superseded_by`, `instrument_number`,
`verification_date`, `licence_status`/`licence_note`, `ocr_quality`, `blockers`,
`recheck_after_days`. Per-chunk metadata (pilot output) adds `provision_kind`,
`provision_label`, `region`, `source_page`, `amending_instruments`,
`split_version`.

**Lanes (one per source type, never merged):** `law` (constitution, statutes,
subordinate rules) · `version_history` (amendment instruments, commencement
notifications) · `court_rules` · `judgments` · `decisions` (tribunal/ombudsman/
regulator — non-precedential where applicable) · `regulatory` (circulars, SROs) ·
`forms` · `service`. **No lane:** marketplace verification, evaluation datasets.

**Hierarchy rules:** legislation and current official rules are not interchangeable
with judgments; judgments are not interchangeable with forms or service
guidance; an ombudsman decision is never ranked like superior-court precedent; a
form is never evidence that a draft is complete. FCCP, FSC, SC and each High
Court are distinct forums; the binding scope of FCCP vs SC decisions after the
27th Amendment is **a lawyer's call**, not encoded.

**Temporal rule:** `temporal_status()` returns `in_force_per_registry` only with
verified commencement evidence, a date reached, nothing ended, and a fresh
check. An enacted-but-not-notified instrument is `commencement_unverified`.
Service data is `fresh`/`stale`, never "in force". Queries whose province, forum
or effective date is unresolved must clarify or state the uncertainty.

**Provinces:** a provincial change to a federal text is its own
`amendment_instrument` that names its target; it never overwrites the federal
record (enforced by `provincial_variant_conflicts`). India's Punjab is a live
confusion risk (seen twice in searches) — `country` is mandatory.

## 6. Ingestion boundaries

May be piloted (isolated, scratch only): records with `url_status=ok`, a document
hash, an ingestible licence status and no blocking legal-status question. Today
that is **only the Court-Fees Act and PECA texts**, and both still carry
blockers (§7). Everything else waits on §7. Live ingestion, collection switches
and flag changes need separate approval.

## 7. Questions that block ingestion

1. **Pakistan Code reuse and currency.** "Information only, under review; the Gazette governs." Is consolidated text acceptable as the retrieval text if every chunk says so and links the Gazette route?
2. **Court-Fees Act currency and provincial rates.** Amended-up-to date of the consolidation; which Punjab/ICT instruments set current rates.
3. **PECA:** original commencement; outcome of petitions against the 2025 amendment.
4. **Punjab Labour Code 2026:** commencement notification number and date.
5. **Banking Mohtasib s.82D:** the amending instrument, its gazette date and whether the bank-response period is 30 days.
6. **CPC (Punjab Amendment):** enacted Act number, assent and gazette dates; status of the 2020 Ordinance.
7. **IHC Rules 2025:** an official text.
8. **LHC Rules & Orders:** written permission to download/index.
9. **FCCP / FSC authority:** how FCCP decisions rank against SC decisions after the 27th Amendment; FSC's precedential scope (the code currently maps FSC to "binding_national").
10. **Reuse terms** for NA, Punjab/Sindh/Balochistan portals, FCCP, FSC, NEPRA, CCP, FBR ("all rights reserved" with no reuse statement).
11. **Blocked sites** (SBP, SECP, NCCIA, NADRA: 403) — manual browser verification.
12. **Zenodo headnotes:** which reporter wrote them (publisher copyright), before any use beyond research evaluation.

## 8. Pilot — what was actually run

Run (2026-10-16): `scripts/pilot_legal_sources.py` on the two verified official
PDFs, output to a scratch directory outside the repo. Parsing only — **no
embeddings, no Chroma collection, no retrieval, no model.**

| | Court-Fees Act 1870 | PECA 2016 (+2025) |
|---|---|---|
| sha256 | a5cdc51c…8d596 | b096696f…d19f8 |
| sections / schedules | 44 / 2 | 72 / 0 |
| amending instruments in footnotes | Act VI of 1905, Act XXI of 1960, Ord. LII of 1962, Act XXVII of 1981 | Act XXXVII of 2023, Act II of 2025 |
| **inserted provisions filed under the preceding section** | 1-A (in 1), 19-H (in 19-G), 35-A (in 35) | **22-A, 24-A, 26-A, 30-A, 43-A, 45-A, 50-A, 51-A** |
| omitted provisions recorded as live sections | ss.2 (×2), 16, 24, 31 (`N. [* * *]`) | — |
| other | — | Authority ss.2-E…2-K, 2-S, 2-T, 2-W not split |

**Finding (negative, important):** the shared statute splitter
(`section_repair.split_provisions`, used by ingestion and sec_v2) misses
provisions printed behind a footnote marker (`1[26A, …`) and does not recognise
asterisk omissions. Ingesting these Acts as-is would file **PECA s.26A (false
information) under s.26 (Spoofing)** and present repealed sections as live. The
splitter was **not** changed — that affects existing indexes and is a separate
decision. The pilot only reports it.

Not run: embedding, a scratch collection, before/after retrieval, any model.

## 9. Evaluation plan (not yet measured)

24 questions (EN 14, Urdu 4, Roman Urdu 6): exact provision, wrong province,
out of date, wrong forum, amendment, omitted provision, lettered/inserted
provision, abstention. Holdout (8) locked by hash before any tuning. All labels
`provisional_developer`.

Metrics (per question): correct provision · correct jurisdiction · effective
status stated · correct source type/lane · citation supported by retrieved text ·
false authority (a form/service page/judgment cited as law, or the federal rate
as provincial) · correct abstention/clarification · latency. Report every
negative.

Baseline vs pilot needs: (a) the live index measured — only on an **isolated
byte copy** of `backend/chroma_data` (~897 MB in a scratch directory, verified by
hash, deleted after the run); (b) a scratch collection embedding the pilot
chunks with the production embedding model, CPU only. **Neither was done; both
need your approval.** No claim of improvement is made, and none can be until a
Pakistani lawyer validates the labels.
