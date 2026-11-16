"""Provisional lawyer suggestions for the client chat, and the match route's
case states (2026-10-16).

THE BUG. Client chat sessions carry no case binding -- deliberately, a client
used to be able to bind their chat to any case id -- but the chat's lawyer
suggestions still went through `match_lawyers_for_case(session["case_id"])`, so
they were ALWAYS "unavailable": under every clarifying question, and on the
answer that told the client to consult a lawyer.

THE FIX. Suggestions come from what the SERVER concluded the conversation is
about (the graph's case type, its confidence, the resolved province), never
from a case and never from an unrelated latest case; they are a browse list,
never scored; weak signals suggest nobody; the vector store is never touched.
"""
import pytest

from app.core.security import hash_password
from app.services import lawyer_service as ls
from app.websockets import chat_socket as cs

pytestmark = pytest.mark.integration


def _lawyer(_id, *, province, specs, verified=True, active=True, rating=4.0):
    return {
        "_id": _id, "role": "lawyer", "email": f"{_id.lower()}@x.test",
        "password_hash": hash_password("Str0ngPass1"), "full_name": f"Adv {_id}",
        "is_active": active, "province": province,
        "lawyer_profile": {"bar_number": f"BAR-{_id}", "specializations": specs,
                           "kyc_verified": verified, "rating": rating,
                           "availability": True, "experience_years": 8},
    }


@pytest.fixture
async def lawyers(mongo, monkeypatch):
    from app.db.collections import get_cases_col, get_users_col

    # The vector store must never be consulted on this path.
    def _forbidden(*_a, **_k):
        raise AssertionError("the vector store was touched")
    monkeypatch.setattr("app.ai.lawyer_embeddings.query_similar_lawyers", _forbidden)
    monkeypatch.setattr("app.ai.lawyer_embeddings.forget_lawyers", _forbidden)

    await get_users_col().delete_many({"_id": {"$regex": "^PS-"}})
    await get_cases_col().delete_many({"_id": {"$regex": "^PS-"}})
    await get_users_col().insert_many([
        _lawyer("PS-CIVIL-PB", province="punjab", specs=["civil"], rating=4.6),
        _lawyer("PS-CIVIL-FED", province="federal", specs=["civil"], rating=4.1),
        _lawyer("PS-CIVIL-SD", province="sindh", specs=["civil"]),
        _lawyer("PS-FAMILY-PB", province="punjab", specs=["family"], rating=5.0),
        _lawyer("PS-CIVIL-UNVER", province="punjab", specs=["civil"], verified=False),
        _lawyer("PS-CIVIL-OFF", province="punjab", specs=["civil"], active=False),
        {"_id": "PS-CLIENT", "role": "client", "email": "ps-c@x.test",
         "password_hash": hash_password("Str0ngPass1"), "is_active": True},
        {"_id": "PS-OTHER", "role": "client", "email": "ps-o@x.test",
         "password_hash": hash_password("Str0ngPass1"), "is_active": True},
    ])
    await get_cases_col().insert_many([
        {"_id": "PS-CASE-DRAFT", "client_id": "PS-CLIENT", "case_type": "civil",
         "province": "punjab", "title": "Rent", "description": "Unpaid rent.", "status": "draft",
         "case_number": "PS-T-0001"},
        {"_id": "PS-CASE-OTHER", "client_id": "PS-OTHER", "case_type": "civil",
         "province": "punjab", "title": "Rent", "description": "Unpaid rent.", "status": "open",
         "case_number": "PS-T-0002"},
    ])
    yield
    await get_users_col().delete_many({"_id": {"$regex": "^PS-"}})
    await get_cases_col().delete_many({"_id": {"$regex": "^PS-"}})


def _ids(result):
    return [m["_id"] for m in result["matches"]]


# ── the service ──────────────────────────────────────────────────────────────

async def test_a_confident_topic_suggests_verified_lawyers_who_list_it_unscored(lawyers):
    out = await ls.suggest_lawyers_from_signals(
        case_type="civil", case_type_confidence=0.9, province="punjab", top_n=10)
    ids = _ids(out)
    assert out["result_kind"] == "provisional"
    assert "PS-CIVIL-PB" in ids and "PS-CIVIL-FED" in ids        # province + nationwide
    for excluded in ("PS-CIVIL-SD", "PS-FAMILY-PB", "PS-CIVIL-UNVER", "PS-CIVIL-OFF"):
        assert excluded not in ids, excluded
    assert all(m["match_score"] is None for m in out["matches"]), "a browse list was scored"
    assert ids.index("PS-CIVIL-PB") < ids.index("PS-CIVIL-FED"), "the local lawyer should lead"
    assert "have not been matched to your facts" in out["notice"]
    assert "in Punjab" in out["notice"]


@pytest.mark.parametrize("confidence", [0.0, 0.5, 0.69, None, "high", float("nan")])
async def test_a_low_or_unusable_confidence_suggests_nobody_and_says_nothing(lawyers, confidence):
    out = await ls.suggest_lawyers_from_signals(
        case_type="civil", case_type_confidence=confidence, province="punjab")
    assert out == {"result_kind": "unavailable", "notice": "", "matches": []}


@pytest.mark.parametrize("case_type", [None, "", "unknown", "property", "CIVIL "])
async def test_a_missing_or_unknown_type_suggests_nobody(lawyers, case_type):
    out = await ls.suggest_lawyers_from_signals(
        case_type=case_type, case_type_confidence=0.95, province="punjab")
    if case_type == "CIVIL ":                       # normalised, so this one is real
        assert out["result_kind"] == "provisional"
    else:
        assert out["result_kind"] == "unavailable" and out["matches"] == []


@pytest.mark.parametrize("province", [None, "", "unknown", "lahore"])
async def test_a_missing_or_invalid_province_widens_to_the_whole_country(lawyers, province):
    out = await ls.suggest_lawyers_from_signals(
        case_type="civil", case_type_confidence=0.9, province=province, top_n=10)
    assert out["result_kind"] == "provisional"
    assert "PS-CIVIL-SD" in _ids(out), "a lawyer outside the (unknown) province was hidden"
    assert "across Pakistan" in out["notice"]


async def test_a_type_nobody_lists_says_so(lawyers, monkeypatch):
    from app.schemas.common import PaginatedResponse

    async def _empty(**_k):
        return PaginatedResponse(items=[], total=0, page=1, page_size=12, pages=0)
    monkeypatch.setattr(ls.user_repo, "find_lawyers", _empty)
    out = await ls.suggest_lawyers_from_signals(
        case_type="constitutional", case_type_confidence=0.9, province="sindh")
    assert out["result_kind"] == "none" and out["matches"] == []
    assert out["notice"] == "No registered lawyer lists constitutional matters in Sindh yet."


# ── the chat wiring: no case, no frame, no latest case ───────────────────────

def test_signals_come_from_graph_state_and_hybrid_turns_give_none():
    assert cs._conversation_signals({"case_type": "family", "case_type_confidence": 0.4,
                                     "classifier_confidence": 0.9, "province": "kpk"}) == {
        "case_type": "family", "case_type_confidence": 0.9, "province": "kpk"}
    assert cs._conversation_signals({"case_type": "civil", "case_type_confidence": 0.9,
                                     "routing_mode": "hybrid"}) is None
    assert cs._conversation_signals({"case_type": "unknown", "case_type_confidence": 0.9}) is None
    assert cs._conversation_signals({"case_type": "civil",
                                     "case_type_confidence": float("inf")})["case_type_confidence"] == 0.0
    assert cs._conversation_signals(None) is None


def test_a_client_frame_still_cannot_bind_a_case():
    assert "case_id" not in cs._session_meta_from_frame({"case_id": "PS-CASE-OTHER",
                                                        "case_type": "civil"})


async def test_a_client_chat_never_matches_a_case(lawyers, monkeypatch):
    async def _no_case_matching(*_a, **_k):
        raise AssertionError("a case was matched for a client chat")
    monkeypatch.setattr(ls, "match_lawyers_for_case", _no_case_matching)

    session = {"session_id": "s1", "owner_id": "PS-CLIENT", "case_id": None}
    out = await cs._fetch_matched_lawyers(
        session, n=3, signals={"case_type": "civil", "case_type_confidence": 0.9,
                               "province": "punjab"})
    assert out["result_kind"] == "provisional"
    assert out["matched_lawyers"] and all(l["match_score"] is None for l in out["matched_lawyers"])

    weak = await cs._fetch_matched_lawyers(
        session, n=3, signals={"case_type": "civil", "case_type_confidence": 0.3,
                               "province": "punjab"})
    assert weak["result_kind"] == "unavailable" and weak["matched_lawyers"] == []
    assert await cs._fetch_matched_lawyers(session, n=3) == {
        "result_kind": "unavailable", "notice": "", "matched_lawyers": []}


# ── the match route: ownership, deleted and draft cases ──────────────────────

async def test_the_match_route_refuses_another_clients_case_and_names_draft_and_missing(lawyers):
    from fastapi import HTTPException
    from app.api.v1.routes import lawyers as route

    me = {"_id": "PS-CLIENT", "role": "client"}
    with pytest.raises(HTTPException) as other:
        await route.match_lawyers("PS-CASE-OTHER", top_n=5, current_user=me)
    assert other.value.status_code == 403

    with pytest.raises(HTTPException) as gone:
        await route.match_lawyers("PS-CASE-DELETED", top_n=5, current_user=me)
    assert gone.value.status_code == 404

    with pytest.raises(HTTPException) as draft:
        await route.match_lawyers("PS-CASE-DRAFT", top_n=5, current_user=me)
    assert draft.value.status_code == 422
    assert draft.value.detail["code"] == "case_draft"
    assert "Confirm it at the end of the intake" in draft.value.detail["message"]
