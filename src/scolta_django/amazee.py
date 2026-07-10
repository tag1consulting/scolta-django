"""Amazee.ai integration for Django: model-backed credential storage,
auto-provisioning, and config overrides.

When Amazee credentials are stored (and no explicit ai_api_key is set), the
resolved config points the OpenAI-compatible AiClient at the LiteLLM endpoint.
"""

from __future__ import annotations

import logging

from scolta.ai.amazee import AutoProvisioner, ConfigStorage, KeyExpiryRecovery

from . import conf
from .models import ScoltaAmazeeConfig

_logger = logging.getLogger("scolta_django.amazee")


class DjangoConfigStorage(ConfigStorage):
    """Stores Amazee credentials in the ScoltaAmazeeConfig singleton row."""

    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None:
        ScoltaAmazeeConfig.objects.update_or_create(
            pk=1,
            defaults={
                "litellm_token": litellm_token,
                "litellm_api_url": litellm_api_url,
                "region": region,
            },
        )

    def load(self) -> dict | None:
        row = ScoltaAmazeeConfig.objects.filter(pk=1).first()
        if row is None or not row.litellm_token:
            return None
        return {
            "litellm_token": row.litellm_token,
            "litellm_api_url": row.litellm_api_url,
            "region": row.region,
        }

    def clear(self) -> None:
        ScoltaAmazeeConfig.objects.filter(pk=1).delete()

    def store_models(self, ai_model: str, ai_expansion_model: str) -> None:
        ScoltaAmazeeConfig.objects.update_or_create(
            pk=1, defaults={"ai_model": ai_model, "ai_expansion_model": ai_expansion_model}
        )

    def stored_models(self) -> dict:
        row = ScoltaAmazeeConfig.objects.filter(pk=1).first()
        if row is None:
            return {}
        out = {}
        if row.ai_model:
            out["ai_model"] = row.ai_model
        if row.ai_expansion_model:
            out["ai_expansion_model"] = row.ai_expansion_model
        return out


def config_overrides(settings_dict: dict) -> dict:
    """Amazee-derived overrides for ScoltaConfig — empty unless creds are stored
    and no explicit key is configured (an explicit key always wins)."""
    if settings_dict.get("ai_api_key"):
        return {}
    try:
        storage = DjangoConfigStorage()
        creds = storage.load()
    except Exception:
        return {}
    if not creds:
        return {}
    models = storage.stored_models()
    if not models.get("ai_model"):
        # Half-provisioned: credentials are stored but model resolution never
        # succeeded (the provision's /model/info step failed), so no resolved
        # model is in the store. Injecting the Amazee key here would leave
        # ScoltaConfig on the dated default (claude-sonnet-4-5-20250929), which
        # the Amazee LiteLLM gateway rejects with HTTP 400, breaking AI
        # permanently and silently. Inject nothing instead: the client stays
        # unconfigured and the endpoint degrades to an unexpanded/no-summary
        # HTTP 200 (the same path as no credentials), never a 400. The state
        # self-heals once maybe_auto_provision() re-resolves against the stored
        # key (see has_resolved_models). Mirrors scolta-node's
        # AmazeeAiService.buildClient().
        return {}
    overrides = {
        "ai_provider": "openai",
        "ai_api_key": creds["litellm_token"],
        "ai_base_url": creds["litellm_api_url"],
    }
    overrides.update(models)
    return overrides


def amazee_active(settings_dict: dict) -> bool:
    """Whether the Amazee.ai gateway is the active AI path.

    True when credentials are stored and no explicit ``ai_api_key`` is set (an
    explicit key always wins and is never touched by this subsystem). This is
    the same condition under which :func:`config_overrides` points the client at
    the LiteLLM endpoint, so it also gates the credential re-authentication
    wiring below.
    """
    if settings_dict.get("ai_api_key"):
        return False
    try:
        return DjangoConfigStorage().load() is not None
    except Exception:
        return False


def build_key_expiry_recovery() -> KeyExpiryRecovery:
    """Construct the KeyExpiryRecovery helper backed by the adapter's stores.

    Policy: the stored Amazee.ai credentials are only ever re-established by an
    operator through the email-verification flow — this subsystem detects when
    they stop being accepted and routes the operator to reconnect, it never
    re-establishes the connection on its own. The cache is the same one the AI
    endpoint, ``/health`` and the settings page use, so the degraded state and
    the re-authentication prompt stay consistent across all of them.
    """
    from .cache import DjangoCacheDriver

    return KeyExpiryRecovery(DjangoConfigStorage(), DjangoCacheDriver(), _logger)


def maybe_auto_provision(client=None) -> bool:
    """Auto-provision a free Amazee trial on first use when provider == 'amazee'
    and nothing is configured yet. No-op otherwise. Returns True if provisioned."""
    if conf.get("ai_provider") != "amazee":
        return False
    storage = DjangoConfigStorage()

    def _save_models(ai_model: str, ai_expansion_model: str) -> None:
        storage.store_models(ai_model, ai_expansion_model)

    return AutoProvisioner.ensure_ai_available(
        storage,
        has_explicit_api_key=bool(conf.get("ai_api_key")),
        on_models_resolved=_save_models,
        client=client,
        # Report whether models are already resolved. When credentials are
        # stored but resolution previously failed, the models store is empty
        # (the clean signal), so this returns False and ensure_ai_available()
        # re-resolves against the ALREADY-STORED key — self-healing the
        # half-provisioned state — instead of no-opping forever and leaving
        # config_overrides() to strand the dated default at the gateway.
        has_resolved_models=lambda: bool(storage.stored_models().get("ai_model")),
    )
