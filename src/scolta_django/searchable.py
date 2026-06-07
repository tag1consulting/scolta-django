"""Searchable mixin for Django models (mirror of Laravel's Searchable trait).

Add ``SearchableMixin`` to a model and list it in ``SCOLTA['models']``. Provide
``to_searchable_content()`` for precise control; a sensible default reads common
field names. WARNING: the default treats the body field as PLAIN TEXT (it wraps
and escapes it); override the method if your content is HTML.

The default derives the per-page filter ``language`` from a Wagtail ``locale``
(``self.locale.language_code``) when present; plain Django models without a
locale keep the ``ContentItem`` default. NOTE: if you override
``to_searchable_content()`` on a multilingual site, you must pass ``language=``
yourself — otherwise every page indexes as the default language and the language
filter collapses to a single bucket.
"""

from __future__ import annotations

from scolta.content import ContentItem


class SearchableMixin:
    def to_searchable_content(self) -> ContentItem:
        from . import conf

        title = (
            getattr(self, "title", None)
            or getattr(self, "name", None)
            or getattr(self, "subject", None)
            or ""
        )
        body_text = (
            getattr(self, "body", None)
            or getattr(self, "content", None)
            or getattr(self, "description", None)
            or ""
        )
        # Plain-text default: escape and wrap. Override for HTML content.
        from scolta.html import _hs

        body_html = f"<p>{_hs(str(body_text))}</p>" if body_text else ""

        pk = self.pk
        table = self._meta.db_table
        url = f"/{table}/{pk}"

        date_value = (
            getattr(self, "updated_at", None)
            or getattr(self, "created_at", None)
            or getattr(self, "published_at", None)
        )
        date = date_value.strftime("%Y-%m-%d") if date_value else ""

        # Multilingual (Wagtail) pages carry a locale; use it as the per-page
        # filter language so the `language` facet is populated per page rather
        # than collapsing to the ContentItem default. Plain models have no
        # locale and keep the default.
        locale = getattr(self, "locale", None)
        language = getattr(locale, "language_code", "") or ""

        kwargs = {
            "id": f"{table}-{pk}",
            "title": str(title),
            "body_html": body_html,
            "url": url,
            "date": date,
            "site_name": conf.site_name(),
        }
        if language:
            kwargs["language"] = language
        return ContentItem(**kwargs)

    @classmethod
    def searchable_queryset(cls):
        """Records that should appear in search. Override to filter (status, etc.)."""
        return cls._default_manager.all()

    def get_searchable_type(self) -> str:
        """Content-type identifier for the tracker ('app_label.ModelName')."""
        return f"{self._meta.app_label}.{self._meta.object_name}"

    def should_be_searchable(self) -> bool:
        """Whether this instance should be indexed right now. Override to filter."""
        return True
