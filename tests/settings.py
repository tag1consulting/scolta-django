import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="scolta-django-test-"))
BASE_DIR = _TMP

SECRET_KEY = "test-secret-key"
DEBUG = True
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "scolta_django",
    "tests.testapp",
]

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# Create tables directly from models (no migration files needed for tests).
MIGRATION_MODULES = {"scolta_django": None, "testapp": None}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

ROOT_URLCONF = "tests.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {},
}]

SCOLTA = {
    "ai_api_key": "",
    "site_name": "Test Site",
    "indexer": "auto",
    "models": ["testapp.Post"],
    "output_dir": str(_TMP / "out"),
    "state_dir": str(_TMP / "state"),
    "auto_rebuild": True,
    "auto_rebuild_delay": 300,
    "route_prefix": "api/scolta/v1",
}
