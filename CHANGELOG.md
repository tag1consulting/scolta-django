# Changelog

## [Unreleased]

### Security
- **The Amazee.ai endpoints and settings page now require an admin user and
  enforce CSRF** (`amazee_views.py`). All eight JSON views were `csrf_exempt`
  with no auth at all: any anonymous visitor could `disconnect()` (wiping the
  site's stored AI credentials), trigger trial provisioning, or drive OTP
  flows against arbitrary emails. The default bar is an active staff user
  (`staff_member_required` semantics; the JSON endpoints return 403 rather
  than redirect). Hosts whose admins are not Django-staff (e.g. some Wagtail
  setups) can override via `SCOLTA["amazee_access"]`, a callable
  `(request) -> bool`. `csrf_exempt` is dropped everywhere; the Alpine.js
  settings UI sends `X-CSRFToken` (embedded via `{{ csrf_token }}`).
- **`{% scolta_search %}` / `{% scolta_config_json %}` escape the emitted JSON
  for script context** (`templatetags/scolta.py`). `json.dumps` + `mark_safe`
  did not escape `</script>`, so a config value containing it broke out of the
  inline script block. `<`, `>`, `&` are now `\uXXXX`-escaped (Django
  `json_script` semantics).

### Fixed
- **Emitted endpoints honour `SCOLTA["route_prefix"]`** (and sub-path
  mounting). The browser config hardcoded `/api/scolta/v1/...` while `urls.py`
  registers the routes under the configurable prefix — any custom prefix made
  the widget POST to 404s. The template tags now build the endpoints with
  `reverse()`, and a widget-mount contract test consumes the EMITTED config
  (container, wasmPath, endpoints all live) — the Jest mount tests in
  scolta-python never see Django's emission.
- **The Wagtail rebuild form ships a real CSRF token** (`wagtail_hooks.py`).
  It rendered `csrfmiddlewaretoken value=""`, so with `CsrfViewMiddleware`
  (every real deployment) the Rebuild button 403ed. The token comes from
  `django.middleware.csrf.get_token(request)`; tests now run the middleware
  stack (`MIDDLEWARE` added to `tests/settings.py` — its absence is why this
  was never caught).
- **The auto-rebuild debounce actually coalesces on the default inline
  dispatch** (`tasks.py`). `trigger_rebuild`'s first act was deleting the
  debounce key that `schedule_rebuild` had just set, so every save ran a full
  synchronous rebuild; the documented coalescing only ever passed in tests
  because `_dispatch` was monkeypatched. Inline dispatch is now deliberate
  leading-edge: the window stays open for `auto_rebuild_delay`, and saves
  within it stay pending in the tracker for the next rebuild. Queue
  integrations point their job at the new `run_scheduled_rebuild()`, which
  clears the window before building so edits landing mid-job schedule a fresh
  rebuild. Tested through the production dispatch path.
- **The Wagtail admin rebuild routes through the dispatch mechanism and
  reports failures distinctly** (`wagtail_hooks.py`, `tasks.py`).
  `trigger_rebuild` returned False for both "build failed" and "nothing to
  index"; it now returns the build report (or None for no content), the admin
  button goes through `rebuild_via_dispatch()` (queue-wired projects don't run
  a full rebuild inside the request), and the panel shows "Build failed:
  <error>" / "Nothing to index." / "Rebuild dispatched." separately.
- **Fail-closed settings** (`conf.py`). An unresolvable `SCOLTA["models"]`
  label now raises `ImproperlyConfigured` (at startup, via `apps.ready()`)
  instead of being silently skipped — a typo meant that content was never
  indexed with no signal. The blanket `except Exception: pass` around the
  Amazee config overlay is gone; `config_overrides()` already guards the
  expected missing-table case narrowly.

### Added
- **`scolta_django.staticfiles.ScoltaAssetFinder`** — exposes the `scolta`
  package's vendored browser runtime to `collectstatic`/dev-server static
  serving under `scolta/` (the default `asset_url` previously required
  hand-copying files out of site-packages). README documents the finder, the
  `asset_url` setting, and the `SCOLTA["wagtail"]` opt-in flag.
- **PEP 561 `py.typed` marker**; verified shipped in the wheel.
- `SearchableMixin` prefers `get_absolute_url()` over the table-name URL.
- CI matrix extended: Python 3.13 and a Django axis (4.2 floor — previously
  untested — paired with Wagtail 6.3 LTS, and 5.2).

### Changed
- Version split-brain resolved: the project version is single-sourced from
  `src/scolta_django/__init__.py` via `[tool.hatch.version]` (pyproject said
  `1.0.0` while `__version__` said `1.0.4.dev0`).
- The app config class is `ScoltaDjangoConfig` (no longer shadows
  `scolta.config.ScoltaConfig`); the inert `default_app_config` is gone; the
  dead `--sync` flag of `manage.py scolta_build` is removed (the command is
  synchronous regardless); `_body()` is shared between the view modules
  (`scolta_django/http.py`).
- Lint posture mirrors scolta-python: `ruff format` enforced in CI
  (`--check`), select extended with `C4`, `SIM`, `RET`, `RUF` (migrations
  ignore `RUF012`), CI lints the whole tree.
- **The health endpoint now returns status-only to anonymous callers.**
  `GET /api/scolta/v1/health` previously exposed the full diagnostic payload
  (AI provider, configured flags, index state) to anyone. Monitoring endpoints
  keep working: anonymous requests still get HTTP 200 with
  `{"status": "ok"|"degraded"}` (the status is still computed from the full
  report, so degradation remains visible to uptime monitors). The detail moved
  behind admin: an active staff user — the `staff_member_required` bar, without
  the login redirect that would break monitors. Matches the status-only
  anonymous shape of the WordPress, Laravel, and Drupal adapters.

## [1.0.0] - 2026-06-08

### Fixed
- **`{% scolta_search %}` now emits `container` and a full WASM glue-module
  `wasmPath`, so the browser search widget actually mounts.** Root cause: the
  template tag omitted the `container` key entirely and left `wasmPath` at the
  empty string `to_browser_config()` returns (the old `setdefault` could never
  fill an already-present key). `scolta.js` auto-init bails unless
  `window.scolta.container` names a mount point, and it loads WASM via
  `import(wasmPath)` against the glue module (`…/wasm/scolta_core.js`) — so the
  widget silently never initialized (no box, no results, no facets, no console
  error). The tag now emits `container: "#<id>"` and
  `wasmPath: …/wasm/scolta_core.js`, restoring parity with the WordPress and
  Laravel adapters. Added a regression test asserting both are present and that
  the `container` selector matches the rendered container `<div>` id.
- **`{% scolta_search %}` asset tags now carry a cache-bust query param.**
  Drupal auto-appends `?v=<core version>` to library assets and WordPress
  appends `?ver=<filemtime>`, but the Django adapter served
  `…/css/scolta.css` and `…/js/scolta.js` with no version param — so a changed
  asset could be served stale from HTTP cache. Both tags now carry `?v=<token>`
  where the token is the served asset file's mtime (content-derived, so a dev
  rebuild busts the cache — matching WP's `filemtime` rationale), falling back
  to the `scolta` package version when the file cannot be stat'd.

Initial Django adapter for the `scolta` Python binding.

- `SearchableMixin` + settings-driven model registry; `ScoltaTracker` change
  model; `DjangoContentSource` over the ORM.
- `post_save`/`post_delete` signals → tracker + debounced (cache.add) rebuild;
  pluggable dispatch (`_dispatch`) for Celery/RQ, inline by default.
- `scolta_build` management command (--force/--sync/--incremental/--resume/--restart/
  --memory-budget/--chunk-size).
- AI proxy views (expand-query/summarize/followup) + health, under the
  configurable route prefix; `DjangoAiService`, `DjangoCacheDriver`.
- `{% scolta_search %}` / `{% scolta_config_json %}` template tags.
- 22 pytest-django tests; ruff clean.

## Phase 10 — Wagtail module

- Optional `scolta_django.wagtail` module (imported only when Wagtail is
  installed): live page-tree enumeration, StreamField/searchable content
  extraction via `get_searchable_content()` (falling back to the title for
  contentless pages), canonical URLs via `get_full_url()`, `WagtailContentSource`
  (indexes ORM models + live pages), and publish/unpublish signal wiring into
  the tracker + debounced rebuild.
- `wagtail_hooks.py`: admin menu item + a panel view to trigger a build and show
  index status (Release Gate #4 — the panel renders the SAVED config value).
- `content_source.get_content_source()` factory selects the Wagtail source when
  `SCOLTA['wagtail']` is enabled; the build command + rebuild task use it.
- Wagtail is an optional `[wagtail]` extra. +9 tests; 31 total, ruff clean.

## Phase 11 — end-to-end demo + verification

- `example/` — a runnable Django demo: a Searchable `blog.Post` model, a
  `seed_demo` command, a search page using `{% scolta_search %}`, and URL wiring
  that serves the built Pagefind index (`/pagefind/`) and the vendored WASM/JS/CSS
  assets (`/scolta-assets/`).
- Fixed the Wagtail gate to use `apps.is_installed("wagtail")` (importing
  wagtail.models requires the app to be installed, not merely importable), so
  the adapter works in plain-Django projects that have Wagtail in the venv.
- Verified end-to-end (headless): migrate → seed → `scolta_build` (6-page index)
  → search page renders with `window.scolta` + pagefindPath; the index,
  `pagefind-entry.json`, `scolta.js`, and `scolta_core_bg.wasm` are served;
  AI endpoints respond (graceful no-key); editing a post auto-rebuilds the index
  and the new content appears in a fragment.

## Amazee.ai integration

- `amazee.py` — `DjangoConfigStorage` (model-backed singleton credentials),
  `config_overrides()` (Amazee creds → OpenAI-compatible config when no explicit
  key), `maybe_auto_provision()` (first-request trial provisioning when
  `ai_provider="amazee"`).
- `ScoltaAmazeeConfig` model + migration; `scolta_amazee_provision` management
  command (`--email`, `--force`).
- `conf.scolta_config()` layers Amazee overrides on top of settings (explicit
  key always wins); `DjangoAiService` converts budget-exhausted errors to
  `AmazeeBudgetExceededException`; AI views auto-provision when configured.
- 11 new tests (storage, overrides, command, auto-provision, budget hook);
  42 total, ruff clean.
