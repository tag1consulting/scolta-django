"""Browser-layer regression test for the Scolta search bar.

The search box is rendered entirely by ``scolta.js`` into an empty mount div;
none of it is in the server HTML. So every curl/string-level check (``"scolta"``
appears in the page, the endpoints answer) passes even when the user-visible
search bar never renders — which is exactly what happened when the template tag
emitted ``window.scolta`` without a ``container`` selector and ``scolta.js``'s
auto-init silently no-op'd.

This test loads the rendered tag + the real ``scolta.js`` in a headless browser
and asserts the mount point actually gains children. It is the cheapest check
that exercises the user-visible surface rather than the endpoint surface.

Requires a chromium build: ``playwright install chromium``. Skips cleanly when
the browser binary (or playwright itself) is unavailable.
"""

import pytest
from django.test import override_settings

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import sync_playwright  # noqa: E402

# Replaces the SCOLTA dict for this test: asset_url points at the route in
# tests.browser_urls that serves the real scolta.js/css/wasm.
_SCOLTA = {
    "ai_api_key": "",
    "site_name": "Test Site",
    "indexer": "auto",
    "models": ["testapp.Post"],
    "wagtail": True,
    "asset_url": "/scolta-assets",
    "route_prefix": "api/scolta/v1",
}


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.browser_urls", SCOLTA=_SCOLTA)
def test_search_box_mounts_in_browser(live_server):
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable (run: playwright install chromium): {exc}")
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            page.goto(live_server.url + "/", wait_until="networkidle")

            # The mount div is empty in the server HTML; scolta.js must populate
            # it. If `container` is missing from window.scolta, this never fires.
            page.wait_for_selector("#scolta-search #scolta-query", timeout=5000)

            child_count = page.eval_on_selector("#scolta-search", "el => el.childElementCount")
            assert child_count > 0, "scolta.js did not render into #scolta-search"
            assert page.query_selector("#scolta-search input") is not None, (
                "search input did not render"
            )
            # This harness intentionally builds no Pagefind index, so the eager
            # import of pagefind.js 404s — expected and unrelated to whether the
            # search UI mounts. Any *other* JS error is a real mount failure.
            unexpected = [e for e in errors if "pagefind" not in e.lower()]
            assert not unexpected, f"unexpected JS errors during mount: {unexpected}"
        finally:
            browser.close()
