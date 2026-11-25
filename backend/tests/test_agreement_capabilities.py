"""GET /agreements/capabilities: the ONE place the UI learns whether the client
agreement builder is on (2026-11-25). It used to be a frontend build variable
too, and the two could disagree."""
import pytest


@pytest.mark.parametrize("on", [True, False])
async def test_capabilities_reports_the_server_setting(monkeypatch, on):
    from app.api.v1.routes import agreements
    from app.core.config import settings
    monkeypatch.setattr(settings, "agreements_diy_builder_enabled", on)
    assert await agreements.agreement_capabilities({"_id": "U1"}) == {"diy_builder": on}


def test_capabilities_is_declared_before_the_agreement_id_route():
    """Otherwise /agreements/capabilities would be read as agreement id
    "capabilities" and answer 404."""
    from app.api.v1.routes import agreements
    paths = [r.path for r in agreements.router.routes if "GET" in getattr(r, "methods", set())]
    assert paths.index("/agreements/capabilities" if paths[0].startswith("/agreements") else "/capabilities") \
        < paths.index("/agreements/{agreement_id}" if paths[0].startswith("/agreements") else "/{agreement_id}")
