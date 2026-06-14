#!/usr/bin/env python3
"""Validate the built PyPI artifacts in dist/.

Run after `uv build` (CI's `dist` job calls this; it also runs locally):

    uv build && uv run python scripts/validate_dist.py

Why this gate exists
--------------------
Distribution artifacts are easy to break silently in two opposite directions,
and both have bitten this fleet before:

* CONTENT LEAK / BLOAT — scolta-wp once shipped a ~13 MB plugin zip (nested
  vendor/ + vendored test trees), and the WP.org review flagged dist cruft
  (caches, IDE files, tests). A Python wheel can leak the same way: bundled
  ``tests/``, ``__pycache__``, ``*.pyc``, ``.ruff_cache``, editor files.
* SILENT MISSING DATA — a Django app is broken at install time if its
  ``templates/`` or ``templatetags/`` are not packaged, yet the build still
  "succeeds". hatchling includes package data under the package dir by
  default, but a stray ``[tool.hatch.build]`` exclude or a moved file would
  drop them with no error. This script makes that failure loud.

The package-data filter lives in pyproject.toml under
``[tool.hatch.build.targets.wheel] packages = ["src/scolta_django"]`` — that
declaration is WHAT decides which files land in the wheel. If an assert here
fails, that is the first place to look.

scolta-django ships NO vendored scolta.js / no static assets: the browser
runtime comes from the ``scolta`` PyPI dependency. So there is no static/
tree to assert present — only the package's Python modules, the one HTML
template, the templatetags, and py.typed.
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

DIST = Path(__file__).resolve().parent.parent / "dist"

# --- Size caps (shared fleet pattern: ~2x the measured good artifact) --------
# Measured on a clean `uv build` of 1.0.4.dev0 (2026-06-14):
#   wheel  = 31_045 bytes  (~30 KiB)
#   sdist  = 111_924 bytes (~109 KiB)
# Caps set at roughly 2x the measured size. A breach means either real new
# content was added (bump the cap deliberately) or cruft leaked (find it via
# the content asserts below — the filter lives in pyproject.toml).
WHEEL_MAX_BYTES = 64 * 1024  # 65_536  (~2x of 31_045)
SDIST_MAX_BYTES = 224 * 1024  # 229_376 (~2x of 111_924)

# --- Wheel: files that MUST be present (load-bearing) ------------------------
# Enumerated from the source tree + pyproject. templatetags are the
# load-bearing piece (the {% scolta_search %} tag); the template renders the
# Amazee settings admin page; py.typed ships the typing marker.
WHEEL_REQUIRED = [
    "scolta_django/__init__.py",
    "scolta_django/apps.py",
    "scolta_django/conf.py",
    "scolta_django/urls.py",
    "scolta_django/views.py",
    "scolta_django/searchable.py",
    "scolta_django/signals.py",
    "scolta_django/tasks.py",
    "scolta_django/staticfiles.py",
    "scolta_django/content_source.py",
    "scolta_django/wagtail_hooks.py",
    "scolta_django/py.typed",
    # Django app data — broken at install time if any of these go missing:
    "scolta_django/templates/scolta_django/amazee_settings.html",
    "scolta_django/templatetags/__init__.py",
    "scolta_django/templatetags/scolta.py",
    "scolta_django/management/__init__.py",
    "scolta_django/management/commands/__init__.py",
    "scolta_django/management/commands/scolta_build.py",
    "scolta_django/management/commands/scolta_amazee_provision.py",
    "scolta_django/migrations/__init__.py",
    "scolta_django/wagtail/__init__.py",
]

# --- Cruft sweeps (fail-closed: the package file set is ours to enumerate) ---
# Anything matching these in either artifact's *package* payload is junk.
CRUFT_PATTERNS = [
    (re.compile(r"(^|/)__pycache__/"), "__pycache__ directory"),
    (re.compile(r"\.pyc$"), "compiled .pyc bytecode"),
    (re.compile(r"(^|/)\.ruff_cache/"), ".ruff_cache"),
    (re.compile(r"(^|/)\.pytest_cache/"), ".pytest_cache"),
    (re.compile(r"(^|/)\.mypy_cache/"), ".mypy_cache"),
    (re.compile(r"(^|/)\.DS_Store$"), "macOS .DS_Store"),
    (re.compile(r"(^|/)\.idea/"), "JetBrains .idea IDE files"),
    (re.compile(r"(^|/)\.vscode/"), ".vscode IDE files"),
    (re.compile(r"\.egg-info/"), "stale .egg-info"),
    (re.compile(r"(^|/)\.venv/"), "checked-in virtualenv"),
]

FILTER_NOTE = (
    "The wheel file set is decided by "
    "[tool.hatch.build.targets.wheel] packages in pyproject.toml; the sdist "
    "set follows the git tree (hatchling vcs). Fix leaks/omissions there."
)


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_one(pattern: str) -> Path:
    matches = sorted(DIST.glob(pattern))
    if not matches:
        fail(f"no {pattern} found in {DIST} — run `uv build` first")
    if len(matches) > 1:
        fail(
            f"multiple {pattern} in {DIST}: {[m.name for m in matches]} — "
            "stale artifacts present; clean dist/ before building"
        )
    return matches[0]


def check_cruft(names: list[str], where: str) -> None:
    for name in names:
        for pat, label in CRUFT_PATTERNS:
            if pat.search(name):
                fail(f"{where} leaked {label}: {name!r}. {FILTER_NOTE}")


def validate_wheel() -> None:
    whl = find_one("*.whl")
    size = whl.stat().st_size
    print(f"wheel: {whl.name} ({size} bytes)")
    if size > WHEEL_MAX_BYTES:
        fail(
            f"wheel is {size} bytes, over the {WHEEL_MAX_BYTES}-byte cap "
            f"(~2x the 31,045-byte baseline). Either real content was added "
            f"(bump WHEEL_MAX_BYTES deliberately) or cruft leaked. {FILTER_NOTE}"
        )

    with zipfile.ZipFile(whl) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]

    check_cruft(names, f"wheel {whl.name}")

    # Required package data must be present.
    present = set(names)
    missing = [r for r in WHEEL_REQUIRED if r not in present]
    if missing:
        fail(
            "wheel is missing required package files (Django app would be "
            f"broken at install time): {missing}. {FILTER_NOTE}"
        )

    # Every payload entry must live under the package dir or the dist-info
    # metadata — nothing else belongs in a wheel (fail-closed).
    dist_info = re.compile(r"^scolta_django-[^/]+\.dist-info/")
    pkg = re.compile(r"^scolta_django/")
    for n in names:
        if not (pkg.match(n) or dist_info.match(n)):
            fail(
                f"wheel {whl.name} contains an entry outside the package and "
                f"dist-info: {n!r}. {FILTER_NOTE}"
            )

    # No tests/ in the wheel.
    tests = [n for n in names if re.search(r"(^|/)tests?/", n)]
    if tests:
        fail(f"wheel {whl.name} ships test files: {tests}. {FILTER_NOTE}")

    print(f"  OK: {len(names)} files, all required package data present")


def validate_sdist() -> None:
    sdist = find_one("*.tar.gz")
    size = sdist.stat().st_size
    print(f"sdist: {sdist.name} ({size} bytes)")
    if size > SDIST_MAX_BYTES:
        fail(
            f"sdist is {size} bytes, over the {SDIST_MAX_BYTES}-byte cap "
            f"(~2x the 111,924-byte baseline). Either real content was added "
            f"(bump SDIST_MAX_BYTES deliberately) or junk leaked. {FILTER_NOTE}"
        )

    with tarfile.open(sdist, "r:gz") as tf:
        names = [m.name for m in tf.getmembers() if m.isfile()]

    check_cruft(names, f"sdist {sdist.name}")

    # The sdist must be a buildable source set: pyproject + the src package +
    # the version-bearing __init__. These are what `pip install <sdist>` needs.
    root = names[0].split("/", 1)[0]  # e.g. scolta_django-1.0.4.dev0
    sdist_required = [
        f"{root}/pyproject.toml",
        f"{root}/src/scolta_django/__init__.py",
        f"{root}/src/scolta_django/templatetags/scolta.py",
        f"{root}/src/scolta_django/templates/scolta_django/amazee_settings.html",
        f"{root}/README.md",
    ]
    present = set(names)
    missing = [r for r in sdist_required if r not in present]
    if missing:
        fail(f"sdist is not a buildable source set, missing: {missing}. {FILTER_NOTE}")

    print(f"  OK: {len(names)} files, buildable source set present")


def main() -> None:
    if not DIST.is_dir():
        fail(f"{DIST} does not exist — run `uv build` first")
    validate_wheel()
    validate_sdist()
    print("dist validation passed.")


if __name__ == "__main__":
    main()
