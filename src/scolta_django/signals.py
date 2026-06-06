"""Model save/delete signal handlers → tracker + debounced rebuild.

Django equivalent of WordPress save_post / Laravel ScoltaObserver. Note: Django
``QuerySet.update()`` and ``bulk_create`` bypass signals (same caveat as Laravel
mass-updates) — run ``manage.py scolta_build`` after bulk operations.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from .models import ACTION_DELETE, ACTION_INDEX, ScoltaTracker
from .tasks import schedule_rebuild


def _content_type(instance) -> str:
    if hasattr(instance, "get_searchable_type"):
        return instance.get_searchable_type()
    return f"{instance._meta.app_label}.{instance._meta.object_name}"


def handle_save(sender, instance, **kwargs) -> None:
    should_index = (
        instance.should_be_searchable() if hasattr(instance, "should_be_searchable") else True
    )
    ScoltaTracker.track(
        str(instance.pk), _content_type(instance), ACTION_INDEX if should_index else ACTION_DELETE
    )
    schedule_rebuild()


def handle_delete(sender, instance, **kwargs) -> None:
    ScoltaTracker.track(str(instance.pk), _content_type(instance), ACTION_DELETE)
    schedule_rebuild()


def connect_model(model) -> None:
    dispatch_uid = f"scolta_{model._meta.label_lower}"
    post_save.connect(handle_save, sender=model, dispatch_uid=dispatch_uid + "_save")
    post_delete.connect(handle_delete, sender=model, dispatch_uid=dispatch_uid + "_delete")


def disconnect_model(model) -> None:
    dispatch_uid = f"scolta_{model._meta.label_lower}"
    post_save.disconnect(sender=model, dispatch_uid=dispatch_uid + "_save")
    post_delete.disconnect(sender=model, dispatch_uid=dispatch_uid + "_delete")
