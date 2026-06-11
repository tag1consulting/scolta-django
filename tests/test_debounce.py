"""Debounce semantics through the PRODUCTION dispatch path.

The pre-existing coalesce test passed only because conftest monkeypatches
``tasks._dispatch``; in production the old ``trigger_rebuild`` deleted the
debounce key as its first act, so with the default inline dispatch every save
ran a full synchronous rebuild and the documented coalescing never happened.
These tests restore the real dispatcher and stub only the orchestrator.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from scolta.index.build_result import StatusReport
from scolta.index.orchestrator import IndexBuildOrchestrator

from scolta_django import tasks
from tests.testapp.models import Post

# Captured at import time, before conftest's autouse fixture replaces it.
_REAL_DISPATCH = tasks._dispatch


def _report(success=True, error=None):
    return StatusReport(
        version="t",
        pagefind_version="t",
        resolved_indexer="python",
        pages_processed=1,
        chunks_written=1,
        peak_memory_bytes=0,
        memory_budget_bytes=0,
        duration_seconds=0.0,
        output_dir="",
        success=success,
        error=error,
    )


@pytest.fixture
def production_dispatch(monkeypatch):
    """Real inline dispatch; only the actual index build is stubbed."""
    builds = []

    def fake_build(self, intent, pages, logger=None, progress=None, force=False):
        builds.append(force)
        return _report()

    monkeypatch.setattr(tasks, "_dispatch", _REAL_DISPATCH)
    monkeypatch.setattr(IndexBuildOrchestrator, "build", fake_build)
    return builds


@pytest.mark.django_db
def test_inline_dispatch_coalesces_saves(production_dispatch):
    """Three saves within the window -> ONE rebuild (previously three)."""
    Post.objects.create(title="One", body="x")
    Post.objects.create(title="Two", body="y")
    Post.objects.create(title="Three", body="z")
    assert len(production_dispatch) == 1


@pytest.mark.django_db
def test_window_reopens_after_expiry(production_dispatch):
    Post.objects.create(title="One", body="x")
    assert len(production_dispatch) == 1
    # Simulate the window expiring.
    cache.delete(tasks._DEBOUNCE_KEY)
    Post.objects.create(title="Two", body="y")
    assert len(production_dispatch) == 2


@pytest.mark.django_db
def test_run_scheduled_rebuild_clears_window_first(production_dispatch):
    """Queue-job entry point: an edit landing after the job starts must be
    able to schedule a fresh rebuild instead of dying in the closing window."""
    assert tasks.schedule_rebuild() is True
    assert tasks.schedule_rebuild() is False  # window open -> debounced

    tasks.run_scheduled_rebuild()

    assert tasks.schedule_rebuild() is True  # window cleared by the job


@pytest.mark.django_db
def test_trigger_rebuild_distinguishes_no_content_from_failure(monkeypatch, settings):
    # Plain ORM source (the Wagtail root page would otherwise count as content).
    settings.SCOLTA = {**settings.SCOLTA, "wagtail": False}
    # No content at all -> None (not False-meaning-failure).
    assert tasks.trigger_rebuild() is None

    Post.objects.create(title="One", body="x")
    monkeypatch.setattr(
        IndexBuildOrchestrator,
        "build",
        lambda self, *a, **k: _report(success=False, error="disk full"),
    )
    report = tasks.trigger_rebuild()
    assert report is not None
    assert report.success is False
    assert report.error == "disk full"
