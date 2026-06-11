"""Rebuild orchestration + debounced scheduling (mirror of Laravel's
TriggerRebuild / ProcessIndexChunk / FinalizeIndex).

The debounce uses Django's cache (atomic ``cache.add``) so many edits within
the delay window coalesce into a single rebuild. Dispatch is pluggable via
``_dispatch`` so a project can wire Celery/RQ; the default runs the rebuild
inline (best-effort for projects without a queue).

Debounce semantics, by dispatch mode:

- **Inline (the default):** leading-edge. The first save in a window rebuilds
  immediately; further saves within ``auto_rebuild_delay`` only mark the
  tracker (the window key is left to expire — deleting it on rebuild start
  made every save a full synchronous rebuild). Changes saved inside the window
  stay pending in the tracker and are picked up by the next rebuild.
- **Queued (Celery/RQ with ``countdown=delay``):** trailing-edge. Point the
  job at :func:`run_scheduled_rebuild`, which clears the window *before*
  building so an edit landing after the job starts schedules a fresh rebuild
  instead of being silently skipped.
"""

from __future__ import annotations

from django.core.cache import cache
from scolta.index.build_intent import BuildIntent
from scolta.index.build_result import StatusReport
from scolta.index.orchestrator import IndexBuildOrchestrator

from . import conf
from .content_source import get_content_source

_DEBOUNCE_KEY = "scolta_rebuild_scheduled"


def schedule_rebuild(force: bool = False) -> bool:
    """Debounced rebuild trigger. Returns True if a rebuild was dispatched now."""
    if not conf.auto_rebuild():
        return False
    delay = conf.auto_rebuild_delay()
    # Atomic add: only the first caller within the window dispatches.
    if cache.add(_DEBOUNCE_KEY, True, delay):
        _dispatch(force, delay)
        return True
    return False


def _dispatch(force: bool, delay: int):
    """Hand off the rebuild. Override/monkeypatch to enqueue
    ``run_scheduled_rebuild`` on Celery/RQ with ``countdown=delay`` (return
    the job, or True, so admin UIs can report "dispatched"); the default runs
    inline (no queue) and returns the build report."""
    return trigger_rebuild(force)


def rebuild_via_dispatch(force: bool = False):
    """Route an explicit (admin-triggered) rebuild through the configured
    dispatcher, so queue-wired projects don't run it inside the request.

    Returns the dispatcher's result: the inline default gives the
    :class:`StatusReport` (or None for nothing-to-index); queue dispatchers
    give their job handle/True."""
    return _dispatch(force, 0)


def run_scheduled_rebuild(force: bool = False) -> StatusReport | None:
    """Queue-job entry point: clear the debounce window, then rebuild.

    Clearing first means an edit that lands while this job is already running
    opens a new window and schedules its own rebuild — nothing is lost to the
    closing window."""
    cache.delete(_DEBOUNCE_KEY)
    return trigger_rebuild(force)


def trigger_rebuild(force: bool = False) -> StatusReport | None:
    """Run a full rebuild over all published content.

    Returns the build report, or None when there is nothing to index — so
    callers can tell "failed" (``report.success is False``, with
    ``report.error``) from "no content" instead of collapsing both to False.
    """
    source = get_content_source()
    config = conf.scolta_config()
    budget = _budget()

    total = source.get_total_count()
    if total == 0:
        return None

    orchestrator = IndexBuildOrchestrator(
        conf.state_dir(),
        conf.output_dir(),
        hmac_secret=conf.hmac_secret(),
        language=config.language,
    )
    report = orchestrator.build(
        BuildIntent.fresh(total, budget),
        source.get_published_content(),
        force=force,
    )
    if report.success:
        source.clear_tracker()
    return report


def _budget():
    from scolta.memory_budget_config import MemoryBudgetConfig

    return MemoryBudgetConfig.load(conf.get("memory_budget", {}) or {}).to_memory_budget()
