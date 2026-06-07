import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _isolate_rebuild(monkeypatch):
    """Prevent model saves from triggering a real inline rebuild, and record
    dispatch calls so the signals tests can assert debounce behaviour."""
    calls = []
    monkeypatch.setattr("scolta_django.tasks._dispatch", lambda force, delay: calls.append((force, delay)))
    cache.clear()
    yield calls


@pytest.fixture(autouse=True)
def _no_network_provision(monkeypatch):
    """Keep AI-view tests hermetic. The AI endpoints now lazily auto-provision a
    free Amazee trial whenever no API key is configured (Bug C: key gate, not
    provider gate), so an un-stubbed view test would attempt a real network
    provisioning call. Stub the view's trigger to a no-op. The Amazee unit tests
    import ``maybe_auto_provision`` directly and inject a fake client, so they
    bind the real function and are unaffected by patching the module attribute."""
    monkeypatch.setattr("scolta_django.amazee.maybe_auto_provision", lambda *a, **k: False)


@pytest.fixture
def dispatch_calls(_isolate_rebuild):
    return _isolate_rebuild
