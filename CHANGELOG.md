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
