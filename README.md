# scolta-django

Scolta AI Search for Django — zero-infrastructure AI-powered search with
[Pagefind](https://pagefind.app/). The Django adapter over the
[`scolta`](../scolta-python) Python binding.

## Install & configure

```python
# settings.py
INSTALLED_APPS = [..., "scolta_django"]

SCOLTA = {
    "ai_api_key": env("SCOLTA_API_KEY"),
    "ai_provider": "anthropic",
    "site_name": "My Site",
    "indexer": "auto",                 # pure-Python indexer (default)
    "models": ["blog.Post", "pages.Page"],   # models using SearchableMixin
    "output_dir": BASE_DIR / "static" / "scolta-pagefind",
    "state_dir": BASE_DIR / ".scolta-state",
    "auto_rebuild": True,              # debounced rebuild on model save/delete
    "auto_rebuild_delay": 300,
    "route_prefix": "api/scolta/v1",
}
```

```python
# urls.py
urlpatterns = [..., path("", include("scolta_django.urls"))]
```

Make a model searchable:

```python
from scolta_django.searchable import SearchableMixin

class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField()
    # Override for HTML content / custom URLs:
    def to_searchable_content(self):
        from scolta.content import ContentItem
        return ContentItem(id=f"post-{self.pk}", title=self.title,
                           body_html=self.body, url=self.get_absolute_url(),
                           date=self.updated_at.strftime("%Y-%m-%d"))
```

Build the index and render the widget:

```sh
python manage.py scolta_build          # --force --incremental --resume --restart
```

```django
{% load scolta %}{% scolta_search %}
```

## Static assets

The browser runtime (scolta.js/css, the WASM scoring engine, the Pagefind
runtime) is vendored inside the `scolta` package, where no default
staticfiles finder looks. Add the bundled finder so `collectstatic` (and the
dev server) serve it at the default `asset_url` (`/static/scolta/`):

```python
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "scolta_django.staticfiles.ScoltaAssetFinder",
]
```

Settings:

- `SCOLTA["asset_url"]` (default `/static/scolta/`) — base URL the
  `{% scolta_search %}` tag uses for the CSS/JS/WASM tags. Point it elsewhere
  if you serve the bundle from a CDN or copy it yourself.
- `SCOLTA["amazee_access"]` (optional) — callable `(request) -> bool` gating
  the Amazee.ai settings page and JSON endpoints. Default: active staff user.

## Health endpoint

`GET /api/scolta/v1/health` always answers monitoring tools: anonymous requests
get `{"status": "ok"}` (or `"degraded"`), HTTP 200. The full diagnostic payload
(AI provider, configured flags, index state) requires an active staff user —
the same bar as `staff_member_required`, without the login redirect that would
break uptime monitors.

## Wagtail

If Wagtail is installed, the optional `scolta_django.wagtail` module is loaded
automatically (StreamField extraction, page-tree enumeration, admin panel).
Indexing Wagtail pages is opt-in: set `SCOLTA["wagtail"] = True` to use the
Wagtail content source, which indexes live public pages alongside the
configured models. With the flag unset, only `SCOLTA["models"]` are indexed
(the admin panel and signal wiring load either way).

## Development

```sh
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest
```
