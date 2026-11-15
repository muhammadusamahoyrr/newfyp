# Batch 10: authority-capability registry for Intake, Chat and Research (2026-10-17)

**Scope:** code and tests only.
- **Not done:** no live `chroma_data` access, no model or provider call (including the local embedding model), no ingestion, no index rebuild or switch, no deletion, no commit.
- **Not switched:** the live index was **not** switched, and the **live CPC relabel is still BLOCKED** (§7).
- **Status:** passing tests do **not** show legal accuracy. The labels and expected outcomes are engineering judgements, not lawyer-reviewed.

## 1. The registry (`app/ai/authority_registry.py`)

Built from **verified provenance** (each chunk's `source_file`) in the verified snapshot `chroma_data_20261017T024819Z`, plus `app/ai/data/corpus_instruments.json`. Counts are identical in `civil_collection`, `__ident_v1` and `__ident_v2`.

| Key | Source files | Chunks | Held for |
|---|---|---|---|
| `cpc` | `code of civil procedure 1908.pdf` (Punjab Code text, labelled `federal`) | 1,967 | **Punjab** |
| `pre_emption` | `punjab-pre-emption-act-1991.pdf` (50), `punjab-pre-emption-removal-of-doubts-ordinance-1972.pdf` (10) | 60 | **Punjab** |
| `rented_premises` | `punjab-rented-premises-act-2009.pdf` | 61 | **Punjab** |
| `specific_relief` | none | **0** | **nowhere** |

**How chunks and provinces are handled:**
- **Ownership by provenance:** a chunk belongs to an authority by its **source file**; its `province` label is never consulted.
- **Unregistered sources:** a chunk named as a registered statute but from an unregistered source (e.g. a test fixture) is `unverified`, and is nobody's applicable law.
- **Coverage is never inferred** for another province.
- **Unknown or model-inferred province** is never treated as Punjab.

**Correction:** batch 9's test file asserted that "specific performance" was `supported` by a fixture `Specific Relief Act 1877` chunk. The real corpus holds **0** chunks of that Act. The question is now `source_unavailable_for_jurisdiction` everywhere, including Punjab, and the old case is replaced by an explicit correction test.

## 2. Detection (conservative)

| Authority | Recognised forms |
|---|---|
| CPC | the batch-9 detector: explicit citations, "Order … Rule", the Code named, precise procedural phrases (EN, UR, Roman) |
| Pre-emption | "pre-emption" / "pre-emptor" (never "pre-emptive"), "haq-e-shufa", "talb-e-muwathibat/ishhad/khusumat", `حق شفع`, `طلب مواثبت` |
| Rented premises | "Rented Premises", "rent controller/tribunal", eviction or ejectment **of a tenant**, "kirayedar … bedakhli", `کرایہ دار … بے دخل` |
| Specific Relief | "specific performance", "Specific Relief", `تعمیل خاص` |

- **Never a refusal on their own:** "rent", "property", "court", "application", "appeal", "landlord", "pre-emptive strike", "Section 186 PPC". These are negative controls, tested.
- **Mixed questions:** when the question also names other law (any "… Act" outside the registry, or PPC, CrPC, Contract Act, …), or asks a **limitation / time-limit** question (answerable from the Limitation Act, which is held), the held part is assessed separately and the unavailable part is marked.

## 3. Where the check runs

| Surface | Before | After |
|---|---|---|
| **Intake** evidence gate (`decide`, v5) | CPC only (batch 9); pre-emption, eviction and specific performance questions were `supported` on leftover law | **any registry authority**: its chunks are admissible only for the confirmed holder. A question needing only unavailable law gives **`source_unavailable_for_jurisdiction`** with a facts-only analysis and no law shown. Mixed: the held issue is judged on its own chunks, with a caveat per unavailable authority. |
| **Chat / Research** decision node (`supervisor._decision_node`) | no authority check; the answer writer saw whatever law was left | **before generation:** unavailable-only questions get `arbitration_output="refuse"`, `refusal_kind=source_unavailable_for_jurisdiction`, and an honest limitation (asks for the province when unknown; Urdu when the language is Urdu). **The answer writer is never called.** Mixed: the unavailable authority's chunks **and exact-lookup tool text** are removed from the evidence, `authority_limits` is recorded, a generation rider says not to answer that part, and the finalizer appends a plain notice. A deterministic engine answer (court fee etc.) is kept and marked, not refused. |
| **Cache** (`cache_block_reason`, used by both lookup and write) | could serve an entry written before the rule | **no lookup and no write** for such a question |
| **Follow-ups** ("explain in detail") | regenerated | the gate reads `presentation_base_query`, so the earlier question is used; the follow-up stays limited |
| **Final visible answer** (finalizer backstop) | n/a | any answer that reaches the finalizer **without** the gate (a cache hit, any bypass) and needs unavailable law is **withheld whole**: limitation text, citations removed, claims marked removed, `is_grounded=False` |
| **Client Intake UI** | note said "civil procedure" | general wording (EN and UR); `components/client/ModIntake.jsx` only |

The role policies and output formats of Chat and Research are otherwise unchanged.

## 4. Before / after on copies of the verified snapshot (MEASURED, BM25 only)

**Copies used:**
- `chroma_data_20261017T024819Z_WORKCOPY_for_fingerprint` (current labels);
- `SCRATCH_cpc_relabel_20261017T025355Z` (CPC relabelled `punjab`).

**What was measured:**
- **Retrieval** is the app's own BM25 retriever and chunk filter, per province.
- **"Before"** is the batch-9 gate (CPC only); before batch 10, Chat had **no** gate.
- **Dense (embedding) ranking was NOT measured.**
- Raw output: `chroma_snapshots\<copy>.b10_before_after.json`.

| Question (EN / UR / Roman) | Punjab | Sindh / KP / Balochistan / federal | Unknown |
|---|---|---|---|
| Pre-emption (EN, Roman) | supported → supported; chat answered | Intake: supported → **source_unavailable**; Chat: answered → **refuse** | wrong_jurisdiction or supported → **source_unavailable**; Chat → **refuse** (asks for province) |
| Tenant eviction (EN, Urdu), rent controller | supported → supported | **supported → source_unavailable**; Chat → **refuse** (only 1–10 leftover chunks retrieved) | → **source_unavailable** / **refuse** |
| Specific performance | **supported → source_unavailable** (Act not in corpus) | **supported → source_unavailable** | **supported → source_unavailable** |
| CPC temporary injunction | supported (CPC kept) | source_unavailable (batch 9, unchanged); Chat: answered → **refuse** | source_unavailable; Chat → **refuse** |
| Mixed: pre-emption + Limitation Act | supported | Intake **supported** (Limitation part); Chat → **mixed** (9–10 of 10 chunks kept, notice) | supported; Chat → mixed |
| Negative control: "I pay rent… landlord wants to sell the property" | supported | **supported (unchanged)**; Chat answered (no gate) | unchanged |
| Negative control: "appeal in the court against the order" | corpus_not_capable (pre-existing, unchanged) | unchanged; Chat no gate | unchanged |
| Limitation (money lent) | supported | **supported (unchanged)** | unchanged |

**Current and relabelled copies give identical verdicts.** Only the retrieved counts differ (the relabel removes CPC from non-Punjab retrieval).

The limitation-phrase refinement (§2) was made after this run. It changes no row above except that a question asking for a limitation period now goes mixed instead of being refused whole.

## 5. Tests (SYNTHETIC evidence, STUBBED models)

**New file `tests/test_authority_registry_gate.py`.** **Before the fix: 53 failed / 41 passed** (log kept in the scratchpad as `b10_before.log`). The real failures it reproduced:
- **Intake:** `supported` on leftover law for pre-emption and eviction in Sindh, KP, Balochistan and federal, in both label states (16), and for specific performance.
- **Chat (real socket and graph, stubbed generator and judge):** the answer writer was called on unavailable law (24 of 24); a cached confident "Order XXXIX" answer was served; a follow-up regenerated an answer.
- The other failures were the missing new API.

**After the fix: 105 passed, 0 failed.** Covered:
- the registry and provenance;
- Punjab, Sindh, KP, Balochistan, federal, unknown and inferred;
- single and mixed questions;
- English, Urdu script and Roman Urdu;
- explicit references (Section 13 Pre-emption Act, Rented Premises Act 2009, Order XXXIX Rule 1, Section 9 CPC);
- 8 negative controls and unrelated valid law;
- final socket `final` frames;
- the research decision node and finalizer;
- cache hit, cache rule, follow-up, the finalizer backstop, an engine answer, exact-lookup tool text, and limitation issues.

**Mutation tests (7), each caught:**
1. trusting the label;
2. claiming Sindh coverage;
3. broad "rent" detection;
4. unknown treated as Punjab;
5. no chat gate;
6. no final backstop;
7. ignoring the limitation issue.

**Batch-9 file `tests/test_cpc_authority_availability.py`: 61 passed.**
- The specific-performance case was corrected (§1).
- The leftover-law finalizer case now expects the answer **withheld**, not annotated.
- Three mutants were retargeted at the registry, which the gate now reads.

**Backend regression** (one file at a time, temporary-Chroma guard, `-m "not integration and not llm and not network"`, rerun 04:37–05:03 UTC after the last code change):
- **Scope:** 66 files (batch 9's 48, plus every test touching the cache rule, generation, supervisor, decision node, finalizer, gate or registry).
- **Results:** **1,898 passed, 0 failed**, 4 skipped, 1 xfailed, 123 deselected (integration, below).
- **Skips:** all 4 are the corpus tier, which needs the live store and is refused by the isolation guard.
- **xfailed:** the known section-parser limitation.
- **Isolation:** 0 accesses to the live path, apart from the guard test's 15 deliberate probes.

**MongoDB integration** (local replica set `localhost:27018`, throwaway `_test` databases, 05:03–05:14 UTC):
- **Scope:** 24 files.
- **Results:** **435 passed, 0 failed, 0 skipped** (12 deselected as llm/network).

**Frontend** (run directly): `intake_grounding_notes` 6, `mod_intake_dom` 67, `intake_export_safety` 13, `lawyer_draft_assist` 46. **132 passed, 0 failed.**

## 6. Remaining bypasses (not covered)

1. **Paraphrase:** an issue asked about in other words ("throw the person living in my house on rent out", "my neighbour sold before offering it to me") is not recognised.
   - **Current labels:** fails open to the earlier output gates for the CPC only.
   - **Pre-emption / rent:** the answer is built from leftover law **without** a notice.
   - Needs a held-out, lawyer-reviewed question set to measure recall.
2. **Generic procedure:** "appeal", "court", "application" are deliberately not detected. On a **relabelled** index a non-Punjab appeal question retrieves only 2 leftover chunks and Chat answers from them (measured row, §4).
3. **Context-carrying follow-ups:** only "make it short / explain in detail" follow-ups re-read the earlier question. "And what about the appeal?" after a pre-emption question is judged on its own words.
4. **Other authorities:** only the four in the registry. Other provincial laws (e.g. other Punjab-only Acts) are not registered, and no coverage is claimed for them.
5. **Dense ranking unmeasured; exact lookups not province-filtered** (they are filtered out of a mixed question's evidence, and a whole-unavailable question never reaches generation).
6. **Intake triage / summary text** is unchanged; only the evidence gate and the facts-only path changed.

## 7. Live relabel: still BLOCKED

**Met:** conditions 1 (general check for registered provincial authorities) and 2 (Chat / Research parity before generation, tested at final frames) of the batch-9 list now hold for the **registered** authorities.

**Still open:**
- broader detection measured on a lawyer-reviewed held-out set;
- dense-retrieval measurement (needs approval to run the local embedding model);
- province-aware exact lookups or an explicit decision to rely on the gates;
- a fresh snapshot, written rollback and updated `index_health` pins;
- ideally, a verified non-Punjab CPC text.

Each is a separate decision.
