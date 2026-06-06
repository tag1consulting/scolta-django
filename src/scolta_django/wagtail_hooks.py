"""Wagtail admin integration — a menu item + a panel to trigger a build and
show index status.

Auto-discovered by Wagtail (only when Wagtail is installed). Admin-only imports
are lazy so the module loads under wagtailcore without wagtail.admin.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from wagtail import hooks


def scolta_admin_view(request):
    from .tasks import trigger_rebuild
    from .wagtail import admin_status

    message = ""
    if request.method == "POST":
        ok = trigger_rebuild(force=True)
        message = "Index rebuilt." if ok else "Nothing to index."

    s = admin_status()
    return HttpResponse(format_html(
        "<h1>Scolta Search</h1>"
        "<p>Site: {}</p><p>Indexer: {}</p>"
        "<p>Index built: {}</p><p>AI configured: {}</p>"
        "<p>Pending changes: {}</p>"
        "{}"
        '<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="">'
        '<button type="submit">Rebuild index</button></form>',
        s["site_name"], s["indexer"], s["index_exists"], s["ai_configured"],
        s["pending_changes"], format_html("<p><strong>{}</strong></p>", message) if message else "",
    ))


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [path("scolta/", scolta_admin_view, name="scolta_admin")]


@hooks.register("register_admin_menu_item")
def register_admin_menu_item():
    from wagtail.admin.menu import MenuItem

    return MenuItem("Scolta Search", reverse("scolta_admin"), icon_name="search", order=10000)
