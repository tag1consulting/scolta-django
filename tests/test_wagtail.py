"""Wagtail integration tests (Phase 10).

Exercises page-tree enumeration, StreamField/searchable content extraction,
canonical URL resolution, the Wagtail content source, publish/unpublish signal
wiring, and the admin status surface (Release Gate #4 — saved value rendered)."""

import re

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
    rec = ScoltaTracker.objects.get(
        content_id=str(page.pk), content_type=scolta_wagtail.WAGTAIL_CONTENT_TYPE
    )
    assert rec.action == ACTION_INDEX


@pytest.mark.django_db
def test_unpublish_signal_tracks_delete(dispatch_calls):
    page = _make_page()
    ScoltaTracker.objects.all().delete()
    page.unpublish()
    rec = ScoltaTracker.objects.get(
        content_id=str(page.pk), content_type=scolta_wagtail.WAGTAIL_CONTENT_TYPE
    )
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


# -- rebuild form CSRF (through real middleware) --------------------------------


@pytest.mark.django_db
@pytest.mark.urls("tests.urls_admin")
def test_rebuild_form_embeds_real_csrf_token():
    """Regression: the form shipped csrfmiddlewaretoken value="" — with
    CsrfViewMiddleware active (every real deployment) the Rebuild button 403ed.
    Tested through the middleware stack, whose absence from tests/settings.py
    is why this was never caught."""
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    page = client.get("/admin/scolta/")
    assert page.status_code == 200
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]*)"', page.content.decode())
    assert match, "rebuild form must carry the CSRF token"
    assert match.group(1), "the token must not be empty"


@pytest.mark.django_db
@pytest.mark.urls("tests.urls_admin")
def test_rebuild_button_works_through_csrf_middleware():
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    page = client.get("/admin/scolta/")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]*)"', page.content.decode()).group(1)

    resp = client.post("/admin/scolta/", data={"csrfmiddlewaretoken": token})
    assert resp.status_code == 200

    # And without the token the middleware rejects it (the old empty-token
    # form would have hit this on every real deployment).
    assert Client(enforce_csrf_checks=True).post("/admin/scolta/").status_code == 403


# -- rebuild result messaging ----------------------------------------------------


@pytest.mark.django_db
def test_admin_rebuild_surfaces_build_error_distinctly(monkeypatch):
    """'failed' and 'nothing to index' were conflated into one False."""
    from scolta.index.build_result import StatusReport

    from scolta_django import tasks
    from scolta_django.wagtail_hooks import scolta_admin_view

    failed = StatusReport(
        version="t",
        pagefind_version="t",
        resolved_indexer="python",
        pages_processed=0,
        chunks_written=0,
        peak_memory_bytes=0,
        memory_budget_bytes=0,
        duration_seconds=0.0,
        output_dir="",
        success=False,
        error="disk full",
    )
    monkeypatch.setattr(tasks, "_dispatch", lambda force, delay: failed)
    body = scolta_admin_view(RequestFactory().post("/admin/scolta/")).content.decode()
    assert "Build failed: disk full" in body

    monkeypatch.setattr(tasks, "_dispatch", lambda force, delay: None)
    body = scolta_admin_view(RequestFactory().post("/admin/scolta/")).content.decode()
    assert "Nothing to index." in body

    monkeypatch.setattr(tasks, "_dispatch", lambda force, delay: "queued-job-id")
    body = scolta_admin_view(RequestFactory().post("/admin/scolta/")).content.decode()
    assert "Rebuild dispatched." in body
