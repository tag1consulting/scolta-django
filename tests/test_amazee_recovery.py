"""Amazee.ai credential re-authentication surfacing for scolta-django.

Amazee.ai credentials are revoked server-side at the end of their lifecycle
without any advance signal, so the only reliable indication is the auth failure
the LiteLLM proxy returns on the next inference call. scolta's KeyExpiryRecovery
records that failure (so ``/health`` reports AI degraded) and sets a persistent
marker (so admin UIs prompt the operator to reconnect). It never re-establishes
the connection on its own — reconnection is always operator-initiated through
the email-verification flow.

These tests cover the adapter's half: wiring recovery into the AI call path,
reflecting the state in ``/health`` and the admin surfaces, and clearing the
prompt once fresh credentials are stored.
"""

import json

import pytest
from django.core.cache import cache
from django.test import Client
from scolta.ai.amazee import KeyExpiryRecovery
from scolta.exceptions import ApiKeyInvalidException

from scolta_django import conf
from scolta_django.ai import DjangoAiService
from scolta_django.amazee import (
    DjangoConfigStorage,
    amazee_active,
    build_key_expiry_recovery,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    # The re-authentication markers live in Django's cache under fixed keys;
    # LocMemCache is process-global, so clear it around every test.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user("scolta-admin", password="pw", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    c = Client()
    c.force_login(staff_user)
    return c


def _store_credentials():
    storage = DjangoConfigStorage()
    storage.store("tok", "https://llm.example", "us-east")
    storage.store_models("claude-sonnet-4-6", "claude-haiku-4-5")


class _FailingClient:
    """An AiClient stand-in whose calls fail as if the stored key is rejected."""

    def message(self, *args, **kwargs):
        raise ApiKeyInvalidException("authentication error: invalid_api_key")

    def conversation(self, *args, **kwargs):
        raise ApiKeyInvalidException("authentication error: invalid_api_key")


# -- active-path predicate ----------------------------------------------------


@pytest.mark.django_db
def test_amazee_active_only_when_credentials_and_no_explicit_key():
    assert amazee_active({"ai_api_key": ""}) is False
    _store_credentials()
    assert amazee_active({"ai_api_key": ""}) is True
    # An explicit key always wins and is never touched by this subsystem.
    assert amazee_active({"ai_api_key": "sk-mine"}) is False


# -- detection: rejected credentials degrade AND raise the reconnect signal ---


@pytest.mark.django_db
def test_rejected_credentials_degrade_and_prompt_for_upgrade(monkeypatch):
    """A rejected-credential failure on the AI path is not swallowed: it marks
    AI degraded for health AND sets the persistent reconnect prompt, while the
    original failure still propagates (the caller degrades gracefully)."""
    _store_credentials()
    svc = DjangoAiService(conf.scolta_config())
    svc.set_key_expiry_recovery(build_key_expiry_recovery())
    monkeypatch.setattr(svc, "_create_client", lambda: _FailingClient())

    with pytest.raises(ApiKeyInvalidException):
        svc.message("system", "user")

    recovery = build_key_expiry_recovery()
    assert recovery.is_auth_failing() is True
    assert recovery.is_upgrade_needed() is True


@pytest.mark.django_db
def test_unwired_service_does_not_flag_upgrade(monkeypatch):
    """Without recovery wired (e.g. an explicit user key), a failure propagates
    unchanged and no reconnect prompt is raised."""
    _store_credentials()
    svc = DjangoAiService(conf.scolta_config())
    monkeypatch.setattr(svc, "_create_client", lambda: _FailingClient())

    with pytest.raises(ApiKeyInvalidException):
        svc.message("system", "user")

    assert build_key_expiry_recovery().is_upgrade_needed() is False


# -- end-to-end: the endpoint wires recovery ----------------------------------


@pytest.mark.django_db
def test_summarize_endpoint_degrades_and_records_state(monkeypatch, settings):
    """Through the real endpoint (_make_handler wires recovery on the Amazee
    path): a rejected-credential failure degrades to an empty summary (HTTP 200,
    not a 500) yet is recorded so health and the admin prompt reflect it."""
    settings.SCOLTA = {**settings.SCOLTA, "cache_ttl": 0}
    _store_credentials()
    monkeypatch.setattr(DjangoAiService, "_create_client", lambda self: _FailingClient())

    resp = Client().post(
        "/api/scolta/v1/summarize",
        data=json.dumps({"query": "hello", "context": "some context"}),
        content_type="application/json",
    )
    assert resp.status_code == 200  # degraded, not swallowed into a 500

    recovery = build_key_expiry_recovery()
    assert recovery.is_auth_failing() is True
    assert recovery.is_upgrade_needed() is True


# -- health reflects the credential state -------------------------------------


@pytest.mark.django_db
def test_health_reports_degraded_when_credentials_rejected(staff_client):
    _store_credentials()
    # Record the auth-failure marker as the AI path would on a rejected call.
    build_key_expiry_recovery().record_auth_failure()

    body = json.loads(staff_client.get("/api/scolta/v1/health").content)
    assert body["status"] == "degraded"
    assert body["ai_configured"] is True
    assert body["ai_usable"] is False
    assert body["ai_auth_failing"] is True


@pytest.mark.django_db
def test_health_usable_when_credentials_accepted(staff_client, settings):
    # A key alone is not a working configuration: there is no default provider,
    # so a site with a key and no provider selected still has AI off. This case
    # is about the auth-failure marker, not provider selection, so it selects
    # one.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "anthropic", "ai_api_key": "sk-mine"}
    body = json.loads(staff_client.get("/api/scolta/v1/health").content)
    assert body["ai_configured"] is True
    assert body["ai_usable"] is True
    assert body["ai_auth_failing"] is False


# -- settings page banner -----------------------------------------------------


@pytest.mark.django_db
def test_settings_page_shows_reconnect_banner_when_upgrade_needed(staff_client):
    _store_credentials()
    build_key_expiry_recovery().flag_upgrade_needed()

    html = staff_client.get("/scolta/amazee/").content.decode()
    assert "needs to be re-authenticated" in html
    assert "Continue with Amazee.ai" in html


@pytest.mark.django_db
def test_settings_page_no_banner_when_not_needed(staff_client):
    _store_credentials()
    html = staff_client.get("/scolta/amazee/").content.decode()
    assert "needs to be re-authenticated" not in html


# -- reconnect clears the prompt ----------------------------------------------


@pytest.mark.django_db
def test_reconnect_via_upgrade_clears_prompt(staff_client, monkeypatch):
    from scolta.ai.amazee import UpgradeResult

    class FakeClient:
        def create_private_key(self, session_token, region_id):
            return UpgradeResult.make_success("tok-fresh", "https://llm.example", region_id)

    monkeypatch.setattr("scolta_django.amazee_views._client", lambda: FakeClient())
    _store_credentials()
    build_key_expiry_recovery().flag_upgrade_needed()
    assert build_key_expiry_recovery().is_upgrade_needed() is True

    resp = staff_client.post(
        "/scolta/amazee/upgrade",
        data=json.dumps({"session_token": "s", "region_id": "eu-west"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert build_key_expiry_recovery().is_upgrade_needed() is False


@pytest.mark.django_db
def test_disconnect_clears_prompt(staff_client):
    _store_credentials()
    build_key_expiry_recovery().flag_upgrade_needed()
    staff_client.post("/scolta/amazee/disconnect", content_type="application/json")
    assert build_key_expiry_recovery().is_upgrade_needed() is False


# -- management command reports the state -------------------------------------


@pytest.mark.django_db
def test_management_command_reports_reauthentication_state(capsys):
    from django.core.management import call_command

    _store_credentials()
    build_key_expiry_recovery().flag_upgrade_needed()
    call_command("scolta_amazee_provision")  # creds present, no --force
    out = capsys.readouterr().out
    assert "re-authentication" in out
    assert "settings page" in out


# -- marker key parity --------------------------------------------------------


def test_recovery_marker_keys_match_health():
    # The adapter reads/writes the same keys scolta's HealthChecker reads.
    assert KeyExpiryRecovery.CACHE_KEY_AUTH_FAILURE == "scolta_amazee_auth_failure"
    assert KeyExpiryRecovery.CACHE_KEY_UPGRADE_NEEDED == "scolta_amazee_upgrade_needed"
