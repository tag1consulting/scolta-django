"""scolta-django adapter tests (pytest-django)."""

import json

import pytest
from django.test import Client
from scolta.content import ContentItem

from scolta_django import conf, tasks
from scolta_django.content_source import DjangoContentSource
from scolta_django.models import ACTION_DELETE, ACTION_INDEX, ScoltaTracker

from .testapp.models import Post

# -- Config resolution --------------------------------------------------------


def test_config_from_settings():
    config = conf.scolta_config()
    assert config.site_name == "Test Site"
    assert config.indexer == "auto"


def test_models_resolve():
    assert Post in conf.models()


def test_state_and_output_dirs():
    assert conf.state_dir().endswith("state")
    assert conf.output_dir().endswith("out")


# -- Tracker model ------------------------------------------------------------


@pytest.mark.django_db
def test_tracker_track_is_upsert():
    ScoltaTracker.track("1", "testapp.Post", ACTION_INDEX)
    ScoltaTracker.track("1", "testapp.Post", ACTION_INDEX)
    assert ScoltaTracker.objects.count() == 1
    ScoltaTracker.track("1", "testapp.Post", ACTION_DELETE)
    assert ScoltaTracker.objects.get(content_id="1").action == ACTION_DELETE


@pytest.mark.django_db
def test_tracker_pending_and_clear():
    ScoltaTracker.track("1", "testapp.Post", ACTION_INDEX)
    ScoltaTracker.track("2", "testapp.Post", ACTION_DELETE)
    assert ScoltaTracker.pending_count() == 2
    assert ScoltaTracker.pending(ACTION_DELETE).count() == 1
    ScoltaTracker.clear_all()
    assert ScoltaTracker.pending_count() == 0


# -- Searchable + content source ---------------------------------------------


@pytest.mark.django_db
def test_searchable_default_content():
    post = Post.objects.create(title="Hello", body="World body text")
    item = post.to_searchable_content()
    assert isinstance(item, ContentItem)
    assert item.title == "Hello"
    assert "World body text" in item.body_html
    assert item.id == f"testapp_post-{post.pk}"


@pytest.mark.django_db
def test_content_source_published():
    Post.objects.create(title="A", body="aaa")
    Post.objects.create(title="B", body="bbb")
    items = list(DjangoContentSource().get_published_content())
    assert len(items) == 2
    assert {i.title for i in items} == {"A", "B"}
    assert DjangoContentSource().get_total_count() == 2


@pytest.mark.django_db
def test_content_source_changed_and_deleted():
    p = Post.objects.create(title="Changed", body="x")
    ScoltaTracker.objects.all().delete()  # clear save-signal records
    ScoltaTracker.track(str(p.pk), "testapp.Post", ACTION_INDEX)
    ScoltaTracker.track("99", "testapp.Post", ACTION_DELETE)
    changed = list(DjangoContentSource().get_changed_content())
    assert [i.title for i in changed] == ["Changed"]
    assert DjangoContentSource().get_deleted_ids() == ["99"]


# -- Signals + debounce -------------------------------------------------------


@pytest.mark.django_db
def test_save_tracks_index(dispatch_calls):
    post = Post.objects.create(title="Tracked", body="x")
    rec = ScoltaTracker.objects.get(content_id=str(post.pk))
    assert rec.action == ACTION_INDEX
    assert len(dispatch_calls) == 1  # rebuild scheduled once


@pytest.mark.django_db
def test_unpublished_save_tracks_delete(dispatch_calls):
    post = Post.objects.create(title="Draft", body="x", published=False)
    assert ScoltaTracker.objects.get(content_id=str(post.pk)).action == ACTION_DELETE


@pytest.mark.django_db
def test_delete_tracks_delete(dispatch_calls):
    post = Post.objects.create(title="Gone", body="x")
    pk = str(post.pk)
    post.delete()
    assert ScoltaTracker.objects.get(content_id=pk).action == ACTION_DELETE


@pytest.mark.django_db
def test_debounce_coalesces(dispatch_calls):
    Post.objects.create(title="One", body="x")
    Post.objects.create(title="Two", body="y")
    Post.objects.create(title="Three", body="z")
    # Three saves within the debounce window -> a single dispatch.
    assert len(dispatch_calls) == 1


@pytest.mark.django_db
def test_schedule_rebuild_disabled(settings, dispatch_calls):
    settings.SCOLTA = {**settings.SCOLTA, "auto_rebuild": False}
    assert tasks.schedule_rebuild() is False
    assert dispatch_calls == []


# -- AI views -----------------------------------------------------------------


@pytest.mark.django_db
def test_expand_query_no_api_key_graceful():
    # No API key configured -> graceful degradation (terms = [query]).
    resp = Client().post("/api/scolta/v1/expand-query", data=json.dumps({"query": "chocolate cake"}),
                         content_type="application/json")
    assert resp.status_code == 200
    assert resp.json()["terms"] == ["chocolate cake"]


def test_expand_query_empty_is_400():
    resp = Client().post("/api/scolta/v1/expand-query", data=json.dumps({"query": ""}),
                         content_type="application/json")
    assert resp.status_code == 400


def test_summarize_no_api_key_returns_empty():
    resp = Client().post("/api/scolta/v1/summarize",
                         data=json.dumps({"query": "q", "context": "some context"}),
                         content_type="application/json")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_followup_no_api_key():
    resp = Client().post("/api/scolta/v1/followup",
                         data=json.dumps({"messages": [{"role": "user", "content": "hi"}]}),
                         content_type="application/json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == ""
    assert body["remaining"] == 0


def test_health_endpoint():
    resp = Client().get("/api/scolta/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "index_exists" in body


def test_invalid_json_is_400():
    resp = Client().post("/api/scolta/v1/expand-query", data="not json",
                         content_type="application/json")
    assert resp.status_code == 400


# -- Build command ------------------------------------------------------------


@pytest.mark.django_db
def test_scolta_build_command(tmp_path, settings):
    settings.SCOLTA = {**settings.SCOLTA, "output_dir": str(tmp_path / "out"),
                       "state_dir": str(tmp_path / "state")}
    Post.objects.create(title="Indexed Post", body="A sufficiently long body for indexing purposes here.")
    Post.objects.create(title="Another Post", body="More body content that is also long enough to index.")
    ScoltaTracker.objects.all().delete()

    from django.core.management import call_command

    call_command("scolta_build")

    frag_dir = tmp_path / "out" / "pagefind" / "fragment"
    assert frag_dir.is_dir()
    assert len(list(frag_dir.glob("*.pf_fragment"))) == 2
    assert (tmp_path / "out" / "pagefind" / "pagefind-entry.json").exists()


# -- Template tag -------------------------------------------------------------


def test_search_template_tag_renders():
    from django.template import Context, Template

    out = Template("{% load scolta %}{% scolta_search %}").render(Context({}))
    assert 'id="scolta-search"' in out
    assert "window.scolta" in out
    assert "scolta.js" in out
    assert "Test Site" in out  # site name from browser config


def test_search_template_tag_appends_cache_bust():
    """Both asset tags carry a non-empty ?v= cache-bust param.

    Drupal/WP append a version to library assets; the Django adapter must too,
    or a changed asset can be served stale from HTTP cache.
    """
    import re

    from django.template import Context, Template

    out = Template("{% load scolta %}{% scolta_search %}").render(Context({}))
    css = re.search(r'href="[^"]*scolta\.css\?v=([^"&]+)"', out)
    js = re.search(r'src="[^"]*scolta\.js\?v=([^"&]+)"', out)
    assert css is not None, f"scolta.css link missing a ?v= param: {out!r}"
    assert js is not None, f"scolta.js script missing a ?v= param: {out!r}"
    assert css.group(1), "scolta.css ?v= param is empty"
    assert js.group(1), "scolta.js ?v= param is empty"


def _extract_window_scolta(rendered: str) -> dict:
    """Pull the `window.scolta = {...};` object out of rendered tag output."""
    import re

    m = re.search(r"window\.scolta\s*=\s*(\{.*?\});", rendered, re.DOTALL)
    assert m is not None, f"window.scolta assignment not found in: {rendered!r}"
    return json.loads(m.group(1))


def test_search_tag_emits_container_and_wasm_glue_path():
    """Regression: the browser config must name a mount point and the full
    WASM glue module, or scolta.js silently never mounts the widget.

    scolta.js auto-init bails unless ``window.scolta.container`` is set, and it
    loads WASM via ``import(wasmPath)`` where ``wasmPath`` must be the glue
    module (``…/wasm/scolta_core.js``), not the directory. The Django adapter
    previously emitted neither correctly — it omitted ``container`` entirely and
    pointed ``wasmPath`` at the ``…/wasm/`` directory — so the widget never
    initialized (no box, no results, no facets, no console error). This asserts
    parity with the WP/Laravel adapters, which both emit these correctly.
    """
    import re

    from django.template import Context, Template

    out = Template("{% load scolta %}{% scolta_search %}").render(Context({}))
    config = _extract_window_scolta(out)

    assert config["container"] == "#scolta-search"
    assert config["wasmPath"].endswith("/wasm/scolta_core.js")

    # The container selector and the rendered div id must not drift apart.
    div = re.search(r'<div id="([^"]+)"', out)
    assert div is not None, f"search container div not found in: {out!r}"
    assert config["container"] == f"#{div.group(1)}"


def test_search_tag_container_tracks_custom_id():
    """A custom container_id flows into both the div and the config selector."""
    from django.template import Context, Template

    out = Template(
        '{% load scolta %}{% scolta_search "my-search" %}'
    ).render(Context({}))
    config = _extract_window_scolta(out)
    assert config["container"] == "#my-search"
    assert 'id="my-search"' in out


def test_config_json_tag():
    from django.template import Context, Template

    out = Template("{% load scolta %}{% scolta_config_json %}").render(Context({}))
    assert json.loads(out)["siteName"] == "Test Site"
