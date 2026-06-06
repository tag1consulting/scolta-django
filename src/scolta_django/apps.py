"""Django app config — wires change-tracking signals for configured models."""

from __future__ import annotations

from django.apps import AppConfig


class ScoltaConfig(AppConfig):
    name = "scolta_django"
    verbose_name = "Scolta AI Search"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import conf, signals

        for model in conf.models():
            signals.connect_model(model)

        # Wagtail integration (Phase 10) — imported only if Wagtail is present.
        try:
            from .wagtail import register as register_wagtail  # noqa: F401

            register_wagtail()
        except ImportError:
            pass
