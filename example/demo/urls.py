from pathlib import Path

import scolta
from blog.views import search_page
from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

_ASSETS = Path(scolta.__file__).resolve().parent / "assets"
_PAGEFIND = Path(settings.SCOLTA["output_dir"]) / "pagefind"

urlpatterns = [
    path("", search_page),
    path("search/", search_page, name="search"),
    re_path(r"^pagefind/(?P<path>.*)$", serve, {"document_root": str(_PAGEFIND)}),
    re_path(r"^scolta-assets/(?P<path>.*)$", serve, {"document_root": str(_ASSETS)}),
    path("", include("scolta_django.urls")),
]
