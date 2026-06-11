"""Template tags to render the Scolta search UI and load assets.

Usage in a template:
    {% load scolta %}
    {% scolta_search %}
"""

from __future__ import annotations

import json
from pathlib import Path

import scolta
from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .. import conf

register = template.Library()

# json.dumps escapes quotes but not HTML: a site_name (or any other config
# value) containing "</script>" would close the inline <script> block early.
# Escape the same characters Django's json_script does before mark_safe.
_SCRIPT_ESCAPES = {ord("<"): "\\u003C", ord(">"): "\\u003E", ord("&"): "\\u0026"}


def _script_safe_json(value) -> str:
    return json.dumps(value).translate(_SCRIPT_ESCAPES)


# The CSS/JS the adapter serves are vendored by the `scolta` package; the
# adapter mirrors them under `asset_url` (e.g. /scolta-assets/ or /static/scolta/).
_ASSET_ROOT = Path(scolta.__file__).parent / "assets"

# Package version fallback for the cache-bust token (mirrors the scolta package
# that ships the asset). Used when the asset file cannot be stat'd.
_VERSION_FALLBACK = getattr(scolta, "__version__", "") or "0"


def _asset_version(relpath: str) -> str:
    """Cache-bust token for a shipped asset.

    Prefers the asset file's mtime so a dev rebuild actually busts the HTTP
    cache (matching WordPress's ``filemtime`` rationale — Drupal/WP both append
    a version param, the Django adapter previously did not, risking a stale
    asset from cache). Falls back to the ``scolta`` package version when the
    file cannot be stat'd (e.g. ``asset_url`` points to a custom location).
    """
    try:
        return str(int(_ASSET_ROOT.joinpath(relpath).stat().st_mtime))
    except OSError:
        return _VERSION_FALLBACK


def _emitted_browser_config() -> dict:
    """The browser config with the endpoints this app actually registered.

    to_browser_config() hardcodes /api/scolta/v1/... while urls.py registers
    the AI routes under the configurable SCOLTA["route_prefix"] (and wherever
    the project mounts the urlconf) — with a custom prefix the widget POSTed
    to 404s. reverse() resolves the real URLs, which also fixes sub-path
    mounting. The endpoints are overridden on the returned dict (rather than
    via to_browser_config(endpoints=...)) so this adapter keeps working with
    scolta releases that predate the override parameter.
    """
    browser_config = conf.scolta_config().to_browser_config()
    browser_config["endpoints"] = {
        "expand": reverse("scolta:expand_query"),
        "summarize": reverse("scolta:summarize"),
        "followup": reverse("scolta:followup"),
    }
    return browser_config


@register.simple_tag
def scolta_config_json() -> str:
    """The browser config (window.scolta) as a JSON string."""
    return mark_safe(_script_safe_json(_emitted_browser_config()))


@register.simple_tag
def scolta_search(container_id: str = "scolta-search") -> str:
    """Render the search container, window.scolta config, and asset tags."""
    asset_url = str(conf.get("asset_url", "/static/scolta/")).rstrip("/")
    browser_config = _emitted_browser_config()
    # scolta.js auto-init bails unless window.scolta.container names the mount
    # point, and it loads WASM via `import(wasmPath)` where wasmPath must be the
    # full glue-module path (…/wasm/scolta_core.js), not the directory. Mirror
    # the WP/Laravel adapters so the browser widget actually mounts.
    browser_config.setdefault("container", f"#{container_id}")
    # to_browser_config() emits wasmPath as an empty string, so setdefault would
    # never fill it — treat empty as unset while still honoring an explicit value.
    if not browser_config.get("wasmPath"):
        browser_config["wasmPath"] = f"{asset_url}/wasm/scolta_core.js"
    config_json = _script_safe_json(browser_config)
    css_version = _asset_version("css/scolta.css")
    js_version = _asset_version("js/scolta.js")
    return format_html(
        '<div id="{}" class="scolta-search"></div>\n'
        '<link rel="stylesheet" href="{}/css/scolta.css?v={}">\n'
        "<script>window.scolta = {};</script>\n"
        '<script type="module" src="{}/js/scolta.js?v={}"></script>',
        container_id,
        asset_url,
        css_version,
        mark_safe(config_json),
        asset_url,
        js_version,
    )
