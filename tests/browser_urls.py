"""URLconf for the search-bar browser regression test.

Serves a minimal page that renders the ``{% scolta_search %}`` tag, plus a route
that serves the real ``scolta.js``/``scolta.css`` assets from the installed
``scolta`` package — the same assets a project would publish. The bug this guards
against only reproduces when the actual script runs against the actual emitted
config, so the test must load both for real.
"""

from pathlib import Path

import scolta
from django.http import HttpResponse
from django.template import Context, Template
from django.urls import path, re_path
from django.views.static import serve

_ASSETS = Path(scolta.__file__).resolve().parent / "assets"

_PAGE = Template(
    '{% load scolta %}<!doctype html><html lang="en"><head>'
    '<meta charset="utf-8"><title>scolta test</title></head>'
    "<body>{% scolta_search %}</body></html>"
)


def search_page(request):
    return HttpResponse(_PAGE.render(Context({})))


urlpatterns = [
    re_path(r"^scolta-assets/(?P<path>.*)$", serve, {"document_root": str(_ASSETS)}),
    path("", search_page),
]
