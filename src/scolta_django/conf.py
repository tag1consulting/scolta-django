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
    """Build a ScoltaConfig from the SCOLTA settings dict (unknown keys ignored)."""
    return ScoltaConfig.from_dict(_settings())


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
    """Resolve configured models to Django model classes."""
    from django.apps import apps

    resolved = []
    for label in model_labels():
        try:
            resolved.append(apps.get_model(label))
        except (LookupError, ValueError):
            continue
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
