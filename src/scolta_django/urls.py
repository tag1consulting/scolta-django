"""URL routes for the Scolta AI endpoints.

Include in a project's urls.py:
    path("", include("scolta_django.urls"))

Routes are registered under SCOLTA['route_prefix'] (default api/scolta/v1) so
the paths match the Drupal/WordPress/Laravel adapters and scolta.js works
identically:
    POST {prefix}/expand-query
    POST {prefix}/summarize
    POST {prefix}/followup
    GET  {prefix}/health

The Amazee.ai upgrade UI (rendered page + admin-facing JSON API) lives under a
fixed scolta/amazee/ prefix:
    GET  scolta/amazee/            (Alpine.js settings page)
    GET  scolta/amazee/status
    POST scolta/amazee/provision
    POST scolta/amazee/request-code
    POST scolta/amazee/sign-in
    POST scolta/amazee/regions
    POST scolta/amazee/upgrade
    POST scolta/amazee/disconnect
"""

from __future__ import annotations

from django.urls import path

from . import amazee_views, conf, views

_prefix = conf.route_prefix().strip("/")

app_name = "scolta"

urlpatterns = [
    path(f"{_prefix}/expand-query", views.expand_query, name="expand_query"),
    path(f"{_prefix}/summarize", views.summarize, name="summarize"),
    path(f"{_prefix}/followup", views.follow_up, name="followup"),
    path(f"{_prefix}/health", views.health, name="health"),
    path("scolta/amazee/", amazee_views.settings_page, name="amazee_settings"),
    path("scolta/amazee/status", amazee_views.status, name="amazee_status"),
    path("scolta/amazee/provision", amazee_views.provision, name="amazee_provision"),
    path("scolta/amazee/request-code", amazee_views.request_code, name="amazee_request_code"),
    path("scolta/amazee/sign-in", amazee_views.sign_in, name="amazee_sign_in"),
    path("scolta/amazee/regions", amazee_views.regions, name="amazee_regions"),
    path("scolta/amazee/upgrade", amazee_views.upgrade, name="amazee_upgrade"),
    path("scolta/amazee/disconnect", amazee_views.disconnect, name="amazee_disconnect"),
]
