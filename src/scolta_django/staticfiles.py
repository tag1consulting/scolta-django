"""Staticfiles finder exposing the scolta asset bundle under ``scolta/``.

The ``scolta`` package vendors the browser runtime (scolta.js/css, the WASM
scoring engine, the Pagefind runtime) inside site-packages, where no default
finder looks. Add this finder so ``collectstatic`` (and the dev server's
static serving) picks the bundle up at the default ``asset_url``
(``/static/scolta/``) without hand-copying files:

    STATICFILES_FINDERS = [
        "django.contrib.staticfiles.finders.FileSystemFinder",
        "django.contrib.staticfiles.finders.AppDirectoriesFinder",
        "scolta_django.staticfiles.ScoltaAssetFinder",
    ]
"""

from __future__ import annotations

from pathlib import Path

import scolta
from django.contrib.staticfiles.finders import BaseFinder
from django.core.files.storage import FileSystemStorage

_PREFIX = "scolta"
_ASSET_ROOT = Path(scolta.__file__).parent / "assets"


class ScoltaAssetFinder(BaseFinder):
    """Serves the ``scolta`` package's vendored assets as ``scolta/...``."""

    def __init__(self, *args, **kwargs):
        self.storage = FileSystemStorage(location=str(_ASSET_ROOT))
        self.storage.prefix = _PREFIX
        super().__init__(*args, **kwargs)

    def check(self, **kwargs):
        return []

    def find(self, path, **kwargs):
        # Django <5.2 passes all=..., 5.2+ passes find_all=...
        find_all = kwargs.get("find_all", kwargs.get("all", False))
        prefix = _PREFIX + "/"
        if not path.startswith(prefix):
            return [] if find_all else None
        relpath = path[len(prefix) :]
        candidate = _ASSET_ROOT / relpath
        if candidate.is_file():
            return [str(candidate)] if find_all else str(candidate)
        return [] if find_all else None

    def list(self, ignore_patterns):
        for f in sorted(_ASSET_ROOT.rglob("*")):
            if f.is_file():
                yield str(f.relative_to(_ASSET_ROOT)), self.storage
