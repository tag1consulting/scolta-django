"""The change-tracker model (mirror of Laravel's ScoltaTracker)."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

ACTION_INDEX = "index"
ACTION_DELETE = "delete"


class ScoltaTracker(models.Model):
    """Records content changes for incremental rebuilds.

    Internal plumbing: signals write to it, the build command reads from it.
    """

    content_id = models.CharField(max_length=255)
    content_type = models.CharField(max_length=255)
    action = models.CharField(max_length=16, default=ACTION_INDEX)
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "scolta_tracker"
        unique_together = ("content_id", "content_type")
        app_label = "scolta_django"

    @classmethod
    def track(cls, content_id: str, content_type: str, action: str = ACTION_INDEX) -> ScoltaTracker:
        obj, _created = cls.objects.update_or_create(
            content_id=str(content_id),
            content_type=content_type,
            defaults={"action": action, "changed_at": timezone.now()},
        )
        return obj

    @classmethod
    def pending_count(cls, action: str | None = None) -> int:
        qs = cls.objects.all()
        if action is not None:
            qs = qs.filter(action=action)
        return qs.count()

    @classmethod
    def pending(cls, action: str):
        return cls.objects.filter(action=action)

    @classmethod
    def clear_all(cls) -> int:
        deleted, _ = cls.objects.all().delete()
        return deleted
