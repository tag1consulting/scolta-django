"""Optional Wagtail integration for scolta-django.

Imported by apps.ready() only if Wagtail is installed (this module's top-level
``import wagtail.*`` raises ImportError otherwise, which apps.ready() swallows).

Provides: page-tree enumeration of live public pages, StreamField content
extraction via ``get_searchable_content()``, canonical URLs via
``get_full_url()``, a content source that adds Wagtail pages to the index, and
publish/unpublish signal wiring into the change tracker + debounced rebuild.
"""

from __future__ import annotations

from collections.abc import Iterator

from scolta.content import ContentItem
from scolta.html import _hs
from wagtail.models import Page
from wagtail.signals import page_published, page_unpublished

from .. import conf
from ..content_source import DjangoContentSource
from ..models import ACTION_DELETE, ACTION_INDEX, ScoltaTracker
from ..tasks import schedule_rebuild

WAGTAIL_CONTENT_TYPE = "wagtailcore.Page"


def live_pages():
    """Live, public, real (non-root) pages as specific instances."""
    return Page.objects.live().public().filter(depth__gt=1).specific()


def page_to_content_item(page) -> ContentItem | None:
    """Convert a Wagtail page to a ContentItem.

    Body text comes from Wagtail's own ``get_searchable_content()`` (which
    walks StreamField/RichText search fields); the canonical URL comes from
    ``get_full_url()`` (falling back to the relative ``url``)."""
    specific = page.specific

    body_parts: list[str] = []
    if hasattr(specific, "get_searchable_content"):
        try:
            body_parts = [str(x) for x in specific.get_searchable_content() if x]
        except Exception:  # noqa: BLE001 - never let one page break the build
            body_parts = []
    # Fall back to the title so a contentless page (e.g. a section index page)
    # still has body text and is not dropped by the indexer's min-length filter.
    if not body_parts:
        body_parts = [str(specific.title or "")]
    body_text = " ".join(body_parts)
    body_html = f"<p>{_hs(body_text)}</p>" if body_text else ""

    url = specific.get_full_url() or specific.url or f"/{specific.slug}/"

    dt = (
        getattr(specific, "last_published_at", None)
        or getattr(specific, "latest_revision_created_at", None)
        or getattr(specific, "first_published_at", None)
    )
    date = dt.strftime("%Y-%m-%d") if dt else ""

    return ContentItem(
        id=f"wagtail-page-{specific.pk}",
        title=str(specific.title or ""),
        body_html=body_html,
        url=url or "/",
        date=date,
        site_name=conf.site_name(),
    )


class WagtailContentSource(DjangoContentSource):
    """Indexes the configured ORM models AND live Wagtail pages."""

    def get_published_content(self, options: dict | None = None) -> Iterator[ContentItem]:
        yield from super().get_published_content(options)
        for page in live_pages():
            item = page_to_content_item(page)
            if item is not None:
                yield item

    def get_total_count(self, options: dict | None = None) -> int:
        return super().get_total_count(options) + Page.objects.live().public().filter(depth__gt=1).count()


def _on_published(sender, instance, **kwargs) -> None:
    ScoltaTracker.track(str(instance.pk), WAGTAIL_CONTENT_TYPE, ACTION_INDEX)
    schedule_rebuild()


def _on_unpublished(sender, instance, **kwargs) -> None:
    ScoltaTracker.track(str(instance.pk), WAGTAIL_CONTENT_TYPE, ACTION_DELETE)
    schedule_rebuild()


def register() -> None:
    """Connect Wagtail publish/unpublish signals (called from apps.ready())."""
    page_published.connect(_on_published, dispatch_uid="scolta_wagtail_published")
    page_unpublished.connect(_on_unpublished, dispatch_uid="scolta_wagtail_unpublished")


def admin_status() -> dict:
    """Status surface for the Wagtail admin panel — reflects the SAVED config."""
    from scolta.health import HealthChecker

    config = conf.scolta_config()
    health = HealthChecker(config, conf.output_dir(), None, None).check()
    return {
        "site_name": config.site_name,
        "indexer": config.indexer,
        "index_exists": health["index_exists"],
        "ai_configured": health["ai_configured"],
        "pending_changes": ScoltaTracker.pending_count(),
    }
