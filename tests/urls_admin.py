"""Urlconf mounting the Wagtail admin view for full request/middleware tests."""

from django.urls import include, path

from scolta_django.wagtail_hooks import scolta_admin_view

urlpatterns = [
    path("admin/scolta/", scolta_admin_view, name="scolta_admin"),
    path("", include("scolta_django.urls")),
]
