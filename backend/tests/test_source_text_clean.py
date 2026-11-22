"""Footnote markers are removed from statute text; real numbers never are."""
from app.ai.source_text_clean import clean_statute_text as clean


def test_ppc_406_reads_seven_years():
    stored = ("Whoever, commits criminal breach of trust snail be punished with imprisonment of either\n"
              "description for a term which may extend to  160[seven] 160 years, or with fine, or with both.")
    out = clean(stored)
    assert "may extend to seven years" in out
    assert "160" not in out and "snail" not in out and "shall be punished" in out


def test_fines_keep_the_amount_and_lose_the_marker():
    assert clean("fine which may extend to  38[one thousand five hundred rupees] 38, or with both.") \
        == "fine which may extend to one thousand five hundred rupees, or with both."
    assert clean("penalty not exceeding  35[one thousand five hundred rupees] 35, if he") \
        == "penalty not exceeding one thousand five hundred rupees, if he"


def test_empty_and_leading_markers():
    assert clean("of the public or any community.      8[] 8 Explanation") == "of the public or any community. Explanation"
    assert clean("committed by:-   1[(1) any citizen of Pakistan") == "committed by:- [(1) any citizen of Pakistan"


def test_real_numbers_are_never_touched():
    for text in ("Section 302 of the Pakistan Penal Code", "a fine of Rs. 1,000 or both",
                 "under sub-section (2) of section 154", "Article 10A", "section 22-A [inserted]",
                 "imprisonment for 7 years", "1860", "clause [a] of section 3", "Rs.10,000[sic]"):
        assert clean(text) == text, text


def test_idempotent_and_empty():
    once = clean("may extend to  160[seven] 160 years")
    assert clean(once) == once
    assert clean("") == "" and clean(None) == ""


def test_a_marker_alone_on_its_line_is_removed():
    stored = "established or \ncontinued by \n4\n[the \n5\n[Federal Government] \n6\n[* * * *] ]: \n(6)"
    out = clean(stored)
    assert "\n4\n" not in out and "\n5\n" not in out and "\n6\n" not in out
    assert "[the \n[Federal Government]" in out and "(6)" in out


def test_a_real_number_ending_a_line_stays():
    for text in ("under section 3\n[and the rules]", "rule 12\n[omitted]", "page\n(2)\n[text]"):
        assert clean(text) == text, text


def test_the_retrieval_pipeline_hands_clean_text_to_generation_and_the_check():
    """The single point every retrieval path passes through (retrieval_node.
    _docs_to_chunks) is where the cleaning happens, so the answer-writer AND
    the statement check both read "seven years"."""
    from langchain_core.documents import Document
    from app.ai.nodes import retrieval_node
    doc = Document(
        page_content=("406. Punishment for criminal breach of trust: \nWhoever, commits criminal breach of "
                      "trust snail be punished with imprisonment of either \ndescription for a term which may "
                      "extend to  160[seven] 160 years, or with fine, or with both."),
        metadata={"statute": "PPC 1860", "section_number": "406", "province": "federal",
                  "law_type": "criminal", "chunk_id": "ppc-406"})
    chunks = retrieval_node._docs_to_chunks([doc], "punjab")
    text = chunks[0]["content"]
    assert "may extend to seven years" in text and "160" not in text and "shall be punished" in text
