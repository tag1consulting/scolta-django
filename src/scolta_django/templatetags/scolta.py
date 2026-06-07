"""Template tags to render the Scolta search UI and load assets.

Usage in a template:
    {% load scolta %}
    {% scolta_search %}
"""

from __future__ import annotations

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .. import conf

register = template.Library()


@register.simple_tag
def scolta_config_json() -> str:
    """The browser config (window.scolta) as a JSON string."""
    return mark_safe(json.dumps(conf.scolta_config().to_browser_config()))


@register.simple_tag
def scolta_search(container_id: str = "scolta-search") -> str:
    """Render the search container, window.scolta config, and asset tags."""
    asset_url = str(conf.get("asset_url", "/static/scolta/")).rstrip("/")
    browser_config = conf.scolta_config().to_browser_config()
    # to_browser_config() leaves platform-specific paths blank for the adapter
    # to fill (mirrors the PHP base config + the WP/Laravel adapters). scolta.js
    # does `import(wasmPath)` directly, so it must be the full path to the WASM
    # glue module — not the containing directory — or the import 404s.
    if not browser_config.get("wasmPath"):
        browser_config["wasmPath"] = f"{asset_url}/wasm/scolta_core.js"
    # scolta.js auto-init reads window.scolta.container (a CSS selector) to find
    # its mount point; without it the search box never renders. Match the div id
    # rendered below. (Mirrors the WP/Laravel adapters' config contract.)
    browser_config.setdefault("container", f"#{container_id}")
    config_json = json.dumps(browser_config)
    return format_html(
        '<div id="{}" class="scolta-search"></div>\n'
        '<link rel="stylesheet" href="{}/css/scolta.css">\n'
        "<script>window.scolta = {};</script>\n"
        '<script type="module" src="{}/js/scolta.js"></script>',
        container_id,
        asset_url,
        mark_safe(config_json),
        asset_url,
    )
