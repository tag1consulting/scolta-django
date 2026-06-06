"""scolta-django Amazee.ai wiring tests (mocked AmazeeClient)."""

import pytest
from scolta.ai.amazee import AmazeeBudgetExceededException, ProvisioningResult

from scolta_django import conf
from scolta_django.ai import DjangoAiService
from scolta_django.amazee import DjangoConfigStorage, config_overrides, maybe_auto_provision
from scolta_django.models import ScoltaAmazeeConfig


class FakeAmazeeClient:
    def __init__(self, *args, **kwargs):
        pass

    def provision_trial(self, email=""):
        return ProvisioningResult.make_success("tok-123", "https://llm.example", "us-east")

    def get_available_models(self, url, token):
        return [{"model_name": "claude-sonnet-4-6"}, {"model_name": "claude-haiku-4-5"}]


# -- storage ------------------------------------------------------------------


@pytest.mark.django_db
def test_config_storage_round_trip():
    s = DjangoConfigStorage()
    assert s.load() is None
    s.store("tok", "https://llm.x", "us")
    assert s.load() == {"litellm_token": "tok", "litellm_api_url": "https://llm.x", "region": "us"}
    s.store_models("claude-sonnet-4-6", "claude-haiku-4-5")
    assert s.stored_models() == {"ai_model": "claude-sonnet-4-6", "ai_expansion_model": "claude-haiku-4-5"}
    s.clear()
    assert s.load() is None
    assert ScoltaAmazeeConfig.objects.count() == 0


# -- config overrides ---------------------------------------------------------


@pytest.mark.django_db
def test_config_overrides_when_creds_stored():
    DjangoConfigStorage().store("tok-abc", "https://llm.example", "us")
    DjangoConfigStorage().store_models("claude-sonnet-4-6", "claude-haiku-4-5")
    ov = config_overrides({"ai_api_key": ""})
    assert ov["ai_provider"] == "openai"
    assert ov["ai_api_key"] == "tok-abc"
    assert ov["ai_base_url"] == "https://llm.example"
    assert ov["ai_model"] == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_config_overrides_explicit_key_wins():
    DjangoConfigStorage().store("tok-abc", "https://llm.example", "us")
    assert config_overrides({"ai_api_key": "sk-mine"}) == {}


@pytest.mark.django_db
def test_scolta_config_applies_amazee(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_api_key": ""}
    DjangoConfigStorage().store("tok-xyz", "https://llm.example", "us")
    cfg = conf.scolta_config()
    assert cfg.ai_provider == "openai"
    assert cfg.ai_api_key == "tok-xyz"
    assert cfg.ai_base_url == "https://llm.example"
    # AiClient uses these as the OpenAI-compatible endpoint.
    client_cfg = cfg.to_ai_client_config()
    assert client_cfg["provider"] == "openai"
    assert client_cfg["base_url"] == "https://llm.example"


# -- provision command --------------------------------------------------------


@pytest.mark.django_db
def test_provision_command(monkeypatch):
    monkeypatch.setattr(
        "scolta_django.management.commands.scolta_amazee_provision.AmazeeClient", FakeAmazeeClient
    )
    from django.core.management import call_command

    call_command("scolta_amazee_provision", "--email", "a@b.com")
    creds = DjangoConfigStorage().load()
    assert creds["litellm_token"] == "tok-123"
    assert DjangoConfigStorage().stored_models()["ai_model"] == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_provision_command_skips_when_present(monkeypatch):
    DjangoConfigStorage().store("existing", "https://x", "us")
    monkeypatch.setattr(
        "scolta_django.management.commands.scolta_amazee_provision.AmazeeClient", FakeAmazeeClient
    )
    from django.core.management import call_command

    call_command("scolta_amazee_provision")  # no --force
    assert DjangoConfigStorage().load()["litellm_token"] == "existing"  # unchanged


# -- auto-provision -----------------------------------------------------------


@pytest.mark.django_db
def test_maybe_auto_provision_noop_when_not_amazee(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "anthropic"}
    assert maybe_auto_provision(client=FakeAmazeeClient()) is False


@pytest.mark.django_db
def test_maybe_auto_provision_provisions_for_amazee(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    assert maybe_auto_provision(client=FakeAmazeeClient()) is True
    assert DjangoConfigStorage().load()["litellm_token"] == "tok-123"


@pytest.mark.django_db
def test_maybe_auto_provision_skips_with_explicit_key(settings):
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": "sk-mine"}
    assert maybe_auto_provision(client=FakeAmazeeClient()) is False


# -- budget hook --------------------------------------------------------------


def test_django_ai_service_budget_hook_converts():
    svc = DjangoAiService.__new__(DjangoAiService)
    with pytest.raises(AmazeeBudgetExceededException):
        svc._handle_possible_budget_exception(RuntimeError("Budget has been exceeded!"))


def test_django_ai_service_budget_hook_ignores_other():
    svc = DjangoAiService.__new__(DjangoAiService)
    # Non-budget errors pass through (no exception raised by the hook).
    svc._handle_possible_budget_exception(RuntimeError("network down"))
