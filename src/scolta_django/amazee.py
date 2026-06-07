"""Amazee.ai integration for Django: model-backed credential storage,
auto-provisioning, and config overrides.

When Amazee credentials are stored (and no explicit ai_api_key is set), the
resolved config points the OpenAI-compatible AiClient at the LiteLLM endpoint.
"""

from __future__ import annotations

from scolta.ai.amazee import AutoProvisioner, ConfigStorage

from . import conf
from .models import ScoltaAmazeeConfig


class DjangoConfigStorage(ConfigStorage):
    """Stores Amazee credentials in the ScoltaAmazeeConfig singleton row."""

    def store(self, litellm_token: str, litellm_api_url: str, region: str) -> None:
        ScoltaAmazeeConfig.objects.update_or_create(
            pk=1,
            defaults={"litellm_token": litellm_token, "litellm_api_url": litellm_api_url, "region": region},
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
    except Exception:  # noqa: BLE001 - table may not exist yet
        return {}
    if not creds:
        return {}
    overrides = {
        "ai_provider": "openai",
        "ai_api_key": creds["litellm_token"],
        "ai_base_url": creds["litellm_api_url"],
    }
    overrides.update(storage.stored_models())
    return overrides


def maybe_auto_provision(client=None) -> bool:
    """Auto-provision a free Amazee trial on first use when NO API key is
    configured — regardless of the ``ai_provider`` setting. This mirrors the PHP
    adapters (e.g. ScoltaAiService::createClient lazy-provisions whenever
    getApiKeySource() === 'none'): a site with no key gets the free Amazee trial
    automatically, while an explicit key always wins. Returns True if a trial was
    provisioned on this call. No-op (returns False) when an explicit key exists;
    ``ensure_ai_available`` handles the already-provisioned and failure cases
    (graceful degrade)."""
    if conf.get("ai_api_key"):
        return False
    storage = DjangoConfigStorage()

    def _save_models(ai_model: str, ai_expansion_model: str) -> None:
        storage.store_models(ai_model, ai_expansion_model)

    return AutoProvisioner.ensure_ai_available(
        storage,
        has_explicit_api_key=bool(conf.get("ai_api_key")),
        on_models_resolved=_save_models,
        client=client,
    )
