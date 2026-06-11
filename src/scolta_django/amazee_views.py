"""Amazee.ai admin/upgrade endpoints (Django port of AmazeeSettingsController).

Stateless JSON flow (the admin UI holds the short-lived session token between
steps, so no server session is required):

    GET  scolta/amazee/status
    POST scolta/amazee/provision        {email?}            -> free trial
    POST scolta/amazee/request-code     {email}             -> send OTP
    POST scolta/amazee/sign-in          {email, code}       -> {session_token}
    POST scolta/amazee/regions          {session_token}     -> {regions}
    POST scolta/amazee/upgrade          {session_token, region_id} -> private key
    POST scolta/amazee/disconnect                            -> clear credentials

A rendered settings page (Alpine.js, driving the JSON endpoints above) is served
at ``scolta/amazee/`` via :func:`settings_page`.

Every endpoint (and the page) requires an admin user: these views store, replace
and wipe the site's AI credentials, and ``provision``/``request-code`` drive
account flows against arbitrary emails. The default bar is an active staff user
(``staff_member_required`` semantics, without the login redirect — the JSON
endpoints return 403). Hosts whose admins are not Django-staff (e.g. some
Wagtail setups) can override via ``SCOLTA["amazee_access"]``, a callable
``(request) -> bool``. POSTs are CSRF-protected; the Alpine.js UI sends the
token.

The AmazeeClient is built via ``_client()`` so tests can monkeypatch it.
"""

from __future__ import annotations

from functools import wraps

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from scolta.ai.amazee import (
    AmazeeAccountUpgrader,
    AmazeeApiException,
    AmazeeClient,
    AmazeeModelResolver,
    AmazeeTrialProvisioner,
)

from . import conf
from .amazee import DjangoConfigStorage
from .http import parse_json_body as _body


def _client() -> AmazeeClient:
    return AmazeeClient()


def _storage() -> DjangoConfigStorage:
    return DjangoConfigStorage()


def _access_allowed(request) -> bool:
    checker = conf.get("amazee_access")
    if callable(checker):
        return bool(checker(request))
    user = getattr(request, "user", None)
    # Fail closed when auth middleware is absent.
    return bool(user is not None and user.is_active and user.is_staff)


def amazee_admin_required(view):
    """Deny anonymous/non-admin access with a 403 (no login redirect: the JSON
    endpoints are fetch()ed by the settings UI, and an explicit 403 on the page
    beats a redirect loop for non-staff Wagtail admins)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _access_allowed(request):
            return JsonResponse({"error": "Admin access required"}, status=403)
        return view(request, *args, **kwargs)

    return wrapped


@amazee_admin_required
@require_GET
def status(request) -> JsonResponse:
    storage = _storage()
    creds = storage.load()
    models = storage.stored_models()
    return JsonResponse(
        {
            "provisioned": creds is not None,
            "region": creds["region"] if creds else None,
            "ai_model": models.get("ai_model"),
            "ai_expansion_model": models.get("ai_expansion_model"),
            "ai_provider": conf.scolta_config().ai_provider,
        }
    )


@amazee_admin_required
@require_POST
def provision(request) -> JsonResponse:
    data = _body(request) or {}
    client, storage = _client(), _storage()
    provisioner = AmazeeTrialProvisioner(client, storage, None, AmazeeModelResolver(client))
    try:
        result = provisioner.provision(str(data.get("email", "")))
    except AmazeeApiException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    if result.ai_model or result.ai_expansion_model:
        storage.store_models(result.ai_model or "", result.ai_expansion_model or "")
    return JsonResponse({"ok": True, "region": result.region, "status": result.status})


@amazee_admin_required
@require_POST
def request_code(request) -> JsonResponse:
    data = _body(request)
    if not data or not data.get("email"):
        return JsonResponse({"error": "email required"}, status=400)
    try:
        AmazeeAccountUpgrader(_client(), _storage()).request_verification_code(data["email"])
    except AmazeeApiException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"ok": True})


@amazee_admin_required
@require_POST
def sign_in(request) -> JsonResponse:
    data = _body(request) or {}
    if not data.get("email") or not data.get("code"):
        return JsonResponse({"error": "email and code required"}, status=400)
    try:
        token = AmazeeAccountUpgrader(_client(), _storage()).sign_in(data["email"], data["code"])
    except AmazeeApiException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"ok": True, "session_token": token})


@amazee_admin_required
@require_POST
def regions(request) -> JsonResponse:
    data = _body(request) or {}
    if not data.get("session_token"):
        return JsonResponse({"error": "session_token required"}, status=400)
    try:
        regs = AmazeeAccountUpgrader(_client(), _storage()).list_regions(data["session_token"])
    except AmazeeApiException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"regions": regs}, safe=False)


@amazee_admin_required
@require_POST
def upgrade(request) -> JsonResponse:
    data = _body(request) or {}
    if not data.get("session_token") or not data.get("region_id"):
        return JsonResponse({"error": "session_token and region_id required"}, status=400)
    try:
        result = AmazeeAccountUpgrader(_client(), _storage()).upgrade(
            data["session_token"], data["region_id"]
        )
    except AmazeeApiException as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"ok": True, "region": result.region})


@amazee_admin_required
@require_POST
def disconnect(request) -> JsonResponse:
    _storage().clear()
    return JsonResponse({"ok": True})


@amazee_admin_required
def settings_page(request):
    """Render the multi-step Amazee.ai connection UI (Alpine.js, no build step)."""
    storage = _storage()
    creds = storage.load()
    cfg = conf.scolta_config()
    if creds:
        step = "connected"
    elif cfg.ai_provider not in ("amazee", ""):
        step = "provider-configured"
    else:
        step = "start"
    return render(
        request,
        "scolta_django/amazee_settings.html",
        {
            "step": step,
            "region": creds["region"] if creds else None,
            "routes": {
                "status": reverse("scolta:amazee_status"),
                "provision": reverse("scolta:amazee_provision"),
                "request_code": reverse("scolta:amazee_request_code"),
                "sign_in": reverse("scolta:amazee_sign_in"),
                "regions": reverse("scolta:amazee_regions"),
                "upgrade": reverse("scolta:amazee_upgrade"),
                "disconnect": reverse("scolta:amazee_disconnect"),
            },
        },
    )
