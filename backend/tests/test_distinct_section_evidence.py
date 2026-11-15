"""One evidence slot per section before any section gets a second (2026-10-22).

Live: "chori ki saza kya hai?" retrieved PPC s.379, but the grounding retry
(4 sources) was filled by PPC s.108 twice and Police Order s.4, so the answer
said s.379 was not among its sources. Orders below are the measured ones.
"""
from app.ai.answer_citations import build_generation_evidence, distinct_sections_first


def _c(cid, statute, section, **extra):
    return {"chunk_id": cid, "statute": statute, "section_number": section, "content": f"text of {cid}",
            "source_file": f"{statute}.pdf", **extra}


# Reranked order of the live retry for "chori ki saza kya hai?".
CHORI = [
    _c("po_0208", "Police Order 2002", "4"),
    _c("ppc_0133", "PPC 1860", "108"),
    _c("ppc_0602", "PPC 1860", "382"),
    _c("ppc_0134", "PPC 1860", "108"),
    _c("ppc_0598", "PPC 1860", "379"),
    _c("po_0209", "Police Order 2002", "4"),
    _c("ppc_0346", "PPC 1860", "227"),
]


def test_the_retry_window_now_reaches_section_379():
    old = build_generation_evidence(CHORI, statute_limit=4)
    new = build_generation_evidence(CHORI, statute_limit=4, distinct_first=True)
    assert "379" not in [e["section"] for e in old], "the measured failure"
    assert [e["section"] for e in new] == ["4", "108", "382", "379"]
    assert [e["id"] for e in new] == ["1", "2", "3", "4"], "ids stay one numbered space"


def test_nothing_is_dropped_only_reordered():
    out = distinct_sections_first(CHORI)
    assert sorted(c["chunk_id"] for c in out) == sorted(c["chunk_id"] for c in CHORI)
    assert [c["chunk_id"] for c in out] == ["po_0208", "ppc_0133", "ppc_0602", "ppc_0598", "ppc_0346",
                                            "ppc_0134", "po_0209"]


def test_a_sections_best_ranked_part_is_the_one_kept_first():
    # Family Courts Act s.10 is four chunks; the one with the khula sub-section
    # ranked first and must stay first.
    khula = [_c("fca_0057_khula", "Family Courts Act 1964", "10"), _c("fca_0049", "Family Courts Act 1964", "7"),
             _c("fca_0056", "Family Courts Act 1964", "10"), _c("fca_0101", "Family Courts Act 1964", "4")]
    out = [c["chunk_id"] for c in distinct_sections_first(khula)]
    assert out == ["fca_0057_khula", "fca_0049", "fca_0101", "fca_0056"]


def test_the_same_section_number_in_another_act_is_a_different_section():
    chunks = [_c("a", "PPC 1860", "10"), _c("b", "Family Courts Act 1964", "10"), _c("c", "PPC 1860", "10")]
    assert [c["chunk_id"] for c in distinct_sections_first(chunks)] == ["a", "b", "c"]


def test_a_provision_the_user_named_keeps_every_part_in_place():
    chunks = [_c("x1", "PPC 1860", "489-F", exact_provision="Section 489-F PPC"),
              _c("x2", "PPC 1860", "489-F", exact_provision="Section 489-F PPC"),
              _c("y", "CrPC 1898", "154"), _c("x3", "PPC 1860", "489-F")]
    assert [c["chunk_id"] for c in distinct_sections_first(chunks)] == ["x1", "x2", "y", "x3"]


def test_an_issue_provision_keeps_its_place():
    chunks = [_c("g1", "Limitation Act 1908", "3", issue_provision={"section": "3"}),
              _c("g2", "Limitation Act 1908", "3", issue_provision={"section": "3"}), _c("z", "CPC 1908", "9")]
    assert [c["chunk_id"] for c in distinct_sections_first(chunks)] == ["g1", "g2", "z"]


def test_chunks_without_a_section_are_never_grouped():
    chunks = [_c("w1", "https://example.org", ""), _c("w2", "https://example.org", ""), _c("s", "PPC 1860", "1")]
    assert [c["chunk_id"] for c in distinct_sections_first(chunks)] == ["w1", "w2", "s"]


def test_default_order_is_unchanged_for_intake():
    assert [e["chunk_id"] for e in build_generation_evidence(CHORI, statute_limit=4)] == \
        ["po_0208", "ppc_0133", "ppc_0602", "ppc_0134"]
    assert distinct_sections_first(None) == [] and distinct_sections_first([]) == []


async def test_generation_node_uses_distinct_sections(monkeypatch):
    from app.ai.nodes import generation_node as gn
    seen = {}
    real = gn.build_generation_evidence

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(gn, "build_generation_evidence", spy)

    class LLM:
        def invoke(self, msgs):
            return type("R", (), {"content": 'Theft is punished under Section 379 PPC [4].\n{"confidence": 0.8}'})()

        def stream(self, msgs):
            yield self.invoke(msgs)
    monkeypatch.setattr(gn, "get_llm", lambda **k: LLM())
    out = await gn.generation_node({"query": "chori ki saza kya hai?", "reranked_chunks": CHORI,
                                    "generation_attempts": 1, "case_type": "criminal", "province": "unknown",
                                    "language": "roman_urdu", "surface": "client"})
    assert seen.get("distinct_first") is True and seen.get("statute_limit") == 4
    assert "379" in [e["section"] for e in out["generation_evidence"] if e["kind"] == "statute"]
