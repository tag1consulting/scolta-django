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
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .. import conf

register = template.Library()

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


@register.simple_tag
def scolta_config_json() -> str:
    """The browser config (window.scolta) as a JSON string."""
    return mark_safe(json.dumps(conf.scolta_config().to_browser_config()))


@register.simple_tag
def scolta_search(container_id: str = "scolta-search") -> str:
    """Render the search container, window.scolta config, and asset tags."""
    asset_url = str(conf.get("asset_url", "/static/scolta/")).rstrip("/")
    browser_config = conf.scolta_config().to_browser_config()
    # scolta.js auto-init bails unless window.scolta.container names the mount
    # point, and it loads WASM via `import(wasmPath)` where wasmPath must be the
    # full glue-module path (…/wasm/scolta_core.js), not the directory. Mirror
    # the WP/Laravel adapters so the browser widget actually mounts.
    browser_config.setdefault("container", f"#{container_id}")
    # to_browser_config() emits wasmPath as an empty string, so setdefault would
    # never fill it — treat empty as unset while still honoring an explicit value.
    if not browser_config.get("wasmPath"):
        browser_config["wasmPath"] = f"{asset_url}/wasm/scolta_core.js"
    config_json = json.dumps(browser_config)
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
