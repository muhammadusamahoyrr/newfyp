"""GET /lawyers/counts: every count the client Lawyers page shows, in one request.

The page used to send a 1-row search per practice-area chip plus two totals —
nine round trips on every open. These tests pin that the one request returns
the same numbers: each area count under the page's other filters, the totals
for the whole directory, and the SAME filter the list itself uses.
"""
import pytest

from app.repositories.user_repo import UserRepository


@pytest.mark.asyncio
async def test_counts_apply_page_filters_to_areas_but_not_to_totals(monkeypatch):
    from app.services import lawyer_service

    calls = []

    async def fake_count(**filters):
        calls.append(filters)
        return len(calls)

    monkeypatch.setattr(lawyer_service.user_repo, "count_lawyers", fake_count)
    out = await lawyer_service.directory_counts(
        province="punjab", min_rating=4.0, availability=True,
        specializations=["family", "criminal", "family"],   # duplicate collapses
    )

    assert set(out) == {"by_specialization", "total", "accepting"}
    assert list(out["by_specialization"]) == ["family", "criminal"]
    area_calls = calls[:2]
    for c in area_calls:
        assert c["province"] == "punjab" and c["min_rating"] == 4.0 and c["availability"] is True
    assert [c["specialization"] for c in area_calls] == ["family", "criminal"]
    assert calls[2] == {}                       # whole directory
    assert calls[3] == {"availability": True}   # accepting clients


def test_list_and_counts_share_one_filter():
    """A chip's number must equal what clicking it lists: same filter builder."""
    f = UserRepository.lawyer_filter(province="sindh", min_rating=3.5,
                                     availability=False, specialization="property")
    assert f["role"] == "lawyer" and f["is_active"] is True
    assert f["lawyer_profile.kyc_verified"] is True
    assert f["province"] == "sindh"
    assert f["lawyer_profile.rating"] == {"$gte": 3.5}
    assert f["lawyer_profile.availability"] is False
    assert f["lawyer_profile.specializations"] == "property"
    # min_rating 0 adds no clause: unrated lawyers must stay listed and counted.
    assert "lawyer_profile.rating" not in UserRepository.lawyer_filter()


@pytest.mark.asyncio
async def test_unknown_practice_area_is_refused():
    from fastapi import HTTPException
    from app.api.v1.routes import lawyers as routes

    with pytest.raises(HTTPException) as err:
        await routes.lawyer_directory_counts(
            province=None, min_rating=0.0, availability=None,
            specialization=["family", "$where"], current_user={"role": "client"},
        )
    assert err.value.status_code == 422
