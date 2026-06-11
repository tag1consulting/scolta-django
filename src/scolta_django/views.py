"""AI proxy views + health endpoint.

Mirrors the Laravel controller routes; backed by the shared AiEndpointHandler.
Paths (under the configured route prefix, default api/scolta/v1):
  POST expand-query, POST summarize, POST followup, GET health
"""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from scolta.ai.endpoint import AiEndpointHandler
from scolta.cache import NullCacheDriver
from scolta.health import HealthChecker

from . import conf
from .ai import DjangoAiService
from .cache import DjangoCacheDriver
from .http import parse_json_body as _body


def _make_handler() -> AiEndpointHandler:
    from .amazee import maybe_auto_provision

    maybe_auto_provision()
    config = conf.scolta_config()
    ai = DjangoAiService(config)
    cache = DjangoCacheDriver() if config.cache_ttl > 0 else NullCacheDriver()
    return AiEndpointHandler(
        ai_service=ai,
        cache=cache,
        generation=0,
        cache_ttl=config.cache_ttl,
        max_follow_ups=config.max_follow_ups,
        ai_languages=config.ai_languages,
        ai_expand_query=config.ai_expand_query,
        ai_summarize=config.ai_summarize,
        ai_summary_max_tokens=config.ai_summary_max_tokens,
        expand_primary_weight=config.expand_primary_weight,
        sortable_fields=config.sortable_fields,
        sortable_field_descriptions=config.sortable_field_descriptions,
        filter_fields=config.filter_fields,
        filter_field_descriptions=config.filter_field_descriptions,
    )


def _respond(result: dict) -> JsonResponse:
    if result.get("ok"):
        return JsonResponse(result.get("data", {}), status=200, safe=False)
    resp = JsonResponse({"error": result.get("error", "Error")}, status=result.get("status", 500))
    if "retry_after" in result:
        resp["Retry-After"] = result["retry_after"]
    return resp


@csrf_exempt
@require_POST
def expand_query(request) -> JsonResponse:
    data = _body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    return _respond(_make_handler().handle_expand_query(str(data.get("query", ""))))


@csrf_exempt
@require_POST
def summarize(request) -> JsonResponse:
    data = _body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    return _respond(
        _make_handler().handle_summarize(str(data.get("query", "")), str(data.get("context", "")))
    )


@csrf_exempt
@require_POST
def follow_up(request) -> JsonResponse:
    data = _body(request)
    if data is None:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    return _respond(_make_handler().handle_follow_up(data.get("messages", [])))


@require_GET
def health(request) -> JsonResponse:
    """Health check: status-only for anonymous callers, full detail for staff.

    Uptime monitors always get HTTP 200 with {"status": ...}; the full
    diagnostic payload (provider, configured flags, index state) requires an
    active staff user — the same bar as staff_member_required, without the
    login redirect that would break monitoring tools. The full report is
    always computed first so the trimmed status still reflects degradation.
    """
    checker = HealthChecker(conf.scolta_config(), conf.output_dir(), None, None)
    report = checker.check()
    user = getattr(request, "user", None)
    if user is not None and user.is_active and user.is_staff:
        return JsonResponse(report)
    return JsonResponse({"status": report["status"]})
