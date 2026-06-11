"""Wagtail admin integration — a menu item + a panel to trigger a build and
show index status.

Auto-discovered by Wagtail (only when Wagtail is installed). Admin-only imports
are lazy so the module loads under wagtailcore without wagtail.admin.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.urls import path, reverse
from django.utils.html import format_html
from wagtail import hooks


def scolta_admin_view(request):
    from scolta.index.build_result import StatusReport

    from .tasks import rebuild_via_dispatch
    from .wagtail import admin_status

    message = ""
    if request.method == "POST":
        # Through the dispatcher: queue-wired projects don't block the
        # request on a full rebuild of a large site.
        result = rebuild_via_dispatch(force=True)
        if isinstance(result, StatusReport):
            message = "Index rebuilt." if result.success else f"Build failed: {result.error}"
        elif result is None:
            message = "Nothing to index."
        else:
            message = "Rebuild dispatched."

    s = admin_status()
    return HttpResponse(
        format_html(
            "<h1>Scolta Search</h1>"
            "<p>Site: {}</p><p>Indexer: {}</p>"
            "<p>Index built: {}</p><p>AI configured: {}</p>"
            "<p>Pending changes: {}</p>"
            "{}"
            '<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit">Rebuild index</button></form>',
            s["site_name"],
            s["indexer"],
            s["index_exists"],
            s["ai_configured"],
            s["pending_changes"],
            format_html("<p><strong>{}</strong></p>", message) if message else "",
            get_token(request),
        )
    )


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [path("scolta/", scolta_admin_view, name="scolta_admin")]


@hooks.register("register_admin_menu_item")
def register_admin_menu_item():
    from wagtail.admin.menu import MenuItem

    return MenuItem("Scolta Search", reverse("scolta_admin"), icon_name="search", order=10000)
