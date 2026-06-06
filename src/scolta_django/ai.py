"""Django AI service adapter.

Django has no framework-native AI SDK, so the dual-path hooks return None and
the built-in scolta AiClient (Anthropic / OpenAI-compatible) is used. When using
the Amazee.ai gateway, a budget-exhausted error is converted to
AmazeeBudgetExceededException (mirrors the Laravel adapter).
"""

from __future__ import annotations

from scolta.ai.amazee import AmazeeBudgetExceededException
from scolta.ai.service import AiServiceAdapter

_BUDGET_MESSAGE = "Budget has been exceeded!"


class DjangoAiService(AiServiceAdapter):
    def _handle_possible_budget_exception(self, exc: RuntimeError) -> None:
        if _BUDGET_MESSAGE in str(exc):
            raise AmazeeBudgetExceededException(exc)
