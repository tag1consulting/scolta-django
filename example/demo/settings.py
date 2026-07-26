import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "demo-insecure-key-change-me"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "scolta_django",
    "blog",
]

MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]

ROOT_URLCONF = "demo.urls"

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

STATIC_URL = "/static/"
USE_TZ = True

SCOLTA = {
    # Set SCOLTA_API_KEY in your environment for live AI summaries; without it,
    # search still works (Pagefind ranks) and AI endpoints degrade gracefully.
    "ai_api_key": os.environ.get("SCOLTA_API_KEY", ""),
    "ai_provider": os.environ.get("SCOLTA_AI_PROVIDER", "anthropic"),
    "site_name": "Scolta Django Demo",
    "site_description": "a demo blog",
    "indexer": "auto",  # pure-Python indexer
    "models": ["blog.Post"],
    "output_dir": str(BASE_DIR / "pagefind_index"),
    "state_dir": str(BASE_DIR / ".scolta-state"),
    "pagefind_index_path": "/pagefind",  # browser loads /pagefind/pagefind.js
    "asset_url": "/scolta-assets",  # browser loads /scolta-assets/js/scolta.js
    "auto_rebuild": True,
    "auto_rebuild_delay": 5,  # short window for demoing edit->rebuild
    "route_prefix": "api/scolta/v1",
    # Facet sidebar: hide values with no results for the current query. Set
    # False to render every value, a zero-count one as a disabled "(0)" row.
    "hide_empty_facets": True,
    # Ranking knobs, shown at their defaults. All six are core scolta keys, so
    # they need no adapter plumbing; omit them unless you are tuning.
    "specificity_weighting": True,
    "specificity_floor": 0.15,
    "specificity_strong_match": 0.55,
    "specificity_cooccurrence": 0.9,
    "specificity_agreement_gate": 0.45,
    "specificity_agreement_decay": 1.0,
}
