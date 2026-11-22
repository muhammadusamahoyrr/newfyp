"""No personal email in geocoding requests (audit 2026-11-22, low #7)."""
from app.core.config import settings
from app.utils import geocoding


def test_default_user_agent_has_no_contact(monkeypatch):
    monkeypatch.setattr(settings, "geocoding_contact", "")
    assert geocoding._user_agent() == "AttorneyAI/1.0"
    assert "@" not in geocoding._user_agent()


def test_a_configured_contact_is_included(monkeypatch):
    monkeypatch.setattr(settings, "geocoding_contact", "ops@example.org")
    assert geocoding._user_agent() == "AttorneyAI/1.0 (ops@example.org)"


def test_the_source_no_longer_hard_codes_an_email():
    import inspect
    assert "@gmail" not in inspect.getsource(geocoding)
