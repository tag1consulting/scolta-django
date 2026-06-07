"""Wagtail integration tests (Phase 10).

Exercises page-tree enumeration, StreamField/searchable content extraction,
canonical URL resolution, the Wagtail content source, publish/unpublish signal
wiring, and the admin status surface (Release Gate #4 — saved value rendered)."""

import pytest
from django.test import RequestFactory
from scolta.content import ContentItem

from scolta_django import wagtail as scolta_wagtail
from scolta_django.content_source import get_content_source
from scolta_django.models import ACTION_DELETE, ACTION_INDEX, ScoltaTracker

from .testapp.models import Post


def _make_page(title="My Wagtail Article", slug="my-wagtail-article"):
    from wagtail.models import Page

    root = Page.get_first_root_node()
    page = Page(title=title, slug=slug)
    root.add_child(instance=page)
    page.save_revision().publish()
    page.refresh_from_db()
    return page


@pytest.mark.django_db
def test_page_to_content_item():
    page = _make_page()
    item = scolta_wagtail.page_to_content_item(page)
    assert isinstance(item, ContentItem)
    assert item.title == "My Wagtail Article"
    assert item.url.endswith("/my-wagtail-article/")
    assert "My Wagtail Article" in item.body_html  # from get_searchable_content()
    assert item.id == f"wagtail-page-{page.pk}"
    assert item.date  # last_published_at populated


@pytest.mark.django_db
def test_mixin_derives_language_from_wagtail_locale():
    """SearchableMixin default derives the per-page filter language from a
    Wagtail locale. Regression for the all-`en` index bug (every page indexed
    as the ContentItem default, collapsing the language filter to one bucket)."""
    from wagtail.models import Locale

    de, _ = Locale.objects.get_or_create(language_code="de")
    post = Post.objects.create(title="Artikel", body="Inhalt")
    post.locale = de  # multilingual pages carry a locale; the mixin reads it
    item = post.to_searchable_content()
    assert item.language == "de"


@pytest.mark.django_db
def test_mixin_default_language_without_locale():
    """A plain Django model without `.locale` keeps the ContentItem default."""
    post = Post.objects.create(title="Plain", body="body")
    assert getattr(post, "locale", None) is None
    item = post.to_searchable_content()
    assert item.language == "en"  # ContentItem default


@pytest.mark.django_db
def test_live_pages_excludes_root():
    page = _make_page()
    pks = {p.pk for p in scolta_wagtail.live_pages()}
    assert page.pk in pks
    # The depth-1 root node is excluded.
    from wagtail.models import Page

    assert Page.get_first_root_node().pk not in pks


@pytest.mark.django_db
def test_wagtail_content_source_includes_pages_and_models():
    _make_page()
    Post.objects.create(title="A Post", body="post body")
    items = list(get_content_source().get_published_content())
    titles = {i.title for i in items}
    assert "My Wagtail Article" in titles
    assert "A Post" in titles


def test_get_content_source_is_wagtail_when_enabled():
    from scolta_django.wagtail import WagtailContentSource

    assert isinstance(get_content_source(), WagtailContentSource)


@pytest.mark.django_db
def test_publish_signal_tracks_index(dispatch_calls):
    page = _make_page()  # publish() fires page_published -> tracker
    rec = ScoltaTracker.objects.get(content_id=str(page.pk),
                                    content_type=scolta_wagtail.WAGTAIL_CONTENT_TYPE)
    assert rec.action == ACTION_INDEX


@pytest.mark.django_db
def test_unpublish_signal_tracks_delete(dispatch_calls):
    page = _make_page()
    ScoltaTracker.objects.all().delete()
    page.unpublish()
    rec = ScoltaTracker.objects.get(content_id=str(page.pk),
                                    content_type=scolta_wagtail.WAGTAIL_CONTENT_TYPE)
    assert rec.action == ACTION_DELETE


@pytest.mark.django_db
def test_admin_status_reflects_saved_config():
    # Release Gate #4: the admin panel reflects the SAVED settings value.
    status = scolta_wagtail.admin_status()
    assert status["site_name"] == "Test Site"
    assert status["indexer"] == "auto"
    assert status["index_exists"] is False
    assert status["pending_changes"] == ScoltaTracker.pending_count()


@pytest.mark.django_db
def test_admin_view_renders_saved_value():
    from scolta_django.wagtail_hooks import scolta_admin_view

    resp = scolta_admin_view(RequestFactory().get("/admin/scolta/"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Scolta Search" in body
    assert "Test Site" in body  # saved site_name round-trips into the panel


def test_admin_url_hook_registered():
    from scolta_django.wagtail_hooks import register_admin_urls

    urls = register_admin_urls()
    assert any(u.name == "scolta_admin" for u in urls)
