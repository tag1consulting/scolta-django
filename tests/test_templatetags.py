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


# -- core scolta config keys reach the browser ----------------------------------


def test_hide_empty_facets_defaults_to_true():
    """The facet-visibility opt-out must be emitted, not merely defaulted.

    scolta.js reads an absent key as "hide" (only a literal false disables it),
    so a missing key looks identical to true in the browser. Asserting the key is
    present is what makes the false case below meaningful.
    """
    config = _extract_window_config(scolta_search())
    assert config["hideEmptyFacets"] is True


def test_hide_empty_facets_opt_out_reaches_the_browser(settings):
    """The false direction is the load-bearing one.

    hide_empty_facets is a core scolta key, not an adapter key: it needs no
    conf.py accessor and no template-tag change, because scolta_config() hands
    the whole SCOLTA dict to ScoltaConfig.from_dict() and _emitted_browser_config()
    passes through whatever to_browser_config() returns. This test pins that
    pass-through end to end.
    """
    settings.SCOLTA = {**settings.SCOLTA, "hide_empty_facets": False}
    config = _extract_window_config(scolta_search())
    assert config["hideEmptyFacets"] is False


def test_specificity_scoring_key_reaches_the_browser(settings):
    """A specificity knob must reach window.scolta.scoring, same mechanism.

    Covers the scoring path as well as the top-level one: the six specificity
    keys and the two filter-hint keys cross as scoring sub-keys rather than
    top-level ones, so a top-level assertion alone would not exercise them.
    """
    config = _extract_window_config(scolta_search())
    assert config["scoring"]["SPECIFICITY_COOCCURRENCE"] == 0.9
    assert config["scoring"]["SPECIFICITY_AGREEMENT_GATE"] == 0.45
    assert config["scoring"]["SPECIFICITY_AGREEMENT_DECAY"] == 1.0

    settings.SCOLTA = {**settings.SCOLTA, "specificity_cooccurrence": 1.4}
    config = _extract_window_config(scolta_search())
    assert config["scoring"]["SPECIFICITY_COOCCURRENCE"] == 1.4


# -- search as you type ---------------------------------------------------------

# The ten browser keys and the fallbacks the bundle uses when a key is absent.
SAYT_DEFAULTS = {
    "saytEnabled": True,
    "saytMinChars": 2,
    "saytDebounceMs": 150,
    "saytMaxSuggestions": 6,
    "saytRecentSearches": True,
    "saytMaxRecent": 3,
    "saytExpand": True,
    "saytExpandPerMinute": 6,
    "saytExpansionDelayMs": 500,
    "saytSuggestionAction": "navigate",
}


def test_sayt_defaults_reach_the_browser():
    """All ten must be emitted, not merely defaulted.

    scolta.js treats an absent key as the default, so a missing key looks
    identical to a correct one in the browser. Asserting presence is what makes
    the override cases below meaningful.
    """
    config = _extract_window_config(scolta_search())
    for key, expected in SAYT_DEFAULTS.items():
        assert key in config, f"{key} must be emitted, not left to the bundle's fallback"
        assert config[key] == expected, f"{key} must be emitted as its documented default"
        assert key not in config["scoring"], f"{key} is a top-level key, not a scoring one"


def test_sayt_settings_reach_the_browser(settings):
    """A SCOLTA dict carrying sayt keys reaches the emitted browser config.

    These are core scolta keys, not adapter keys: they need no conf.py accessor
    and no template-tag change, because scolta_config() hands the whole SCOLTA
    dict to ScoltaConfig.from_dict() and the tag passes through whatever
    to_browser_config() returns. This pins that pass-through end to end for all
    ten, which is the only reason no adapter code ships with this feature.
    """
    settings.SCOLTA = {
        **settings.SCOLTA,
        "sayt_enabled": False,
        "sayt_min_chars": 1,
        "sayt_debounce_ms": 400,
        "sayt_max_suggestions": 10,
        "sayt_recent_searches": False,
        "sayt_max_recent": 5,
        "sayt_expand": False,
        "sayt_expand_per_minute": 2,
        "sayt_expansion_delay_ms": 800,
        "sayt_suggestion_action": "search",
    }
    config = _extract_window_config(scolta_search())

    assert config["saytEnabled"] is False
    assert config["saytMinChars"] == 1
    assert config["saytDebounceMs"] == 400
    assert config["saytMaxSuggestions"] == 10
    assert config["saytRecentSearches"] is False
    assert config["saytMaxRecent"] == 5
    assert config["saytExpand"] is False
    assert config["saytExpandPerMinute"] == 2
    assert config["saytExpansionDelayMs"] == 800
    assert config["saytSuggestionAction"] == "search"


def test_sayt_disabled_reaches_the_browser_as_false(settings):
    """The off direction is the load-bearing one: SAYT is on by default in the
    bundle too, so an emission that dropped the key would still look correct."""
    settings.SCOLTA = {**settings.SCOLTA, "sayt_enabled": False}
    assert _extract_window_config(scolta_search())["saytEnabled"] is False


def test_sayt_string_settings_coerce_like_every_other_key(settings):
    """A settings dict built from environment variables carries strings."""
    settings.SCOLTA = {
        **settings.SCOLTA,
        "sayt_enabled": "0",
        "sayt_min_chars": "3",
        "sayt_debounce_ms": "250",
    }
    config = _extract_window_config(scolta_search())

    assert config["saytEnabled"] is False
    assert config["saytMinChars"] == 3
    assert config["saytDebounceMs"] == 250


def test_unknown_sayt_suggestion_action_reaches_the_browser_as_navigate(settings):
    """Clamped once on the way out rather than rediscovered client-side."""
    settings.SCOLTA = {**settings.SCOLTA, "sayt_suggestion_action": "teleport"}
    assert _extract_window_config(scolta_search())["saytSuggestionAction"] == "navigate"


def test_sayt_json_config_matches_the_widget_emission(settings):
    """scolta_config_json() is the second emission path and must agree.

    A project that mounts the widget itself uses this tag instead of
    scolta_search(), so a key present in one and absent from the other is a
    feature that works on one mounting path only.
    """
    settings.SCOLTA = {**settings.SCOLTA, "sayt_max_recent": 5}
    config = json.loads(str(scolta_config_json()))

    for key in SAYT_DEFAULTS:
        assert key in config, f"{key} must be emitted by scolta_config_json() too"
    assert config["saytMaxRecent"] == 5
