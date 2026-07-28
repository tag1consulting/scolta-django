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

    # Filter sidebar: hide a facet value with no results for the current query,
    # and drop a filter group whose values are all zero. An active (checked)
    # value stays visible so it can be unchecked. Set False to render every
    # value, showing a zero-count one as a disabled "(0)" row.
    "hide_empty_facets": True,

    # Ranking: weight each partial match by how rare its term is in the corpus,
    # so a match on a rare intent-bearing term outranks a match on a ubiquitous
    # one. The defaults below are the browser's own, so omit them unless tuning.
    "specificity_weighting": True,     # False restores flat sub-query weighting
    "specificity_floor": 0.15,         # floor for a ubiquitous term's weight (0-1)
    "specificity_strong_match": 0.55,  # specificity counting as a strong hit (0-1)
    # Co-occurrence: a page agreeing with several query terms outranks one that
    # spikes on a single rare word.
    "specificity_cooccurrence": 0.9,   # bonus multiplier (0-5); 0 disables
    "specificity_agreement_gate": 0.45,   # specificity a term needs to count (0-1)
    "specificity_agreement_decay": 1.0,   # factor per successive agreeing term

    # Search as you type: a suggestions dropdown while someone types. The full
    # search (AI expansion, summary, follow-ups) still runs only on Enter, on the
    # search button, or on picking a suggestion. On by default, and no index
    # rebuild is needed. The defaults below are the browser's own, so omit them
    # unless tuning; sayt_enabled False restores the previous search box exactly.
    "sayt_enabled": True,
    "sayt_min_chars": 2,               # graphemes typed before suggesting; CJK wants 1
    "sayt_debounce_ms": 150,           # typing pause before suggestions are fetched
    "sayt_max_suggestions": 6,         # also the cap on index reads per pass
    "sayt_recent_searches": True,      # the visitor's own, from their browser storage
    "sayt_max_recent": 3,
    "sayt_expand": True,               # enrich suggestions with AI query expansion
    "sayt_expand_per_minute": 6,       # shares the AI budget with committed searches
    "sayt_expansion_delay_ms": 500,    # idle delay before an AI call, longer than above
    "sayt_suggestion_action": "navigate",  # or "search" to run the full search
}
```

Every core `scolta` config key is accepted here: the whole `SCOLTA` dict is handed
to `ScoltaConfig.from_dict()`, which ignores keys it does not recognise. See
[scolta-python's `docs/CONFIG_REFERENCE.md`](https://github.com/tag1consulting/scolta-python/blob/main/docs/CONFIG_REFERENCE.md)
for the full list and defaults.

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
