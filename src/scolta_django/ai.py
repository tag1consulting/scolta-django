"""Django AI service adapter.

Django has no framework-native AI SDK, so the dual-path hooks return None and
the built-in scolta AiClient (Anthropic / OpenAI-compatible) is used.
"""

from __future__ import annotations

from scolta.ai.service import AiServiceAdapter


class DjangoAiService(AiServiceAdapter):
    """Thin marker subclass; behaviour is the shared AiServiceAdapter."""
