"""The client templates print a complete instrument, not a skeleton (2026-10-19).

The plaint, written statement and legal notice printed each detail as one
unnumbered block with no verification, and the guardianship petition dropped
the material facts it asked for. pleading_rules checked the plaint for its
jurisdiction and valuation particulars under keys no builder read, so every
plaint reported both missing.
"""
from __future__ import annotations

import re

from app.services import pleading_rules, template_registry as reg
from app.services.pdf_generator import template_html


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


PLAINT = {
    "plaintiff_name": "Ayesha Khan", "plaintiff_address": "House 4, Lahore",
    "defendant_name": "Bilal Ahmed", "defendant_address": "Shop 9, Lahore",
    "court_name": "Court of the Senior Civil Judge, Lahore",
    "facts": "The defendant took a loan of Rs 500,000.\nHe has not repaid it.",
    "cause_of_action": "The cause of action arose on 1 March 2026 when payment was refused.",
    "jurisdiction_facts": "The defendant resides and the cause of action arose in Lahore.",
    "valuation": "Rs 500,000",
    "relief_sought": "A decree for Rs 500,000 with costs.",
    "verified_by": "Ayesha Khan",
}


def test_plaint_paragraphs_run_on_through_every_section():
    text = _text(template_html("plaint_civil", PLAINT, placeholders=False))
    assert "1. The defendant took a loan" in text and "2. He has not repaid it." in text
    assert "3. The cause of action arose" in text
    assert "4. The defendant resides" in text
    assert "5. Value of the subject-matter of the suit" in text and "Rs 500,000" in text
    assert "respectfully prayed that a decree may be passed" in text
    assert "VERIFICATION" in text and "Ayesha Khan (verifier)" in text


def test_plaint_jurisdiction_and_valuation_now_reach_the_compliance_check():
    fields = {k: v for k, v in PLAINT.items() if k in reg.fields_for("plaint_civil")}
    assert {"jurisdiction_facts", "valuation", "verified_by"} <= set(fields)
    by = {i["clause"]: i["status"] for i in pleading_rules.check_pleading("plaint_civil", fields)["items"]}
    assert by["(f)"] == "satisfied" and by["(i)"] == "satisfied"
    assert by["Order VI Rule 15"] == "satisfied"


def test_an_empty_plaint_still_says_nothing_between_facts_and_relief():
    text = _text(template_html("plaint_civil", {}, placeholders=False))
    between = text.split("FACTS OF THE CASE", 1)[1].split("RELIEF SOUGHT", 1)[0]
    assert not between.strip()


def test_written_statement_is_numbered_prayed_and_verified():
    text = _text(template_html("written_statement", {
        "defendant_name": "Bilal Ahmed",
        "preliminary_objections": "The suit is time-barred.\nThe court lacks jurisdiction.",
        "reply_on_merits": "Para 1 is denied.",
    }, placeholders=False))
    assert "1. The suit is time-barred." in text and "2. The court lacks jurisdiction." in text
    assert "3. Para 1 is denied." in text
    assert "PRAYER" in text and "dismissed with costs" in text
    assert "Bilal Ahmed (verifier)" in text


def test_legal_notice_numbers_the_grievance_and_states_the_demand():
    text = _text(template_html("legal_notice", {
        "sender_name": "Ayesha Khan", "recipient_name": "Bilal Ahmed",
        "notice_body": "You took a loan.\nYou have not repaid it.",
        "demand": "Pay Rs 500,000.",
    }, placeholders=False))
    assert "1. You took a loan." in text and "2. You have not repaid it." in text
    assert "You are hereby called upon to: Pay Rs 500,000." in text
    assert "legal proceedings shall be initiated without further notice" in text


def test_guardianship_prints_the_material_facts_it_asks_for():
    assert "facts" in reg.fields_for("guardianship_petition")
    text = _text(template_html("guardianship_petition", {
        "minor_name": "Hamza", "facts": "The father died in 2024.\nThe minor lives with the petitioner.",
    }, placeholders=False))
    assert "MATERIAL FACTS" in text
    assert "(1) The father died in 2024." in text and "(2) The minor lives with the petitioner." in text
    blank = _text(template_html("guardianship_petition", {}, placeholders=False))
    assert "MATERIAL FACTS" in blank and "[not stated]" in blank
