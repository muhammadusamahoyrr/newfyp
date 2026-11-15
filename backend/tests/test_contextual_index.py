"""Deterministic contextual indexing (Batch 5): metadata-only prefixes, a lost
section letter restored from the passage header, unknowns left unknown, raw
text recoverable, and the A/B switch never touching the base collection."""
from app.ai import contextual_index as C


def test_the_prefix_comes_only_from_metadata_and_marks_unknowns():
    doc, meta = C.contextualize({"statute": "PPC 1860", "section_number": "379", "province": "federal"},
                                "379. Punishment for theft")
    assert doc.startswith("Instrument: PPC 1860\nProvision: Section 379\nJurisdiction: federal\n")
    assert "Area of law: unknown" in doc and "Chapter: unknown" in doc
    assert "Status: unknown" in doc, "PPC has no omission data; 'in force' must not be claimed"


def test_a_lost_letter_is_restored_from_the_passage_itself():
    doc, meta = C.contextualize({"statute": "PPC 1860", "section_number": "489"},
                                "489- F.  Dishonestly issuing a cheque")
    assert meta["provision_label"] == "489-F" and "Provision: Section 489-F" in doc


def test_an_omitted_section_is_marked_from_the_omission_record():
    doc, _ = C.contextualize({"statute": "CrPC 1898", "section_number": "562"}, "562. Power of Court")
    assert "Status: omitted (" in doc


def test_the_raw_text_is_recoverable_and_base_is_untouched_by_default():
    raw = "15. Eviction of a tenant"
    doc, meta = C.contextualize({"statute": "Punjab Rented Premises Act 2009", "section_number": "15"}, raw)
    assert C.strip_context(doc, meta) == raw
    assert C.strip_context(raw, {}) == raw, "base-index text must pass through unchanged"
    assert C.collection_for("civil_collection", "base") == "civil_collection"
    assert C.collection_for("civil_collection", None) == "civil_collection"
    assert C.collection_for("civil_collection", "ctx_v1") == "civil_collection__ctx_v1"


def test_the_production_default_is_the_base_index():
    from app.core.config import Settings
    assert Settings.model_fields["retrieval_index_variant"].default == "base"
