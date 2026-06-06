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
