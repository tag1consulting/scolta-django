"""Amazee model-resolution self-heal coverage for scolta-django.

The Amazee provisioner stores credentials and resolves model names in two
steps. When the ``/model/info`` step fails, credentials are stored with no
resolved model: ``AutoProvisioner.ensure_ai_available()`` no-opped forever on
the stored creds, ``config_overrides()`` injected the Amazee key while
``ScoltaConfig`` fell back to the shipped dated default
(``claude-sonnet-4-5-20250929``), and the Amazee gateway rejects that dated
name with HTTP 400 — summarize silently returned nothing, expand ran
unexpanded.

``maybe_auto_provision()`` now passes scolta-python's ``has_resolved_models``
predicate (keyed off the models store, empty in the unresolved state — the
clean signal), so the library re-resolves against the already-stored key
(never a fresh trial). ``config_overrides()`` degrades (injects nothing) when
no model is resolved, so the dated default never reaches the gateway.
"""

import pytest

from scolta_django import conf
from scolta_django.amazee import DjangoConfigStorage, config_overrides, maybe_auto_provision


class ResolvingClient:
    """A client that resolves models but refuses to provision a new trial.

    Used to prove the self-heal re-resolves against the STORED key: if it tried
    to provision a fresh trial, provision_trial() would raise and fail the test.
    """

    def __init__(self, *args, **kwargs):
        pass

    def provision_trial(self, email=""):
        raise AssertionError("self-heal must not provision a new trial")

    def get_available_models(self, url, token):
        return [{"model_name": "claude-sonnet-4-6"}, {"model_name": "claude-haiku-4-5"}]


class FailingModelsClient:
    """A client whose /model/info yields nothing — resolution keeps failing."""

    def __init__(self, *args, **kwargs):
        pass

    def provision_trial(self, email=""):
        raise AssertionError("self-heal must not provision a new trial")

    def get_available_models(self, url, token):
        return []


# -- self-heal ----------------------------------------------------------------


@pytest.mark.django_db
def test_maybe_auto_provision_self_heals_unresolved_models(settings):
    # Half-provisioned: credentials stored, no resolved models.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    DjangoConfigStorage().store("stored-tok", "https://llm.example", "us")
    assert DjangoConfigStorage().stored_models() == {}

    # Not a fresh trial — a model-only heal that re-resolves against the
    # stored key (ResolvingClient.provision_trial would raise if called).
    provisioned = maybe_auto_provision(client=ResolvingClient())

    assert provisioned is False
    assert DjangoConfigStorage().stored_models() == {
        "ai_model": "claude-sonnet-4-6",
        "ai_expansion_model": "claude-haiku-4-5",
    }


@pytest.mark.django_db
def test_self_heal_then_config_uses_gateway(settings):
    # End to end: after the heal, config points the client at the gateway with
    # the resolved model — never the dated default.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    DjangoConfigStorage().store("stored-tok", "https://llm.example", "us")

    maybe_auto_provision(client=ResolvingClient())
    cfg = conf.scolta_config()

    assert cfg.ai_provider == "openai"
    assert cfg.ai_api_key == "stored-tok"
    assert cfg.ai_model == "claude-sonnet-4-6"


# -- degrade ------------------------------------------------------------------


@pytest.mark.django_db
def test_config_overrides_degrades_when_models_unresolved():
    # Credentials stored, model resolution still failing: config_overrides must
    # NOT inject the Amazee key, so the client degrades (no key -> HTTP 200)
    # rather than sending the gateway the dated default (HTTP 400).
    DjangoConfigStorage().store("stored-tok", "https://llm.example", "us")

    assert config_overrides({"ai_api_key": ""}) == {}


@pytest.mark.django_db
def test_scolta_config_degrades_without_resolved_model(settings):
    # The degrade observed through the built config: no Amazee key is applied,
    # and the provider is NOT switched to the openai/LiteLLM path. The dated
    # default never reaches the gateway because there is no key to call it with.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "anthropic", "ai_api_key": ""}
    DjangoConfigStorage().store("stored-tok", "https://llm.example", "us")

    cfg = conf.scolta_config()

    assert cfg.ai_api_key == ""
    assert cfg.ai_provider != "openai"


@pytest.mark.django_db
def test_self_heal_no_op_when_model_info_keeps_failing(settings):
    # Resolution still fails: the store stays empty (no partial/garbage write),
    # config_overrides keeps degrading, and no fresh trial is provisioned.
    settings.SCOLTA = {**settings.SCOLTA, "ai_provider": "amazee", "ai_api_key": ""}
    DjangoConfigStorage().store("stored-tok", "https://llm.example", "us")

    assert maybe_auto_provision(client=FailingModelsClient()) is False
    assert DjangoConfigStorage().stored_models() == {}
    assert config_overrides({"ai_api_key": ""}) == {}


# -- the predicate / wiring ---------------------------------------------------


def test_maybe_auto_provision_wires_has_resolved_models():
    import inspect

    from scolta_django import amazee

    src = inspect.getsource(amazee.maybe_auto_provision)
    assert "has_resolved_models=" in src
    assert 'stored_models().get("ai_model")' in src
