"""scolta-django Amazee.ai upgrade-UI endpoint tests (mocked AmazeeClient).

Drives the JSON OTP-upgrade flow through Django's test client with the
AmazeeClient monkeypatched at ``amazee_views._client`` so no network is hit.
"""

import json

import pytest
from scolta.ai.amazee import AmazeeApiException, UpgradeResult

from scolta_django.amazee import DjangoConfigStorage


class FakeAmazeeClient:
    """Records calls and returns canned responses for every endpoint."""

    def __init__(self, *, raise_on=None):
        self.calls = []
        self._raise_on = raise_on

    def _maybe_raise(self, name):
        if self._raise_on == name:
            raise AmazeeApiException(f"boom in {name}")

    def provision_trial(self, email=""):
        self.calls.append(("provision_trial", email))
        self._maybe_raise("provision_trial")
        from scolta.ai.amazee import ProvisioningResult

        return ProvisioningResult.make_success("tok-trial", "https://llm.example", "us-east")

    def get_available_models(self, url, token):
        self.calls.append(("get_available_models", url, token))
        return [{"model_name": "claude-sonnet-4-6"}, {"model_name": "claude-haiku-4-5"}]

    def request_verification_code(self, email):
        self.calls.append(("request_verification_code", email))
        self._maybe_raise("request_verification_code")

    def sign_in(self, email, code):
        self.calls.append(("sign_in", email, code))
        self._maybe_raise("sign_in")
        return "session-tok-xyz"

    def list_regions(self, session_token):
        self.calls.append(("list_regions", session_token))
        self._maybe_raise("list_regions")
        return [{"id": "us-east", "name": "US East"}, {"id": "eu-west", "name": "EU West"}]

    def create_private_key(self, session_token, region_id):
        self.calls.append(("create_private_key", session_token, region_id))
        self._maybe_raise("create_private_key")
        return UpgradeResult.make_success("tok-upgraded", "https://llm.example", region_id)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeAmazeeClient()
    monkeypatch.setattr("scolta_django.amazee_views._client", lambda: client)
    return client


def _json(response):
    return json.loads(response.content)


# -- status -------------------------------------------------------------------


@pytest.mark.django_db
def test_status_unprovisioned(client):
    resp = client.get("/scolta/amazee/status")
    assert resp.status_code == 200
    body = _json(resp)
    assert body["provisioned"] is False
    assert body["region"] is None
    assert body["ai_model"] is None


@pytest.mark.django_db
def test_status_provisioned(client):
    storage = DjangoConfigStorage()
    storage.store("tok", "https://llm.example", "us-east")
    storage.store_models("claude-sonnet-4-6", "claude-haiku-4-5")
    body = _json(client.get("/scolta/amazee/status"))
    assert body["provisioned"] is True
    assert body["region"] == "us-east"
    assert body["ai_model"] == "claude-sonnet-4-6"
    assert body["ai_expansion_model"] == "claude-haiku-4-5"


def test_status_rejects_post(client):
    assert client.post("/scolta/amazee/status").status_code == 405


# -- provision (free trial) ---------------------------------------------------


@pytest.mark.django_db
def test_provision_stores_credentials_and_models(client, fake_client):
    resp = client.post(
        "/scolta/amazee/provision",
        data=json.dumps({"email": "a@b.com"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = _json(resp)
    assert body["ok"] is True
    assert body["region"] == "us-east"
    creds = DjangoConfigStorage().load()
    assert creds["litellm_token"] == "tok-trial"
    assert DjangoConfigStorage().stored_models()["ai_model"] == "claude-sonnet-4-6"
    assert ("provision_trial", "a@b.com") in fake_client.calls


@pytest.mark.django_db
def test_provision_without_body(client, fake_client):
    resp = client.post("/scolta/amazee/provision", content_type="application/json")
    assert resp.status_code == 200
    assert ("provision_trial", "") in fake_client.calls


@pytest.mark.django_db
def test_provision_api_error_is_502(client, monkeypatch):
    monkeypatch.setattr(
        "scolta_django.amazee_views._client", lambda: FakeAmazeeClient(raise_on="provision_trial")
    )
    resp = client.post("/scolta/amazee/provision", content_type="application/json")
    assert resp.status_code == 502
    assert "boom" in _json(resp)["error"]


def test_provision_rejects_get(client):
    assert client.get("/scolta/amazee/provision").status_code == 405


# -- request verification code ------------------------------------------------


@pytest.mark.django_db
def test_request_code(client, fake_client):
    resp = client.post(
        "/scolta/amazee/request-code",
        data=json.dumps({"email": "a@b.com"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert _json(resp)["ok"] is True
    assert ("request_verification_code", "a@b.com") in fake_client.calls


@pytest.mark.django_db
def test_request_code_requires_email(client, fake_client):
    resp = client.post(
        "/scolta/amazee/request-code", data=json.dumps({}), content_type="application/json"
    )
    assert resp.status_code == 400
    assert "email" in _json(resp)["error"]


# -- sign in ------------------------------------------------------------------


@pytest.mark.django_db
def test_sign_in_returns_session_token(client, fake_client):
    resp = client.post(
        "/scolta/amazee/sign-in",
        data=json.dumps({"email": "a@b.com", "code": "123456"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert _json(resp)["session_token"] == "session-tok-xyz"


@pytest.mark.django_db
def test_sign_in_requires_email_and_code(client, fake_client):
    resp = client.post(
        "/scolta/amazee/sign-in",
        data=json.dumps({"email": "a@b.com"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


# -- regions ------------------------------------------------------------------


@pytest.mark.django_db
def test_regions_lists(client, fake_client):
    resp = client.post(
        "/scolta/amazee/regions",
        data=json.dumps({"session_token": "session-tok-xyz"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    regions = _json(resp)["regions"]
    assert {r["id"] for r in regions} == {"us-east", "eu-west"}


@pytest.mark.django_db
def test_regions_requires_session_token(client, fake_client):
    resp = client.post("/scolta/amazee/regions", data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400


# -- upgrade ------------------------------------------------------------------


@pytest.mark.django_db
def test_upgrade_stores_private_key(client, fake_client):
    resp = client.post(
        "/scolta/amazee/upgrade",
        data=json.dumps({"session_token": "session-tok-xyz", "region_id": "eu-west"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = _json(resp)
    assert body["ok"] is True
    assert body["region"] == "eu-west"
    creds = DjangoConfigStorage().load()
    assert creds["litellm_token"] == "tok-upgraded"
    assert creds["region"] == "eu-west"


@pytest.mark.django_db
def test_upgrade_requires_fields(client, fake_client):
    resp = client.post(
        "/scolta/amazee/upgrade",
        data=json.dumps({"session_token": "session-tok-xyz"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_upgrade_api_error_is_502(client, monkeypatch):
    monkeypatch.setattr(
        "scolta_django.amazee_views._client",
        lambda: FakeAmazeeClient(raise_on="create_private_key"),
    )
    resp = client.post(
        "/scolta/amazee/upgrade",
        data=json.dumps({"session_token": "s", "region_id": "eu-west"}),
        content_type="application/json",
    )
    assert resp.status_code == 502


# -- disconnect ---------------------------------------------------------------


@pytest.mark.django_db
def test_disconnect_clears_credentials(client):
    DjangoConfigStorage().store("tok", "https://llm.example", "us-east")
    resp = client.post("/scolta/amazee/disconnect", content_type="application/json")
    assert resp.status_code == 200
    assert _json(resp)["ok"] is True
    assert DjangoConfigStorage().load() is None


def test_disconnect_rejects_get(client):
    assert client.get("/scolta/amazee/disconnect").status_code == 405


# -- settings page (rendered UI) ----------------------------------------------


@pytest.mark.django_db
def test_settings_page_renders(client):
    resp = client.get("/scolta/amazee/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "amazeeSettings(" in html
    assert "amazee-routes" in html
    # The JSON route map must be embedded for the Alpine component.
    assert "/scolta/amazee/provision" in html


@pytest.mark.django_db
def test_settings_page_connected_when_provisioned(client):
    DjangoConfigStorage().store("tok", "https://llm.example", "us-east")
    resp = client.get("/scolta/amazee/")
    assert "amazeeSettings('connected'" in resp.content.decode()


# -- full flow ----------------------------------------------------------------


@pytest.mark.django_db
def test_full_upgrade_flow(client, fake_client):
    assert client.post(
        "/scolta/amazee/request-code",
        data=json.dumps({"email": "a@b.com"}),
        content_type="application/json",
    ).status_code == 200

    signin = _json(client.post(
        "/scolta/amazee/sign-in",
        data=json.dumps({"email": "a@b.com", "code": "123456"}),
        content_type="application/json",
    ))
    token = signin["session_token"]

    regions = _json(client.post(
        "/scolta/amazee/regions",
        data=json.dumps({"session_token": token}),
        content_type="application/json",
    ))["regions"]
    region_id = regions[0]["id"]

    upgrade = _json(client.post(
        "/scolta/amazee/upgrade",
        data=json.dumps({"session_token": token, "region_id": region_id}),
        content_type="application/json",
    ))
    assert upgrade["ok"] is True
    assert DjangoConfigStorage().load()["litellm_token"] == "tok-upgraded"
