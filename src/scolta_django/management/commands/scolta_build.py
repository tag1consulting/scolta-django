"""``manage.py scolta_build`` — build or rebuild the Scolta search index.

Django equivalent of Laravel's ``scolta:build``. The pure-Python indexer is the
default; ``--incremental`` only affects the binary path's export scope (the
token cache provides incrementality automatically on the Python indexer).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from scolta.index.build_intent import BuildIntentFactory
from scolta.index.memory_budget import MemoryBudget
from scolta.index.orchestrator import IndexBuildOrchestrator
from scolta.memory_budget_config import MemoryBudgetConfig

from ... import conf
from ...content_source import get_content_source


class Command(BaseCommand):
    help = "Build or rebuild the Scolta search index."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the token cache and fingerprint; full rebuild.",
        )
        parser.add_argument(
            "--incremental", action="store_true", help="Only process tracked changed content."
        )
        parser.add_argument(
            "--resume", action="store_true", help="Resume an interrupted Python index build."
        )
        parser.add_argument(
            "--restart", action="store_true", help="Discard interrupted state and restart."
        )
        parser.add_argument(
            "--memory-budget",
            dest="memory_budget",
            default=None,
            help="conservative|balanced|aggressive|256M|1G",
        )
        parser.add_argument(
            "--chunk-size", dest="chunk_size", type=int, default=None, help="Pages per chunk."
        )

    def handle(self, *args, **options) -> None:
        config = conf.scolta_config()
        source = get_content_source()
        budget = self._budget(options)

        if options["incremental"]:
            items = source.get_changed_content()
            total = source.get_pending_count()
        else:
            items = source.get_published_content()
            total = source.get_total_count()

        intent = BuildIntentFactory.from_flags(options["resume"], options["restart"], total, budget)

        orchestrator = IndexBuildOrchestrator(
            conf.state_dir(),
            conf.output_dir(),
            hmac_secret=conf.hmac_secret(),
            language=config.language,
        )
        report = orchestrator.build(intent, items, force=options["force"])

        if report.success:
            source.clear_tracker()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Built index: {report.pages_processed} pages, "
                    f"{report.chunks_written} chunks → {conf.output_dir()}/pagefind"
                )
            )
        else:
            self.stderr.write(self.style.ERROR(f"Build failed/aborted: {report.error}"))
            raise SystemExit(1)

    @staticmethod
    def _budget(options) -> MemoryBudget:
        if options.get("memory_budget") or options.get("chunk_size"):
            return MemoryBudget.from_options(
                options.get("memory_budget") or "conservative", options.get("chunk_size")
            )
        return MemoryBudgetConfig.load(conf.get("memory_budget", {}) or {}).to_memory_budget()
