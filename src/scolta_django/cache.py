"""Django cache driver for AI endpoint response caching."""

from __future__ import annotations

from typing import Any

from django.core.cache import cache as _django_cache
from scolta.cache import CacheDriver


class DjangoCacheDriver(CacheDriver):
    def get(self, key: str) -> Any:
        return _django_cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        _django_cache.set(key, value, ttl_seconds)
