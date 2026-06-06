# Changelog

## [Unreleased]

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
