# scolta-django — conventions

Django adapter over the `scolta` Python binding (`../scolta-python`), modeled on
`../scolta-laravel`. The pure-Python indexer is the default.

- Config: a single `SCOLTA` dict in Django settings (snake_case scolta keys +
  adapter keys: models, state_dir, output_dir, auto_rebuild[_delay],
  route_prefix). `conf.scolta_config()` builds a `ScoltaConfig`.
- Searchable models use `SearchableMixin` and are listed in `SCOLTA["models"]`.
- Auto-rebuild is debounced via `cache.add`; dispatch is pluggable (`tasks._dispatch`)
  so projects can wire Celery/RQ. Mass `QuerySet.update()` bypasses signals —
  run `manage.py scolta_build` after bulk ops.
- No AI attribution anywhere. Tests use pytest-django.
