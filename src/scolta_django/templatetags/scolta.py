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
    browser_config.setdefault("wasmPath", f"{asset_url}/wasm/")
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
