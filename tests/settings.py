import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="scolta-django-test-"))
BASE_DIR = _TMP

SECRET_KEY = "test-secret-key"
DEBUG = True
USE_TZ = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "taggit",
    "wagtail",
    "scolta_django",
    "tests.testapp",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# scolta_django and testapp create tables directly from models (no migration
# files needed for tests); Wagtail/taggit run their real migrations (they create
# the root page and default Site).
MIGRATION_MODULES = {"scolta_django": None, "testapp": None}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

ROOT_URLCONF = "tests.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {},
}]

WAGTAIL_SITE_NAME = "Test Site"

SCOLTA = {
    "ai_api_key": "",
    "site_name": "Test Site",
    "indexer": "auto",
    "models": ["testapp.Post"],
    "wagtail": True,
    "output_dir": str(_TMP / "out"),
    "state_dir": str(_TMP / "state"),
    "auto_rebuild": True,
    "auto_rebuild_delay": 300,
    "route_prefix": "api/scolta/v1",
}
