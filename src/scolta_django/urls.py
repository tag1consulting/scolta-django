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
"""

from __future__ import annotations

from django.urls import path

from . import conf, views

_prefix = conf.route_prefix().strip("/")

app_name = "scolta"

urlpatterns = [
    path(f"{_prefix}/expand-query", views.expand_query, name="expand_query"),
    path(f"{_prefix}/summarize", views.summarize, name="summarize"),
    path(f"{_prefix}/followup", views.follow_up, name="followup"),
    path(f"{_prefix}/health", views.health, name="health"),
]
