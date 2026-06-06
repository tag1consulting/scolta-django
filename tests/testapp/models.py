from django.db import models

from scolta_django.searchable import SearchableMixin


class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    body = models.TextField(default="")
    published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "testapp"

    def should_be_searchable(self) -> bool:
        return self.published
