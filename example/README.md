# Scolta Django demo

A minimal, runnable Django project wired to `scolta-django`. It seeds a few blog
posts, builds a Pagefind index with the pure-Python indexer, and serves a search
page that loads `scolta.js` + the index in the browser.

## Run

```sh
cd packages/scolta-django
uv pip install -e ".[dev]"            # installs scolta + scolta-django + Django (+ Wagtail)
cd example
uv run python manage.py migrate
uv run python manage.py seed_demo     # 6 sample posts
uv run python manage.py scolta_build  # builds pagefind_index/pagefind/
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/search/ and search (try "chocolate dessert",
"crispy vegetables", "tangy bread").

## Pre-release: verify the widget actually mounts

The unit tests assert the emitted `window.scolta` config carries `container` and
a full-glue `wasmPath` (`tests/test_adapter.py`), but CI has no browser, so it
cannot prove `scolta.js` mounts the widget. Before tagging a release, confirm
the live mount against this demo (this is what catches a regression where the
config renders but the box never appears):

```sh
uv run python manage.py runserver
# then, against http://127.0.0.1:8000/search/ :
#   - the search input element exists in the DOM (the widget mounted), and
#   - typing a query returns results with facets,
#   - with no console errors.
```

A headless equivalent (used in the demo CI checks): load `/search/` in a
headless browser and assert `document.querySelector('#scolta-search input')`
is non-null after load — a present `#scolta-search` div with no input inside
means auto-init bailed (missing `container`) or the WASM glue 404'd (wrong
`wasmPath`).

## AI summaries (optional)

Without an API key, search still works and the AI endpoints degrade gracefully
(no summary). For live AI:

```sh
SCOLTA_API_KEY=sk-ant-... uv run python manage.py runserver
```

## Auto-rebuild on edit

`auto_rebuild` is on with a 5-second debounce. Edit a post (shell or admin) and
the index rebuilds automatically (inline here; wire Celery/RQ in production by
overriding `scolta_django.tasks._dispatch`). The token cache means only the
edited page is re-tokenized.

```sh
uv run python manage.py shell -c "from blog.models import Post; p=Post.objects.first(); p.body+='<p>fresh edit</p>'; p.save()"
```
