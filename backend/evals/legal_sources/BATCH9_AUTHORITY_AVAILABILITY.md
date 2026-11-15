# Batch 9: authority availability: no "supported" on leftover law (2026-10-17)

**Scope:** release-blocker fix, code and tests only.
- **Not done:** no live `chroma_data` access, no model call (including the local embedding model), no ingestion, no index rebuild or switch, no snapshot copy deleted, no commit.
- **Not switched:** the live index was **not** switched.
- **Status:** a passing gate does **not** prove an answer legally correct.

## 1. Trace (before)

**How a question reaches "supported":**
1. Intake gets the province from the client's step-1 choice or the stored case.
2. Retrieval filters on `province ∈ {P, federal}` (none when the province is unknown).
3. The **evidence gate** (`intake_evidence_gate_node.decide`) drops statute chunks of another province **by their `province` label**, then says `supported` **whenever any admissible chunk remains**.

**What the gate never asked:**
- It never asked whether the law the question **needs** is among those chunks.
- It trusted the `province` label: the Punjab CPC is labelled `federal` today and `punjab` after the scratch relabel.

**Reproduced before the fix:** `tests/test_cpc_authority_availability.py`, **53 failed / 8 passed** before the fix.
- **Relabelled index, Sindh:** a civil-procedure question over leftover Limitation Act / Transfer of Property Act chunks returned `'supported'`.
- **Current index, Sindh:** the same question over Punjab CPC chunks also returned `'supported'`.
- The other failures were the absent new API.

## 2. The fix

**Provenance, not labels** (`source_currency.py`):
- `CPC_SOURCES = {"code of civil procedure 1908.pdf": "punjab"}`, the Punjab Code consolidation, sha256 `528384…`, verified snapshot 2026-10-17.
- `cpc_chunk_jurisdiction(chunk)` returns that jurisdiction, `"unverified"` for an unregistered CPC source, or None for a non-CPC chunk. **The chunk's `province` field is not consulted**, so the check behaves the same on current and relabelled metadata.

**Need** (`cpc_requirement(text)`): the question requires the CPC when it has:
- an **explicit** CPC citation or names the Code: Section … CPC, Order … Rule, "O VII R 11", "Rules 1 and 2", `ضابطہ دیوانی کی دفعہ`, "CPC ki dafa"; or
- a **precise civil-procedure phrase**: temporary injunction, ex parte decree, setting aside a decree, execution of a decree, judgment-debtor, attachment before judgment, rejection or return of plaint, written statement, res judicata, pecuniary jurisdiction, "where the defendant resides", amendment of pleadings, impleadment, civil revision. Urdu forms: `حکم امتناعی`, `یک طرفہ ڈگری`, `اجرائے ڈگری`, `جواب دعویٰ`. Roman Urdu forms: hukm imtinai, yaktarfa decree, decree ka ijra, jawab dawa.

**Generic words never count:** "court", "application", "suit", "decree", "order" or "injunction" alone, "Supreme Court Rules", CrPC, PPC.

The detector also records **other law the question names**, so a mixed question keeps its non-CPC part.

**Availability** (`cpc_text_available`): confirmed Punjab → held. Sindh, KP, Balochistan, federal → **not held**. Unknown or model-inferred → **not held**; Punjab is never assumed.

**The intake evidence gate (v4), before any judge:**

| Case | Behaviour |
|---|---|
| Any CPC chunk | admissible **only** if its provenance jurisdiction is the matter's own; counted as `cpc_not_applicable` otherwise |
| CPC-only question, CPC not held | **`source_unavailable_for_jurisdiction`**, with a reason (and "add the province" when unknown). The gate node then forwards no law: a **facts-only** analysis, no law shown, no CPC-based actions. |
| Mixed question, CPC not held | the non-CPC part is judged normally on its own chunks (Limitation Act → `supported`), with the caveat "CPC not held for this province: the CPC part of the question is not answered"; a requested CPC section is not demanded among the passages |
| Query-side capability (instrument not in corpus, pure unsupported issue) | still takes precedence, as before |

**Chat / research final answer** (`finalizer_node` → `apply_cpc_jurisdiction(question=…)`): when the **question** needs the CPC but the answer cites none (the relabelled-index case, where the Punjab CPC is no longer retrieved), a notice is still appended. "This question turns on civil procedure, and the only CPC text held here is the Punjab version, which is not verified for Sindh. The answer above does not rely on the CPC…" (with an "ask your province" variant, and Urdu).

**Exact lookups** (Chat, Research, Draft Assistant) were audited:
- Lookups are still **not province-filtered**: they find the Punjab text under either label.
- **Every presentation gate keys on the statute (`is_cpc`), never on the chunk's `province`.** Batch-5/6 behaviour (claims "Not assessed", CPC currency "unknown", notice, drafter clause removal) is therefore identical on current and relabelled metadata. Tested for Sections 9, 20, 151 and Order VII Rule 11, with the **section identity kept** in claims and citations.

**Client UI** (`ModIntake.jsx`): `GROUNDING_NOTE` / `GROUNDING_NOTE_UR` gain `source_unavailable_for_jurisdiction`: "Your question turns on civil procedure, and our law library holds the Code of Civil Procedure only as it applies in Punjab, so no procedural law is shown for your case. If your province is not recorded, add it. A lawyer in your province should advise on the procedure." (Urdu too.)

## 3. Gate before / after on copies of the verified snapshot (BM25 only)

These are measured gate outcomes on BM25-retrieved chunks. **Dense (embedding) ranking was not measured.** Raw output: `chroma_snapshots\<store>.gate_before_after.json`.

**Copies used:**
- **Current labels:** the fingerprint work copy, `federal`.
- **Relabelled:** `SCRATCH_cpc_relabel_…`, `punjab`.

| Questions | Punjab | Sindh / KP / Balochistan / federal | Unknown |
|---|---|---|---|
| 5 CPC procedural | supported → **supported** (CPC kept) | supported → **`source_unavailable_for_jurisdiction`** on **both** copies. Current: 7–10 Punjab CPC chunks are no longer support. Relabelled: 2–10 leftover non-CPC chunks are no longer support. | current supported → **source_unavailable**; relabelled `wrong_jurisdiction` / supported → **source_unavailable** |
| 2 Limitation | supported (unchanged) | supported (unchanged); stray CPC chunks are no longer admissible on the current copy | supported |
| Mixed (injunction + Limitation Act) | supported, CPC kept | **supported on the Limitation Act**; CPC 3 → 0 admissible | supported; CPC 3 → 0 |
| Pre-emption, eviction (Punjab Acts) | supported | **unchanged: supported on leftover chunks**, a remaining gap (§5) | wrong_jurisdiction (unchanged) |

## 4. Tests

**New `tests/test_cpc_authority_availability.py`: before the fix 53 failed / 8 passed; after the fix 61 passed.**
- **Failure reproduced:**
  - **Relabelled index**, for Sindh, KP, Balochistan and federal: leftover non-CPC law is no longer `supported` (now `source_unavailable_for_jurisdiction`).
  - **Current index**, for the same four provinces: Punjab CPC chunks labelled `federal` are no longer support, and no CPC chunk stays admissible.
- **Punjab and unknown:**
  - Confirmed Punjab keeps its CPC on both metadata states.
  - An **unknown** province (both states) gives `source_unavailable` with "add the province".
  - **Inferred Punjab** is not confirmed.
- **Not blocked:**
  - Limitation, specific performance and PPC s.186 questions;
  - "application in the court", "family court … decree", "appeal in the High Court";
  - a **mixed** question, where the non-CPC part stays `supported` and the CPC is dropped with a caveat (both metadata states);
  - facts-only: the gate node forwards no law on `source_unavailable`.
- **Requirement forms** (13): Section 9 CPC, Order VII Rule 11, O VII R 11, Order XXXIX Rules 1 and 2, rejection of plaint, ex parte decree, execution of decree, written statement, Urdu `ضابطہ دیوانی کی دفعہ 20` and `حکم امتناعی`, Roman Urdu "CPC ki dafa 20", "hukm imtinai", "yakterfa decree".
- **False positives rejected** (8): "court" + "application", "decree", "suit", Section 186 PPC, a 497 CrPC bail application, Supreme Court Rules, "an order of the court", "injunction of my doctor".
- **Provenance:** decided by the source file, not the label: current and relabelled → punjab; an unregistered CPC source → unverified; non-CPC → None.
- **Chat / research final answer** (real `finalizer_node`): a CPC question answered only from Limitation law → notice naming Sindh; Punjab → no notice.
- **Exact identity:** Sections 9 / 20 / 151 / Order VII Rule 11, on current and relabelled metadata, give "Not assessed" for Sindh and section identity kept in claims and citations.
- **Mutation tests (5), each caught:**
  - trusting the `province` label;
  - no authority check;
  - "court" treated as procedural;
  - mixed questions blocked;
  - unknown assumed to be Punjab.

**Backend regression** (one file at a time, temporary-Chroma guard, `-m "not integration and not llm and not network"`, 03:14–03:33 UTC):
- **Scope:** 48 files, covering every test touching the evidence gate, `source_currency`, the finalizer, the intake graph, `_run_intake_ai` or the CPC gates.
- **Results:** **1,363 passed, 0 failed**, 1 xfailed (the known parser limitation), 123 deselected (integration, below).
- **Isolation:** 0 accesses to the live path, apart from the guard test's 15 deliberate probes.

**MongoDB integration** (local replica set, throwaway `_test` databases, 03:33–03:44 UTC):
- **Scope:** 23 files (intake, chat, research and finalizer integration).
- **Results:** **432 passed, 0 failed, 0 skipped.**

**Frontend** (run directly):
- **Results:** `mod_intake_dom` 67, `intake_grounding_notes` 6 (+1: the new status has EN and UR notes, read from the gate source), `intake_export_safety` 13, `lawyer_draft_assist` 46. **132 passed, 0 failed.**

**Not run:**
- **Live corpus:** nothing on the live corpus.
- **Embedding model and other model/provider calls:** no local embedding model, so dense ranking is unmeasured, and no other model or provider call.
- **Corpus-tier tests:** stay skipped by the isolation guard.

## 5. Remaining bypasses

1. **Other provincial laws (not the CPC):** for a Sindh, KP, Balochistan or federal question about pre-emption or rented-premises eviction, only Punjab Acts are held. The gate still says `supported` on whatever leftover chunks remain, the same class of failure as the CPC. The batch-9 check is CPC-specific; a general "required provincial authority" check is needed.
2. **Chat and Research retrieval** don't run the intake gate. After a relabel, a Sindh procedural chat answer is built from leftover law. It now carries the notice ("does not rely on the CPC… check with a lawyer"), but its claims can still be judged "supported" on that unrelated law.
3. **Requirement detection is phrase-based.** A CPC procedure asked about in other words ("stop him selling the house until the case ends", without the word "injunction") is not recognised. That fails open to the batch-5/6 output gates on the current index, but on a **relabelled** index it is the original failure.
4. **Exact lookups are not province-filtered.** Presentation is gated, but the Punjab text still enters the model's evidence for a non-Punjab question.
5. **Dense ranking is unmeasured**, and the **Specific Relief Act is not in the corpus**.

## 6. Conditions before a live relabel could be considered (each separately approved)

1. A **general authority-availability check** for provincial laws (§5.1), with the same before/after evidence on snapshot copies.
2. **Chat / research parity:** an authority check before generation, or an answer-level refusal for non-Punjab procedural questions, tested at the final visible answer.
3. **Broader requirement detection**, measured on a held-out set of real (synthetic, lawyer-reviewed) civil-procedure questions for both recall and false positives.
4. **Dense-retrieval measurement** with the local embedding model (separate approval to run it), BM25 + dense, on snapshot copies.
5. **Province-aware exact lookups**, or an explicit decision to keep relying on the presentation gates.
6. A **fresh snapshot** right before the switch, a written rollback (keep `__ident_v2` and the base collections as they are; relabel a *new* collection version and switch one constant), and `index_health` pins updated for the new version.
7. **Better still:** add a verified federal or other-province CPC text (licence, status and commencement first), so non-Punjab procedural questions have lawful text instead of an abstention.
