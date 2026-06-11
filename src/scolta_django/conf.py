"""Resolve Scolta configuration from Django settings.

A project configures Scolta via a single ``SCOLTA`` dict in settings. Scolta
config keys (snake_case, mirroring scolta-php) plus a few adapter-only keys:

    SCOLTA = {
        "ai_api_key": env("SCOLTA_API_KEY"),
        "site_name": "My Site",
        "indexer": "auto",
        "models": ["blog.Post", "pages.Page"],
        "state_dir": BASE_DIR / ".scolta-state",
        "output_dir": BASE_DIR / "static" / "scolta-pagefind",
        "auto_rebuild": True,
        "auto_rebuild_delay": 300,
        "route_prefix": "api/scolta/v1",
    }
"""

from __future__ import annotations

import os

from django.conf import settings
from scolta.config import ScoltaConfig


def _settings() -> dict:
    return getattr(settings, "SCOLTA", {}) or {}


def get(key, default=None):
    return _settings().get(key, default)


def scolta_config() -> ScoltaConfig:
    """Build a ScoltaConfig from the SCOLTA settings dict (unknown keys ignored).

    Amazee.ai credentials (when stored and no explicit key is set) are layered
    on top to point the OpenAI-compatible client at the LiteLLM endpoint."""
    data = dict(_settings())
    from .amazee import config_overrides

    # config_overrides() itself guards the expected missing-table case and
    # returns {} — no blanket except here, so real bugs surface.
    data.update(config_overrides(data))
    return ScoltaConfig.from_dict(data)


def state_dir() -> str:
    configured = get("state_dir")
    if configured:
        return str(configured)
    base = getattr(settings, "BASE_DIR", os.getcwd())
    return os.path.join(str(base), ".scolta-state")


def output_dir() -> str:
    configured = get("output_dir")
    if configured:
        return str(configured)
    base = getattr(settings, "BASE_DIR", os.getcwd())
    return os.path.join(str(base), "scolta-pagefind")


def model_labels() -> list[str]:
    """Configured 'app_label.ModelName' strings."""
    return list(get("models", []) or [])


def models() -> list:
    """Resolve configured models to Django model classes.

    A label that doesn't resolve raises ImproperlyConfigured: silently
    skipping it (the old behaviour) meant a typo in SCOLTA["models"] left
    that content unindexed with no signal anywhere. apps.ready() calls this,
    so a bad label fails at startup."""
    from django.apps import apps
    from django.core.exceptions import ImproperlyConfigured

    resolved = []
    for label in model_labels():
        try:
            resolved.append(apps.get_model(label))
        except (LookupError, ValueError) as exc:
            raise ImproperlyConfigured(
                f"SCOLTA['models'] entry {label!r} does not resolve to an installed model: {exc}"
            ) from exc
    return resolved


def auto_rebuild() -> bool:
    return bool(get("auto_rebuild", True))


def auto_rebuild_delay() -> int:
    return int(get("auto_rebuild_delay", 300))


def route_prefix() -> str:
    return str(get("route_prefix", "api/scolta/v1"))


def site_name() -> str:
    return str(get("site_name", "") or "")


def hmac_secret() -> str | None:
    secret = getattr(settings, "SECRET_KEY", None)
    return str(secret) if secret else None
