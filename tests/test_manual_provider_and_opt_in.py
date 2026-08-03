"""Provider selection is manual, and connecting Amazee.ai takes two actions.

The policy this pins:

- **No default provider.** Nothing selects one. While none is selected AI is off:
  search works, no provider is assumed, and Anthropic in particular is not
  silently assumed.
- **Amazee is never auto-enabled.** ``SCOLTA["ai_provider"] == "amazee"`` in
  Django settings is the manual opt-in — a developer wrote it down — and it is
  the only thing that permits :func:`maybe_auto_provision` to establish a
  connection. With the provider unset or set to anything else, no credential is
  provisioned and no outbound Amazee call is made on any request path. In the
  admin, "Try the demo" takes no email and "Enter your Amazee credentials" runs
  the email → code → region flow.
- **Provenance is recorded, not guessed.** Which action ran is written to the
  credential store when it runs.

The Amazee client used here fails the test if it is called at all, so an
unexpected outbound call is a hard failure naming the method rather than a
swallowed error.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.test import Client
from scolta.ai.amazee import AmazeeConnectionSource

from scolta_django.amazee import DjangoConfigStorage, maybe_auto_provision

ROOT = Path(__file__).resolve().parents[1]


class FailOnCallClient:
    """An Amazee client whose every method fails the test, recording it first."""

    def __init__(self):
        self.calls: list[str] = []

    def _fail(self, name):
        self.calls.append(name)
        raise AssertionError(f"no outbound Amazee call expected, got {name}")

    def provision_trial(self, email=""):
        self._fail("provision_trial")

    def get_available_models(self, url, token):
        self._fail("get_available_models")

    def request_verification_code(self, email):
        self._fail("request_verification_code")

    def sign_in(self, email, code):
        self._fail("sign_in")

    def create_private_key(self, token, region):
        self._fail("create_private_key")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user("scolta-optin-admin", password="pw", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    """A logged-in staff client — /health's full payload needs one."""
    c = Client()
    c.force_login(staff_user)
    return c


def _source(relative: str) -> str:
    return (ROOT / relative).read_text()


# -- Invariant A: no default provider -----------------------------------------


def test_no_surface_coalesces_an_empty_provider_to_anthropic():
    offenders = []
    for relative in (
        "src/scolta_django/conf.py",
        "src/scolta_django/amazee.py",
        "src/scolta_django/views.py",
    ):
        if '"anthropic"' in _source(relative) or "'anthropic'" in _source(relative):
            offenders.append(relative)

    assert offenders == [], (
        "These files name anthropic; an unselected provider must be reported as "
        f"empty, never substituted: {offenders}"
    )


@pytest.mark.django_db
def test_health_reports_ai_off_rather_than_assuming_anthropic(staff_client, settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "", "ai_api_key": ""}

    body = json.loads(staff_client.get("/api/scolta/v1/health").content)

    assert body["ai_provider"] == ""
    assert body["ai_provider_selected"] is False
    assert body["ai_configured"] is False
    assert body["ai_usable"] is False


@pytest.mark.django_db
def test_key_without_a_provider_is_still_ai_off(staff_client, settings):
    # The case a coalescing default used to hide: a key set before anybody chose
    # a provider looked like a working Anthropic install.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "", "ai_api_key": "sk-env"}

    body = json.loads(staff_client.get("/api/scolta/v1/health").content)

    assert body["ai_provider"] == ""
    assert body["ai_provider_selected"] is False
    assert body["ai_usable"] is False


# -- Invariant B: the opt-in gate ---------------------------------------------


@pytest.mark.django_db
def test_no_provision_and_no_call_when_no_provider_is_selected(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "", "ai_api_key": ""}
    client = FailOnCallClient()

    assert maybe_auto_provision(client=client) is False
    assert client.calls == []
    assert DjangoConfigStorage().load() is None


@pytest.mark.django_db
def test_no_provision_and_no_call_for_a_non_amazee_provider(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "anthropic", "ai_api_key": ""}
    client = FailOnCallClient()

    assert maybe_auto_provision(client=client) is False
    assert client.calls == []
    assert DjangoConfigStorage().load() is None


@pytest.mark.django_db
def test_an_explicit_key_suppresses_amazee_entirely(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": "sk-mine"}
    client = FailOnCallClient()

    assert maybe_auto_provision(client=client) is False
    assert client.calls == []
    assert DjangoConfigStorage().load() is None


@pytest.mark.django_db
def test_the_opt_in_establishes_the_demo_once(settings, fake_client_class):
    # A developer wrote ai_provider = "amazee" in settings. That is the manual
    # opt-in, and it is what permits this — the same act as clicking "Try the
    # demo" in an admin UI.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    client = fake_client_class()

    assert maybe_auto_provision(client=client) is True
    assert DjangoConfigStorage().load()["litellm_token"] == "tok-trial"

    # Idempotent: the store is no longer empty, so nothing is established again.
    trials_after_first = [c for c in client.calls if c[0] == "provision_trial"]
    assert maybe_auto_provision(client=client) is False
    assert [c for c in client.calls if c[0] == "provision_trial"] == trials_after_first


@pytest.mark.django_db
def test_the_demo_is_established_with_no_email(settings, fake_client_class):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    client = fake_client_class()

    maybe_auto_provision(client=client)

    # Trying the demo costs no input at all.
    assert ("provision_trial", "") in client.calls


# -- Provenance ---------------------------------------------------------------


@pytest.mark.django_db
def test_the_demo_records_demo_provenance(settings, fake_client_class):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}

    maybe_auto_provision(client=fake_client_class())

    assert DjangoConfigStorage().load_connection_source() is AmazeeConnectionSource.DEMO


@pytest.mark.django_db
def test_unrecorded_provenance_reads_as_not_recorded():
    # A connection made before the column existed has no recorded origin, and
    # must report none rather than a guess.
    storage = DjangoConfigStorage()
    storage.store("tok", "https://llm.example", "us-east")

    assert storage.load_connection_source() is None


@pytest.mark.django_db
def test_clearing_credentials_also_clears_provenance():
    storage = DjangoConfigStorage()
    storage.store("tok", "https://llm.example", "us-east")
    storage.store_connection_source(AmazeeConnectionSource.DEMO)

    storage.clear()

    assert storage.load() is None
    assert storage.load_connection_source() is None


# -- No stale wording ---------------------------------------------------------


def test_no_operator_facing_wording_claims_an_automatic_trial():
    offenders = []
    for path in list((ROOT / "src/scolta_django").rglob("*.py")) + list(
        (ROOT / "src/scolta_django/templates").rglob("*.html")
    ):
        text = path.read_text()
        for banned in ("auto-provisioned", "auto provisioned"):
            if banned in text.lower():
                offenders.append(f"{path.relative_to(ROOT)}: {banned}")

    assert offenders == [], (
        "No connection is provisioned automatically, so nothing may describe one:\n"
        + "\n".join(offenders)
    )


def test_the_admin_offers_both_actions_and_no_manual_key_field():
    template = _source("src/scolta_django/templates/scolta_django/amazee_settings.html")

    assert "Try the demo" in template
    assert "Enter your Amazee credentials" in template
    # Email-only, matching amazee.ai's own module.
    assert "never generate or paste an API key" in template
    assert 'id="amazee-token"' not in template
