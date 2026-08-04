"""Amazee.ai integration for Django: model-backed credential storage,
first-use provisioning under the provider gate, and config overrides.

When Amazee credentials are stored (and no explicit ai_api_key is set), the
resolved config points the OpenAI-compatible AiClient at the LiteLLM endpoint.

**Nothing here connects a site that did not opt in.** ``SCOLTA["ai_provider"] =
"amazee"`` in settings is the manual opt-in — a developer wrote it down, the
same act as clicking "Try the demo" in the Wagtail admin — and it is the gate on
:func:`maybe_auto_provision`. With the provider unset or set to anything else,
no credential is provisioned and no outbound Amazee call is made on any request
path.
"""

from __future__ import annotations

import logging

from scolta.ai.amazee import (
    AmazeeApiException,
    AmazeeClient,
    AmazeeConnectionSource,
    AmazeeModelResolver,
    AmazeeTrialProvisioner,
    AutoProvisioner,
    KeyExpiryRecovery,
    ProvenanceAwareConfigStorage,
)

from . import conf
from .models import ScoltaAmazeeConfig

_logger = logging.getLogger("scolta_django.amazee")


class DjangoConfigStorage(ProvenanceAwareConfigStorage):
    """Stores Amazee credentials in the ScoltaAmazeeConfig singleton row.

    Provenance-aware: it also records which operator action established the
    connection, so no surface has to guess between the free demo and an
    operator's own amazee.ai account.
    """

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
        # Deleting the row drops the recorded connection source with the
        # credentials it describes. Left behind, it would be paired with
        # whatever connection comes next, which is a guess wearing a recorded
        # fact's clothes.
        ScoltaAmazeeConfig.objects.filter(pk=1).delete()

    def store_connection_source(self, source: AmazeeConnectionSource) -> None:
        ScoltaAmazeeConfig.objects.update_or_create(
            pk=1, defaults={"connection_source": source.value}
        )

    def load_connection_source(self) -> AmazeeConnectionSource | None:
        row = ScoltaAmazeeConfig.objects.filter(pk=1).first()
        stored = getattr(row, "connection_source", "") if row is not None else ""
        if not stored:
            # The right answer for a connection made before provenance was
            # recorded. It must read as "not recorded", never as a default.
            return None
        try:
            return AmazeeConnectionSource(stored)
        except ValueError:
            return None

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
    """Establish the free Amazee demo on first use, under the provider gate.

    **The gate is the opt-in.** ``SCOLTA["ai_provider"] == "amazee"`` in Django
    settings is a developer's explicit choice, and it is the only thing that
    permits a connection to be established here. With the provider unset or set
    to anything else this returns immediately, having read nothing and called
    nothing — so no request path can enrol a site that did not opt in.

    Idempotent: only an empty credential store establishes a connection, so
    every later request reuses what is stored. An explicit ``ai_api_key`` wins
    outright and suppresses Amazee entirely.

    The establishing call is explicit. It used to be delegated to
    :meth:`AutoProvisioner.ensure_ai_available`, which minted a trial for any
    caller that reached it with an empty store — a contract removed upstream,
    because anything else reaching that helper would have enrolled a site that
    never opted in. That helper now self-heals stored credentials and
    establishes nothing, so routing this through it would silently do nothing at
    all.

    Returns True when a connection was established on this call.
    """
    if conf.get("ai_provider") != "amazee":
        return False
    if conf.get("ai_api_key"):
        return False

    storage = DjangoConfigStorage()

    def _save_models(ai_model: str, ai_expansion_model: str) -> None:
        storage.store_models(ai_model, ai_expansion_model)

    established = False
    if storage.load() is None:
        amazee_client = client or AmazeeClient()
        try:
            # No email: the demo needs none, which is the point of it. Attaching
            # a real amazee.ai account is the email flow in the admin views.
            result = AmazeeTrialProvisioner(
                amazee_client, storage, None, AmazeeModelResolver(amazee_client)
            ).provision()
        except AmazeeApiException:
            # The control plane is unreachable or refused — the demo is one-time
            # per site. AI stays off; the operator reconnects through the admin.
            _logger.warning("Could not establish the Amazee.ai demo connection.", exc_info=True)
            return False

        if result.success:
            established = True
            if result.ai_model or result.ai_expansion_model:
                _save_models(result.ai_model or "", result.ai_expansion_model or "")

    # Self-heal only, against credentials already stored: re-resolve model names
    # when the store has credentials but no model. Never mints.
    AutoProvisioner.ensure_ai_available(
        storage,
        has_explicit_api_key=False,
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

    return established
