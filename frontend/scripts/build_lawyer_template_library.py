"""Convert the reference .docx templates into the lawyer drafter's HTML library.

  python -I build_library.py <docx_dir> <out_js>

Keeps the Word formatting the editor can show (centre / bold / underline / italic, numbered and
bulleted lists with nesting, line breaks, blank spacer lines) and applies the LEGAL FIXES below as
explicit, reviewable edits. Output: an ES module exporting LIBRARY = [{key, name, cat, law, desc,
icon, html}]. Text is HTML-escaped; only the tags the server's draft sanitiser keeps are emitted."""
import html
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def val(el, name="val"):
    return el.get(W + name) if el is not None else None


# ── parse ────────────────────────────────────────────────────────────────────

def numbering_map(z: zipfile.ZipFile) -> dict:
    """numId -> {ilvl: fmt}"""
    if "word/numbering.xml" not in z.namelist():
        return {}
    root = ET.fromstring(z.read("word/numbering.xml"))
    abstract = {}
    for an in root.findall(W + "abstractNum"):
        abstract[val(an, "abstractNumId")] = {
            val(lv, "ilvl"): val(lv.find(W + "numFmt")) for lv in an.findall(W + "lvl")}
    out = {}
    for n in root.findall(W + "num"):
        out[val(n, "numId")] = abstract.get(val(n.find(W + "abstractNumId")), {})
    return out


def parse(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        nums = numbering_map(z)
        body = ET.fromstring(z.read("word/document.xml")).find(W + "body")
    paras = []
    for p in body.iter(W + "p"):
        ppr = p.find(W + "pPr")
        align = val(ppr.find(W + "jc")) if ppr is not None and ppr.find(W + "jc") is not None else "left"
        num = None
        if ppr is not None and ppr.find(W + "numPr") is not None:
            np_ = ppr.find(W + "numPr")
            nid, lvl = val(np_.find(W + "numId")), val(np_.find(W + "ilvl")) or "0"
            if nid and nid != "0":
                num = {"fmt": nums.get(nid, {}).get(lvl, "decimal"), "lvl": int(lvl), "id": nid}
        runs = []
        for r in p.iter(W + "r"):
            rpr = r.find(W + "rPr")
            flag = lambda t: rpr is not None and rpr.find(W + t) is not None and val(rpr.find(W + t)) not in ("0", "false", "none")
            text = ""
            for ch in r:
                if ch.tag == W + "t":
                    text += ch.text or ""
                elif ch.tag == W + "br":
                    text += "\n"
                elif ch.tag == W + "tab":
                    text += " "
            if text:
                runs.append({"text": text, "b": flag("b"), "i": flag("i"), "u": flag("u")})
        paras.append({"align": align, "num": num, "runs": runs})
    return paras


# ── legal fixes (each one stated) ────────────────────────────────────────────

def text_of(p):
    return "".join(r["text"] for r in p["runs"])


def set_text(p, text, bold=False):
    p["runs"] = [{"text": text, "b": bold, "i": False, "u": False}]


def replace_in_runs(paras, old, new):
    hit = 0
    for p in paras:
        for r in p["runs"]:
            if old in r["text"]:
                r["text"] = r["text"].replace(old, new)
                hit += 1
    return hit


def find(paras, starts):
    for i, p in enumerate(paras):
        if " ".join(text_of(p).split()).startswith(starts):
            return i
    raise SystemExit(f"fix target not found: {starts!r}")


def para(text, align="left", bold=False, num=None):
    return {"align": align, "num": num, "runs": [{"text": text, "b": bold, "i": False, "u": False}]}


def fix_dissolution(ps):
    # The heading and ground cited s.7 MFLO 1961 -- that section governs TALAQ notice. A wife's suit
    # for dissolution lies under s.2 of the Dissolution of Muslim Marriages Act 1939, tried by the
    # Family Court under the West Pakistan Family Courts Act 1964.
    set_text(ps[find(ps, "PETITION FOR DISSOLUTION OF MARRIAGE")],
             "SUIT FOR DISSOLUTION OF MARRIAGE UNDER SECTION 2 OF THE DISSOLUTION OF MUSLIM MARRIAGES ACT, "
             "1939, READ WITH THE WEST PAKISTAN FAMILY COURTS ACT, 1964", bold=True)
    i = find(ps, "That the Petitioner is entitled to seek dissolution")
    set_text(ps[i], "That the Petitioner is entitled to a decree for dissolution of marriage under Section 2 of "
                    "the Dissolution of Muslim Marriages Act, 1939, on the ground(s) of [state the clause of "
                    "Section 2 relied on, e.g. (ii) failure to maintain for two years, (viii) cruelty, or (ix) "
                    "any other ground recognised under Muslim law, including khula].")


def fix_custody(ps):
    set_text(ps[find(ps, "APPLICATION FOR CUSTODY OF MINOR")],
             "APPLICATION FOR CUSTODY OF MINOR CHILD(REN) UNDER SECTION 25 OF THE GUARDIANS AND WARDS ACT, 1890",
             bold=True)
    # The prayer was written twice ("Prayer for Relief:" + its items, then "PRAYER" + items).
    i = find(ps, "Prayer for Relief:")
    end = find(ps, "PRAYER")
    del ps[i:end]


def fix_guardianship(ps):
    set_text(ps[find(ps, "APPLICATION FOR APPOINTMENT AS GUARDIAN")],
             "APPLICATION FOR APPOINTMENT AS GUARDIAN OF MINOR CHILD(REN) UNDER SECTIONS 7 AND 10 OF THE "
             "GUARDIANS AND WARDS ACT, 1890", bold=True)


def fix_criminal_petition(ps):
    # "Section [RELEVANT]": a court direction to register an FIR is sought from the Sessions Judge as
    # ex-officio Justice of the Peace under s.22-A(6) CrPC, with the SHO as a respondent.
    set_text(ps[find(ps, "IN THE COURT OF")],
             "IN THE COURT OF THE SESSIONS JUDGE / EX-OFFICIO JUSTICE OF THE PEACE, [LOCATION]", bold=True)
    set_text(ps[find(ps, "Criminal Petition No.")], "Criminal Miscellaneous Petition No. ______/20", bold=True)
    i = find(ps, "[Accused’s Full Name]")
    ps[i] = para("1. Station House Officer, Police Station [Name], [District]\n"
                 "2. [Proposed Accused’s Full Name], S/O [Father’s Name], Resident of [Complete Address]\n"
                 "…Respondents", align="center")
    set_text(ps[find(ps, "PETITION UNDER SECTION")],
             "PETITION UNDER SECTION 22-A(6) OF THE CODE OF CRIMINAL PROCEDURE, 1898 FOR A DIRECTION TO "
             "REGISTER A CASE (FIR)", bold=True)
    replace_in_runs(ps, "direct the relevant police authority", "direct Respondent No. 1")


def fix_civil_suit(ps):
    # A plaint must state the valuation for court fee and jurisdiction (Order VII Rule 1(i) CPC) and be
    # verified (Order VI Rule 15 CPC); the reference text had neither.
    set_text(ps[find(ps, "SUIT FOR [SPECIFY RELIEF")],
             "SUIT FOR [SPECIFY RELIEF: RECOVERY OF MONEY / POSSESSION / INJUNCTION / SPECIFIC PERFORMANCE / "
             "ETC.] — PLAINT UNDER ORDER VII RULE 1, C.P.C.", bold=True)
    i = find(ps, "Jurisdiction:")
    num = ps[i]["num"]
    ps.insert(i + 1, {"align": "left", "num": num, "runs": [
        {"text": "Valuation:\n", "b": True, "i": False, "u": False},
        {"text": "The suit is valued at PKR [Amount] for the purposes of court fee and at PKR [Amount] for the "
                 "purposes of jurisdiction, and the requisite court fee has been affixed.",
         "b": False, "i": False, "u": False}]})
    j = find(ps, "Plaintiff")
    ps[j:j] = [para("VERIFICATION", bold=True),
               para("Verified on oath at [Place] on this [Date] that the contents of paragraphs [__] are true to "
                    "my own knowledge and those of paragraphs [__] are true on information received and believed "
                    "to be true. (Order VI Rule 15, C.P.C.)"),
               para("")]


def fix_habeas(ps):
    # The District Coordination Officer post no longer exists; the respondent is the Deputy Commissioner.
    replace_in_runs(ps, "District Coordination Officer / Deputy Commissioner", "Deputy Commissioner")



# ── the second batch (2026-10-19): the user's own reference downloads ────────

def must_replace(ps, old, new):
    if not replace_in_runs(ps, old, new):
        raise SystemExit(f"fix target not found: {old!r}")


RENT_LAW = ("the applicable provincial rent law (Punjab Rented Premises Act, 2009 / Sindh Rented Premises "
            "Ordinance, 1979 / Islamabad Rent Restriction Ordinance, 2001 / Khyber Pakhtunkhwa Rented "
            "Premises Act, 2019)")


def fix_sale_deed(ps):
    # "Bayana nama" is the earnest-money agreement TO sell; a deed that conveys title is a "bai nama".
    must_replace(ps, "(BAYNA NAMA)", "(BAI NAMA)")


def fix_consumer(ps):
    # The Consumer Protection Act 2019 is India's. Pakistan's consumer courts sit under the provincial
    # Acts (and the Islamabad Act), and a complaint follows a written notice to the defendant.
    set_text(ps[find(ps, "IN THE DISTRICT CONSUMER PROTECTION COUNCIL")], "IN THE DISTRICT CONSUMER COURT", bold=True)
    set_text(ps[find(ps, "COMPLAINT UNDER THE CONSUMER PROTECTION ACT")],
             "COMPLAINT UNDER THE [PUNJAB CONSUMER PROTECTION ACT, 2005 / SINDH CONSUMER PROTECTION ACT, 2014 / "
             "KHYBER PAKHTUNKHWA CONSUMERS PROTECTION ACT, 1997 / BALOCHISTAN CONSUMER PROTECTION ACT, 2003 / "
             "ISLAMABAD CONSUMERS PROTECTION ACT, 1995]", bold=True)
    i = find(ps, "3. That the Complainant reported the defect")
    ps.insert(i + 1, para("3-A. That before filing this complaint the Complainant served a written notice on the "
                          "Respondent on [Date], as the applicable Act requires, and the Respondent failed to "
                          "remedy the matter within the time allowed (copy annexed as Annexure \"B\")."))


def fix_eviction(ps):
    # Eviction is sought by an application to the Rent Tribunal / Rent Controller under the provincial
    # rent law, not by a civil suit.
    must_replace(ps, "file a suit for eviction and recovery of rent/mesne profits before the Rent "
                     "Controller/Competent Court",
                 "file an eviction application, and claim the rent due, before the Rent Tribunal / Rent "
                 "Controller under " + RENT_LAW)


def fix_tenancy(ps):
    must_replace(ps, "Rent Restriction Ordinance of [Province] (if applicable)", RENT_LAW)


def fix_sub_lease(ps):
    must_replace(ps, "Rent Restrictions laws of [Province]", RENT_LAW)


def fix_nepra(ps):
    # No "NEPRA (Consumer Protection) Rules, 2022" could be confirmed; a complaint against a licensee
    # lies under section 39 of the NEPRA Act 1997.
    set_text(ps[find(ps, "CONSUMER COMPLAINT UNDER NEPRA")],
             "COMPLAINT UNDER SECTION 39 OF THE REGULATION OF GENERATION, TRANSMISSION AND DISTRIBUTION OF "
             "ELECTRIC POWER ACT, 1997", bold=True)
    must_replace(ps, "for violation of Consumer Protection Rules", "under the Act")


FIXES = {
    "Dissolution Of Marriage Application": fix_dissolution,
    "Custody Application": fix_custody,
    "Guardianship Application": fix_guardianship,
    "Criminal Petition": fix_criminal_petition,
    "Civil Suit Application": fix_civil_suit,
    "Habeas Writ Petition": fix_habeas,
    "Deed Of Sale": fix_sale_deed,
    "Consumer Complaint": fix_consumer,
    "Eviction Notice": fix_eviction,
    "Commercial Tenancy Agreement": fix_tenancy,
    "Sub Lease Agreement": fix_sub_lease,
    "NEPRA Complaint": fix_nepra,
}
GLOBAL = [("Guardian and Wards Act", "Guardians and Wards Act")]


# ── metadata (card text) ─────────────────────────────────────────────────────

APP, AGR, BUS, LET = "Application / Petition", "Agreement / Contract", "Business / Commercial", "Notice / Letter"
PROP = "Property"
META = {
    "Dissolution Of Marriage Application": (1, "Dissolution of Marriage Application", APP, "DMMA 1939 s.2 · Family Courts Act 1964",
                                            "Wife's suit for dissolution — parties, marriage, grounds under s.2 DMMA, prayer.", "⚖️"),
    "Civil Suit Application": (2, "Plaint — Civil Suit", APP, "CPC Order VII Rule 1",
                               "Plaint with parties, cause of action, jurisdiction, valuation, verification and prayer.", "🏛️"),
    "Bail Application": (3, "Bail Application", APP, "CrPC ss.496–498",
                         "Bail in a registered FIR — grounds, undertaking, Articles 9–10, prayer.", "🔓"),
    "Habeas Writ Petition": (4, "Habeas Corpus Writ Petition", APP, "Constitution Art. 199(1)(b)(i)",
                             "High Court writ for production and release of a person illegally detained.", "🏛️"),
    "Review Petition": (5, "Review Petition", APP, "CPC Order XLVII Rule 1",
                        "Review of a judgment for new evidence, error on the face of the record or sufficient reason.", "🔁"),
    "Custody Application": (6, "Custody Application", APP, "Guardians and Wards Act 1890 s.25",
                            "Custody of minor child(ren) — welfare grounds, visitation, maintenance.", "👨‍👧"),
    "Guardianship Application": (7, "Guardianship Application", APP, "Guardians and Wards Act 1890 ss.7, 10",
                                 "Appointment as guardian of the person and property of a minor.", "🛡️"),
    "Criminal Petition": (8, "Petition for Registration of FIR", APP, "CrPC s.22-A(6)",
                          "Petition to the Justice of the Peace for a direction to register an FIR.", "🚓"),
    "Application For Leave": (9, "Application for Leave", LET, "General correspondence",
                              "Leave application — dates, reason, handover.", "🗓️"),
    "Lease Agreement": (10, "Lease Agreement", AGR, "Contract Act 1872 · TPA 1882",
                        "Premises, term, rent, deposit, maintenance, use, termination, governing law.", "🏠"),
    "Loan Agreement": (11, "Loan Agreement", AGR, "Contract Act 1872",
                       "Principal, repayment schedule, default, security and governing law.", "💵"),
    "Sale And Purchase Agreement": (12, "Sale and Purchase Agreement", AGR, "Contract Act 1872 · Sale of Goods Act 1930",
                                    "Parties, goods/property, price, payment, delivery, warranties.", "🤝"),
    "Employment Contract": (13, "Employment Contract", AGR, "Contract Act 1872",
                            "Position, term, salary, duties, leave, confidentiality, termination.", "💼"),
    "Consultancy Agreement": (14, "Consultancy Agreement", AGR, "Contract Act 1872",
                              "Services, fees, deliverables, IP, confidentiality, termination.", "🧭"),
    "Articles Of Association": (15, "Articles of Association", BUS, "Companies Act 2017",
                                "Company articles — shares, meetings, directors, accounts, winding up.", "🏢"),
    "Board Resolution": (16, "Board Resolution", BUS, "Companies Act 2017",
                         "Resolution of the board — meeting details, resolutions passed, signatures.", "📋"),
    "Notice Letter": (17, "Notice Letter", LET, "General correspondence",
                      "Formal notice — subject, grounds, time to act.", "📨"),
    "Cover Letter": (18, "Cover Letter", LET, "General correspondence", "Covering letter for documents or an application.", "✉️"),
    "Reference Letter": (19, "Reference Letter", LET, "General correspondence", "Reference / recommendation letter.", "📝"),
    "Resignation Letter": (20, "Resignation Letter", LET, "General correspondence", "Resignation with notice period and handover.", "🚪"),
    "Termination Letter": (21, "Termination Letter", LET, "General correspondence", "Termination of employment — grounds, dues, return of property.", "📕"),
    "Employment Offer Letter": (22, "Employment Offer Letter", LET, "General correspondence", "Offer of employment — role, pay, terms, acceptance.", "🎉"),
    "General Letter": (23, "General Letter", LET, "General correspondence", "A general formal letter.", "📄"),
    "Follow Up Email": (24, "Follow-up Email", LET, "General correspondence", "Follow-up email on a pending matter.", "📧"),
    # Second batch (2026-10-19), from the user's own downloads of the same reference site.
    "Deed Of Gift": (25, "Deed of Gift (Hiba Nama)", PROP, "Muslim law of gift · Registration Act 1908 s.17",
                     "Gift of immovable property — declaration, delivery of possession, schedule, registration.", "🎁"),
    "Deed Of Sale": (26, "Sale Deed (Bai Nama)", PROP, "Transfer of Property Act 1882 s.54 · Registration Act 1908",
                     "Absolute sale — consideration and receipt, transfer, possession, title warranty, schedule.", "🏡"),
    "Deed Of Relinquishment": (27, "Deed of Relinquishment", PROP, "Registration Act 1908",
                               "A co-sharer gives up a share in joint property in favour of another.", "✋"),
    "Deed Of Exchange": (28, "Deed of Exchange (Mubadila Nama)", PROP, "Transfer of Property Act 1882 s.118",
                         "Two owners exchange properties — schedules, balancing payment, possession.", "🔄"),
    "Deed Of Partition": (29, "Deed of Partition", PROP, "Registration Act 1908",
                          "Co-owners divide joint property by metes and bounds — portions, possession, release.", "🧩"),
    "Easement Agreement": (30, "Easement Agreement (Right of Way)", PROP, "Easements Act 1882",
                           "Right of way over a servient tenement — purpose, extent, restrictions, duration.", "🛣️"),
    "Affidavit Of Non Encumbrance": (31, "Affidavit of Non-Encumbrance", PROP, "Oaths Act 1873",
                                     "Owner's sworn declaration that property is free of charges, liens and litigation.", "📜"),
    "Property Development Agreement": (32, "Property Development Agreement", PROP, "Contract Act 1872 · Arbitration Act 1940",
                                       "Landowner and developer — contributions, profit share, approvals, allotted units.", "🏗️"),
    "Commercial Tenancy Agreement": (33, "Commercial Tenancy Agreement", AGR, "Contract Act 1872 · provincial rent law",
                                     "Shop / office tenancy — term, rent, escalation, deposit, use, fit-out, renewal.", "🏬"),
    "Sub Lease Agreement": (34, "Sub-Lease Agreement", AGR, "Contract Act 1872 · provincial rent law",
                            "Sub-letting by a tenant with the owner's consent — term, rent, deposit, use.", "🔑"),
    "Legal Notice": (35, "Legal Notice (General)", LET, "Pre-litigation notice",
                     "Advocate's notice — numbered facts, demand within 15 days, consequences.", "📮"),
    "Breach Of Contract Notice": (36, "Notice of Breach of Contract", LET, "Contract Act 1872 ss.39, 73",
                                  "Breach particulars, losses, demand to cure within 14 days, rights reserved.", "⚠️"),
    "Cease And Desist Notice": (37, "Cease and Desist Notice", LET, "Trade Marks Ordinance 2001 · tort",
                                "Demand to stop infringement, defamation, trespass or passing off.", "🛑"),
    "Eviction Notice": (38, "Eviction / Vacation Notice", LET, "Provincial rent law",
                        "Landlord's notice — grounds, rent due, time to vacate, eviction application.", "🏚️"),
    "Demand Notice": (39, "Demand Notice for Outstanding Dues", LET, "Contract Act 1872",
                      "Invoices due, mark-up, total, seven days to pay, recovery proceedings.", "💰"),
    "Consumer Complaint": (40, "Consumer Court Complaint", APP, "Provincial consumer protection law",
                           "Defective product or deficient service — facts, prior notice, loss, refund and compensation.", "🛒"),
    "Income Tax Appeal": (41, "Income Tax Appeal (ITAT)", APP, "Income Tax Ordinance 2001 s.131",
                          "Appeal against the Commissioner (Appeals) order — grounds and prayer.", "🧾"),
    "NEPRA Complaint": (42, "NEPRA Consumer Complaint", APP, "NEPRA Act 1997 s.39",
                        "Complaint against a DISCO — inflated bills, disconnection, faulty meter.", "⚡"),
    "SECP Complaint": (43, "SECP Complaint", BUS, "Companies Act 2017 · Securities Act 2015",
                       "Shareholder or investor complaint about a company's violations.", "📈"),
    "Competition Commission Complaint": (44, "Competition Commission Complaint", BUS, "Competition Act 2010 s.37",
                                         "Abuse of dominance, prohibited agreements or deceptive marketing.", "🏛️"),
}


# ── render ───────────────────────────────────────────────────────────────────

def run_html(r):
    t = html.escape(r["text"], quote=False).replace("\n", "<br>")
    if r["u"]:
        t = f"<u>{t}</u>"
    if r["i"]:
        t = f"<em>{t}</em>"
    if r["b"]:
        t = f"<strong>{t}</strong>"
    return t


def inline(p):
    return "".join(run_html(r) for r in p["runs"]).rstrip()


def block(p):
    body = inline(p) or "<br>"
    if p["align"] in ("center", "right", "both"):
        a = {"both": "justify"}.get(p["align"], p["align"])
        return f'<p style="text-align:{a}">{body}</p>'
    return f"<p>{body}</p>"


def render(paras):
    out, i = [], 0
    # drop leading / trailing blank paragraphs
    while paras and not text_of(paras[0]).strip():
        paras = paras[1:]
    while paras and not text_of(paras[-1]).strip():
        paras = paras[:-1]
    while i < len(paras):
        p = paras[i]
        if not p["num"]:
            out.append(block(p))
            i += 1
            continue
        # a run of list paragraphs (any level) -> nested lists
        items = []
        while i < len(paras) and paras[i]["num"]:
            items.append(paras[i])
            i += 1
        out.append(render_list(items, 0))
    return "".join(out)


def tag_for(fmt):
    return "ul" if fmt == "bullet" else "ol"


def render_list(items, lvl):
    html_parts, k = [], 0
    tag = tag_for(items[0]["num"]["fmt"])
    html_parts.append(f"<{tag}>")
    while k < len(items):
        it = items[k]
        li = inline(it)
        k += 1
        children = []
        while k < len(items) and items[k]["num"]["lvl"] > lvl:
            children.append(items[k])
            k += 1
        if children:
            li += render_list(children, lvl + 1)
        html_parts.append(f"<li>{li}</li>")
    html_parts.append(f"</{tag}>")
    return "".join(html_parts)


def main(src, out_js):
    lib, report = [], []
    for f in sorted(Path(src).glob("*.docx")):
        key = re.sub(r"_2026-10-14T.*$", "", f.stem)
        if key not in META:
            raise SystemExit(f"no metadata for {key}")
        ps = parse(f)
        for old, new in GLOBAL:
            n = replace_in_runs(ps, old, new)
            if n:
                report.append(f"{key}: '{old}' -> '{new}' x{n}")
        if key in FIXES:
            FIXES[key](ps)
            report.append(f"{key}: {FIXES[key].__name__}")
        tid, name, cat, law, desc, icon = META[key]
        lib.append({"id": tid, "key": key, "name": name, "cat": cat, "law": law, "desc": desc,
                    "icon": icon, "html": render(ps)})
    lib.sort(key=lambda x: x["id"])
    header = ("/* GENERATED by build_library.py from the reference .docx templates (2026-10-14; 20 more on\n"
              " * 2026-10-19) -- do not hand-edit\n"
              " * the HTML; change the generator and re-run. Formatting kept from Word: centred / bold headings,\n"
              " * numbered paragraphs, nested lists, Times-style court layout. Legal fixes applied by the generator\n"
              " * (each stated there): Dissolution -> DMMA 1939 s.2 (not MFLO s.7); Guardians and Wards Act name and\n"
              " * sections (25; 7, 10); duplicate custody prayer removed; FIR petition -> CrPC s.22-A(6) with the\n"
              " * SHO as respondent; plaint valuation (O.VII r.1) and verification (O.VI r.15); DCO -> Deputy\n"
              " * Commissioner; sale deed is a bai nama (not bayana); consumer complaint under the provincial Acts\n"
              " * (not India's 2019 Act) with prior notice; eviction by application to the Rent Tribunal /\n"
              " * Controller; provincial rent laws named; NEPRA complaint under s.39 of the NEPRA Act 1997.\n"
              " * These are developer corrections -- a lawyer should review before filing. */\n")
    js = header + "export const LIBRARY = " + json.dumps(lib, ensure_ascii=False, indent=1) + ";\n"
    Path(out_js).write_text(js, encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(report))
    print(f"{len(lib)} templates -> {out_js}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
