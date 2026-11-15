"""Build evals/chat_length/adversarial_v1.jsonl from REAL corpus chunks.

Labels are assigned here BY HAND, from reading the quoted statute text, before
and independently of the checker -- they are NOT produced by
period_support / exact_provision / imminent_danger. Some cases are included
precisely because the deterministic checks are expected to get them wrong.
Silver labels (one developer, no lawyer review). Read-only on the corpus.

  python scripts/build_adversarial_set.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
OUT = BACKEND / "evals" / "chat_length" / "adversarial_v1.jsonl"


def _overlay():
    spec = importlib.util.spec_from_file_location("serve", BACKEND / "scripts" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    os.environ.update(mod.read_env_overlay(BACKEND / ".env.analyzer-demo.local"))


def main() -> int:
    _overlay()
    from app.db.chroma import connect_chroma, get_chroma
    connect_chroma()
    client = get_chroma()

    def chunk(collection, chunk_id):
        res = client.get_collection(collection).get(ids=[chunk_id], include=["documents", "metadatas"])
        if not res["documents"]:
            res = client.get_collection(collection).get(where={"chunk_id": chunk_id},
                                                         include=["documents", "metadatas"])
        meta = res["metadatas"][0]
        return {"statute": meta.get("statute", ""), "section": str(meta.get("section_number", "")),
                "chunk_id": chunk_id, "content": res["documents"][0]}

    lim_57_62 = chunk("civil_collection", "statutes_limitation_act_1908_0128")
    lim_113_117 = chunk("civil_collection", "statutes_limitation_act_1908_0150")
    lim_67_69 = chunk("civil_collection", "statutes_limitation_act_1908_0131")
    lim_cont_theft = chunk("civil_collection", "statutes_limitation_act_1908_0121")
    lim_cont_ditto = chunk("civil_collection", "statutes_limitation_act_1908_0139")
    ppc_489f = chunk("criminal_collection__sec_v2", "statutes_ppc_1860_0760")
    ppc_489 = chunk("criminal_collection__sec_v2", "statutes_ppc_1860_0753")
    ppc_302 = chunk("criminal_collection__sec_v2", "statutes_ppc_1860_0439")
    ppc_506 = chunk("criminal_collection__sec_v2", "statutes_ppc_1860_0794")
    crpc_345_row = chunk("criminal_collection", "statutes_crpc_1898_0928")
    crpc_489_row = chunk("criminal_collection", "statutes_crpc_1898_1380")

    def find(collection, statute, section, heading, must_contain=""):
        res = client.get_collection(collection).get(where={"section_number": section},
                                                     include=["documents", "metadatas"], limit=50)
        for doc, meta in zip(res["documents"], res["metadatas"]):
            if meta.get("statute") == statute and doc.lstrip().startswith(heading)                     and must_contain.lower() in doc.lower():
                return {"statute": statute, "section": section, "chunk_id": meta.get("chunk_id"),
                        "content": doc}
        raise SystemExit(f"not found: {statute} {section}")

    pta_81 = find("civil_collection", "Punjab Tenancy Act 1887", "81", "81.", "thirty")
    # s.15 has a heading-only fragment too (a table-of-contents slice); the
    # case needs the chunk that holds clause (b).
    rent_15 = find("civil_collection", "Punjab Rented Premises Act 2009", "15", "15.", "thirty")
    rent_7 = find("civil_collection", "Punjab Rented Premises Act 2009", "7", "7.")
    crpc_any = find("criminal_collection", "CrPC 1898", "154", "154.")

    def ev(*chunks):
        return [{"id": str(i), "kind": "statute", **c} for i, c in enumerate(chunks, 1)]

    P = []   # (category, sentence, evidence, label, basis)
    P += [
        ("wrong_article", "Under Article 58 of the Limitation Act, a suit on a dishonoured cheque must be filed "
         "within three years [1].", ev(lim_57_62), "unsupported",
         "Art. 58 is a suit for money lent where the LENDER gave a cheque; not a dishonoured-cheque suit."),
        ("wrong_article", "Under Article 57 of the Limitation Act, a suit on a dishonoured cheque must be filed "
         "within three years [1].", ev(lim_57_62), "unsupported", "Art. 57 is money lent, not a cheque suit."),
        ("wrong_article", "Under Article 113 of the Limitation Act, a suit to rescind a contract must be filed "
         "within three years [1].", ev(lim_113_117), "unsupported", "Rescission is Art. 114; Art. 113 is specific performance."),
        ("missing_heading", "Under Section 6 of the Limitation Act, a suit to recover stolen property must be "
         "filed within three years [1].", ev(lim_cont_theft), "unsupported",
         "Chunk starts mid-entry; the article is not shown, and Section 6 (legal disability) sets no period."),
        ("missing_heading", "A suit for an account must be filed within three years [1].", ev(lim_cont_ditto),
         "unsupported", "Continuation slice ('[Three years]. Ditto.'); the entry it belongs to is not shown."),
        ("wrong_act", "Under Section 6 of the Limitation Act, a suit on a dishonoured cheque must be filed "
         "within three years [1].", ev(crpc_any), "unsupported", "Named provision absent; cited text is CrPC s.154."),
        ("wrong_act", "Under Section 15 of the Punjab Rented Premises Act, rent must be paid within thirty days [1].",
         ev(rent_7), "unsupported", "Names s.15 but the evidence is s.7 only."),
        ("wrong_act", "Under Section 81 of the Punjab Tenancy Act, an appeal against a civil court decree must be "
         "filed within ninety days [1].", ev(pta_81), "unsupported",
         "s.81 governs appeals under the Tenancy Act (to Collector/Commissioner/Board of Revenue), not civil-court "
         "decrees. EXPECTED HARD CASE for a lexical check ('decree' appears in s.81)."),
        ("valid_period", "An appeal to the Collector under the Punjab Tenancy Act must be filed within thirty "
         "days [1].", ev(pta_81), "supported", "s.81(a): to the Collector - thirty days."),
        ("valid_period", "The landlord may seek eviction if the tenant fails to pay the rent within thirty days of "
         "it becoming due [1].", ev(rent_15), "supported", "s.15(b)."),
        ("valid_period", "Under Article 69 of the Limitation Act, a suit on a bill of exchange payable at a fixed "
         "time after date must be brought within three years of the bill falling due [1].", ev(lim_67_69),
         "supported", "Art. 69 text."),
        ("valid_period", "Under Article 114 of the Limitation Act, a suit for the rescission of a contract must be "
         "brought within three years [1].", ev(lim_113_117), "supported", "Art. 114 text."),
        ("valid_period", "Under Article 58 of the Limitation Act, a suit for money lent where the lender gave a "
         "cheque for the money must be brought within three years of the cheque being paid [1].", ev(lim_57_62),
         "supported", "Art. 58 text, stated for its own subject."),
        ("valid_period", "Dishonestly issuing a cheque under Section 489-F PPC is punishable with imprisonment "
         "which may extend to three years [1].", ev(ppc_489f), "supported", "s.489-F text."),
        ("valid_period", "دفعہ 489-F PPC کے تحت بے ایمانی سے چیک جاری کرنے کی سزا تین سال تک قید ہے [1]۔",
         ev(ppc_489f), "supported",
         "Urdu restatement of s.489-F. EXPECTED HARD CASE: the Urdu check is deliberately conservative."),
    ]

    PROV = [  # (question, chunk, label, basis)
        ("What is Section 489-F PPC?", ppc_489f, True, "the section's own text"),
        ("What is Section 489-F PPC?", crpc_345_row, False, "CrPC compounding-table row mentioning 489-F"),
        ("What is Section 489-F PPC?", crpc_489_row, False, "CrPC Second Schedule row for 489-F"),
        ("What is Section 489 PPC?", ppc_489f, False, "lettered lookalike: 489-F is not 489"),
        ("What is Section 489-F PPC?", ppc_489, False, "lettered lookalike: 489 is not 489-F"),
        ("What does Section 302 PPC say?", ppc_302, True, "the section's own text"),
        ("What is Section 506 PPC?", ppc_506, True, "the section's own text"),
        ("What is Section 506 PPC?", ppc_302, False, "a different section"),
    ]

    DANGER = [  # (text, label, basis) -- phrasings NOT used in the unit tests
        ("He has a knife and says he will kill me, I'm hiding in the bathroom", True, "armed, threat to life, now"),
        ("میرے شوہر نے کہا ہے کہ وہ مجھے آج رات قتل کر دے گا", True, "threat to kill tonight"),
        ("mere bhai ne aaj mujhe bohat maara aur kehta hai phir maarega", True, "beaten today, threat repeats"),
        ("My ex keeps following me and threatening to throw acid on me", True,
         "repeated threat of acid attack. EXPECTED HARD CASE (acid threat without 'now')"),
        ("What is the punishment for throwing acid on someone?", False, "abstract legal question"),
        ("My husband threatened to divorce me", False, "no threat of violence"),
        ("Can I get bail if I hit someone in self-defence last year?", False, "past, speaker was not the victim"),
        ("My boss shouts at me every day", False, "no violence"),
        ("My father died and my uncle took our land", False, "no violence"),
        ("Someone stole my motorcycle today", False, "property crime, no threat to a person"),
    ]

    with OUT.open("w", encoding="utf-8") as fh:
        for i, (cat, s, evidence, label, basis) in enumerate(P, 1):
            fh.write(json.dumps({"id": f"p{i:02d}", "kind": "period", "category": cat, "sentence": s,
                                 "evidence": evidence, "label": label, "basis": basis},
                                ensure_ascii=False) + "\n")
        for i, (q, ch, label, basis) in enumerate(PROV, 1):
            fh.write(json.dumps({"id": f"x{i:02d}", "kind": "provision", "category": "exact_provision",
                                 "question": q, "chunk": ch, "label": label, "basis": basis},
                                ensure_ascii=False) + "\n")
        for i, (t, label, basis) in enumerate(DANGER, 1):
            fh.write(json.dumps({"id": f"d{i:02d}", "kind": "danger", "category": "imminent_danger",
                                 "text": t, "label": label, "basis": basis}, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({len(P)} period, {len(PROV)} provision, {len(DANGER)} danger)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
