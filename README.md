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
python manage.py scolta_build          # --force --incremental --resume --restart --sync
```

```django
{% load scolta %}{% scolta_search %}
```

## Health endpoint

`GET /api/scolta/v1/health` always answers monitoring tools: anonymous requests
get `{"status": "ok"}` (or `"degraded"`), HTTP 200. The full diagnostic payload
(AI provider, configured flags, index state) requires an active staff user —
the same bar as `staff_member_required`, without the login redirect that would
break uptime monitors.

## Wagtail

If Wagtail is installed, the optional `scolta_django.wagtail` module is loaded
automatically (StreamField extraction, page-tree enumeration, admin panel).

## Development

```sh
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest
```
