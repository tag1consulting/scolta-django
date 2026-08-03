import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolate_rebuild(monkeypatch):
    """Prevent model saves from triggering a real inline rebuild, and record
    dispatch calls so the signals tests can assert debounce behaviour."""
    calls = []
    monkeypatch.setattr(
        "scolta_django.tasks._dispatch", lambda force, delay: calls.append((force, delay))
    )
    cache.clear()
    yield calls


@pytest.fixture
def dispatch_calls(_isolate_rebuild):
    return _isolate_rebuild


@pytest.fixture
def fake_client_class():
    """The recording Amazee client double from the views tests, as a factory.

    Shared so the opt-in tests drive the same canned control plane the view
    tests do, rather than a second one that could drift from it.
    """
    from .test_amazee_views import FakeAmazeeClient

    return FakeAmazeeClient
