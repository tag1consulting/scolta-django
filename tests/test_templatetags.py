"""Template-tag emission: the config the widget actually receives.

Covers the route_prefix regression (endpoints were hardcoded to
/api/scolta/v1/... while urls.py registers under the configurable prefix) and
the </script> injection regression (json.dumps + mark_safe without
script-context escaping). The contract test at the bottom is the
adapter-level widget-mount smoke: it asserts everything scolta.js's auto-init
requires of the EMITTED config, and that the emitted endpoints are live
routes — the Jest mount tests in scolta-python never see Django's emission.
"""

from __future__ import annotations

import importlib
import json
import re

import pytest
from django.test import Client
from django.urls import clear_url_caches

from scolta_django.templatetags.scolta import scolta_config_json, scolta_search


def _extract_window_config(html: str) -> dict:
    match = re.search(r"window\.scolta = (\{.*?\});</script>", html, re.S)
    assert match, "scolta_search must emit window.scolta"
    return json.loads(match.group(1))


@pytest.fixture
def custom_prefix(settings):
    """Re-register the scolta routes under a custom prefix (urls.py computes
    the prefix at import time, so the module must be reloaded)."""

    def _reload():
        # tests.urls must reload too: its include() resolver instance caches
        # url_patterns, so reloading only scolta_django.urls is not enough.
        import scolta_django.urls
        import tests.urls

        importlib.reload(scolta_django.urls)
        importlib.reload(tests.urls)
        clear_url_caches()

    original_scolta = settings.SCOLTA

    def apply(prefix: str):
        settings.SCOLTA = {**settings.SCOLTA, "route_prefix": prefix}
        _reload()

    yield apply
    # Restore BEFORE reloading: this fixture tears down before the settings
    # fixture reverts, so the reload must not bake in the custom prefix.
    settings.SCOLTA = original_scolta
    _reload()


def test_custom_route_prefix_emits_matching_endpoints(custom_prefix):
    custom_prefix("custom/search/api")
    config = _extract_window_config(scolta_search())
    assert config["endpoints"] == {
        "expand": "/custom/search/api/expand-query",
        "summarize": "/custom/search/api/summarize",
        "followup": "/custom/search/api/followup",
    }


def test_custom_route_prefix_endpoints_are_live(custom_prefix):
    """The emitted endpoint must answer — with the hardcoded default it 404ed."""
    custom_prefix("custom/search/api")
    config = _extract_window_config(scolta_search())
    resp = Client().post(
        config["endpoints"]["expand"],
        data=json.dumps({"query": "chocolate"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["terms"] == ["chocolate"]


def test_default_prefix_unchanged():
    config = _extract_window_config(scolta_search())
    assert config["endpoints"]["expand"] == "/api/scolta/v1/expand-query"


# -- script-context escaping ----------------------------------------------------


def test_config_json_escapes_script_close(settings):
    settings.SCOLTA = {**settings.SCOLTA, "site_name": "Evil</script><script>alert(1)//"}
    out = scolta_config_json()
    assert "</script>" not in out
    assert "<script>" not in out
    # Still round-trips to the original value.
    assert json.loads(out)["siteName"] == "Evil</script><script>alert(1)//"


def test_scolta_search_escapes_script_close_in_config(settings):
    settings.SCOLTA = {**settings.SCOLTA, "site_name": "Evil</script><script>alert(1)//"}
    html = scolta_search()
    assert "<script>alert(1)" not in html
    assert _extract_window_config(html)["siteName"] == "Evil</script><script>alert(1)//"


# -- widget-mount contract (emitted config) --------------------------------------


def test_emitted_config_satisfies_widget_mount_contract():
    """Everything scolta.js auto-init needs, asserted on the EMITTED config."""
    html = scolta_search("my-search")
    config = _extract_window_config(html)

    # Mount point: auto-init bails without window.scolta.container, and the
    # container element must be rendered.
    assert config["container"] == "#my-search"
    assert '<div id="my-search" class="scolta-search">' in html

    # WASM glue module path: import(wasmPath) needs the full module path.
    assert config["wasmPath"].endswith("/wasm/scolta_core.js")

    # Pagefind runtime path ends in pagefind.js.
    assert config["pagefindPath"].endswith("/pagefind.js")

    # Scoring config block is present (the WASM engine consumes it).
    assert "scoring" in config

    # The asset tags the widget loads, cache-busted.
    assert re.search(r'<link rel="stylesheet" href="[^"]+/css/scolta\.css\?v=\d', html)
    assert re.search(r'<script type="module" src="[^"]+/js/scolta\.js\?v=\d', html)

    # Every emitted endpoint resolves to a live route (POST != 404/405).
    client = Client()
    for name, url in config["endpoints"].items():
        resp = client.post(
            url,
            data=json.dumps({"query": "x", "context": "c", "messages": []}),
            content_type="application/json",
        )
        assert resp.status_code not in (404, 405), f"emitted endpoint {name} -> {url} is dead"
