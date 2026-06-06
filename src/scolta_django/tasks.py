"""Rebuild orchestration + debounced scheduling (mirror of Laravel's
TriggerRebuild / ProcessIndexChunk / FinalizeIndex).

The debounce uses Django's cache (atomic ``cache.add``) so many edits within the
delay window coalesce into a single rebuild. Dispatch is pluggable via
``_dispatch`` so a project can wire Celery/RQ; the default runs the rebuild
inline (best-effort for projects without a queue).
"""

from __future__ import annotations

from django.core.cache import cache
from scolta.index.build_intent import BuildIntent
from scolta.index.orchestrator import IndexBuildOrchestrator

from . import conf
from .content_source import DjangoContentSource

_DEBOUNCE_KEY = "scolta_rebuild_scheduled"


def schedule_rebuild(force: bool = False) -> bool:
    """Debounced rebuild trigger. Returns True if a rebuild was scheduled now."""
    if not conf.auto_rebuild():
        return False
    delay = conf.auto_rebuild_delay()
    # Atomic add: only the first caller within the window schedules.
    if cache.add(_DEBOUNCE_KEY, True, delay):
        _dispatch(force, delay)
        return True
    return False


def _dispatch(force: bool, delay: int) -> None:
    """Hand off the rebuild. Override/monkeypatch to use Celery/RQ with a
    countdown; the default runs inline (no queue)."""
    trigger_rebuild(force)


def trigger_rebuild(force: bool = False) -> bool:
    """Run a full rebuild over all published content. Returns build success."""
    cache.delete(_DEBOUNCE_KEY)
    source = DjangoContentSource()
    config = conf.scolta_config()
    budget = _budget()

    total = source.get_total_count()
    if total == 0:
        return False

    orchestrator = IndexBuildOrchestrator(
        conf.state_dir(), conf.output_dir(),
        hmac_secret=conf.hmac_secret(), language=config.language,
    )
    report = orchestrator.build(
        BuildIntent.fresh(total, budget),
        source.get_published_content(),
        force=force,
    )
    if report.success:
        source.clear_tracker()
    return report.success


def _budget():
    from scolta.memory_budget_config import MemoryBudgetConfig

    return MemoryBudgetConfig.load(conf.get("memory_budget", {}) or {}).to_memory_budget()
