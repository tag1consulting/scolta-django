"""Django ORM content source (mirror of Laravel's ContentSource)."""

from __future__ import annotations

from collections.abc import Iterator

from django.apps import apps
from scolta.content import ContentItem, ContentSource
from scolta.export import ContentExporter

from . import conf
from .models import ACTION_DELETE, ACTION_INDEX, ScoltaTracker


def get_content_source() -> DjangoContentSource:
    """Return the active content source — WagtailContentSource when Wagtail is
    enabled (``SCOLTA['wagtail']`` truthy) and installed, else the ORM source."""
    if conf.get("wagtail") and apps.is_installed("wagtail"):
        from .wagtail import WagtailContentSource

        return WagtailContentSource()
    return DjangoContentSource()


def _searchable_queryset(model):
    if hasattr(model, "searchable_queryset"):
        return model.searchable_queryset()
    return model._default_manager.all()


def _resolve(content_type: str):
    try:
        return apps.get_model(content_type)
    except (LookupError, ValueError):
        return None


class DjangoContentSource(ContentSource):
    def get_published_content(self, options: dict | None = None) -> Iterator[ContentItem]:
        for model in conf.models():
            for record in _searchable_queryset(model).iterator():
                if not hasattr(record, "to_searchable_content"):
                    continue
                item = record.to_searchable_content()
                if isinstance(item, ContentItem):
                    yield item

    def get_changed_content(self) -> Iterator[ContentItem]:
        by_type: dict[str, list[str]] = {}
        for rec in ScoltaTracker.pending(ACTION_INDEX):
            by_type.setdefault(rec.content_type, []).append(rec.content_id)

        for content_type, ids in by_type.items():
            model = _resolve(content_type)
            if model is None:
                continue
            pk_name = model._meta.pk.name
            for record in model._default_manager.filter(**{f"{pk_name}__in": ids}).iterator():
                if not hasattr(record, "to_searchable_content"):
                    continue
                if hasattr(record, "should_be_searchable") and not record.should_be_searchable():
                    continue
                item = record.to_searchable_content()
                if isinstance(item, ContentItem):
                    yield item

    def get_deleted_ids(self) -> list[str]:
        return list(ScoltaTracker.pending(ACTION_DELETE).values_list("content_id", flat=True))

    def clear_tracker(self) -> None:
        ScoltaTracker.clear_all()

    def get_total_count(self, options: dict | None = None) -> int:
        return sum(_searchable_queryset(model).count() for model in conf.models())

    def get_pending_count(self) -> int:
        return ScoltaTracker.pending_count()

    def mark_all_for_reindex(self) -> int:
        count = 0
        for model in conf.models():
            content_type = f"{model._meta.app_label}.{model._meta.object_name}"
            for record in _searchable_queryset(model).iterator():
                ScoltaTracker.track(str(record.pk), content_type, ACTION_INDEX)
                count += 1
        return count

    def filtered_published_items(self) -> list[ContentItem]:
        """Published items passing the min-content-length filter (for fingerprinting)."""
        exporter = ContentExporter(conf.output_dir())
        return exporter.export_to_items(list(self.get_published_content()))
