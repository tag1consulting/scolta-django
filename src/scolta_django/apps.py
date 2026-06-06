"""Django app config — wires change-tracking signals for configured models."""

from __future__ import annotations

from django.apps import AppConfig


class ScoltaConfig(AppConfig):
    name = "scolta_django"
    verbose_name = "Scolta AI Search"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.apps import apps as django_apps

        from . import conf, signals

        for model in conf.models():
            signals.connect_model(model)

        # Wagtail integration (Phase 10) — wired only when 'wagtail' is an
        # installed app (importing wagtail.models requires the app, even when the
        # package is merely importable in the environment).
        if django_apps.is_installed("wagtail"):
            from .wagtail import register as register_wagtail

            register_wagtail()
