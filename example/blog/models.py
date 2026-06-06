from django.db import models
from django.utils import timezone
from scolta.content import ContentItem

from scolta_django.searchable import SearchableMixin


class Post(SearchableMixin, models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    body = models.TextField(help_text="HTML body")
    published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/blog/{self.slug}/"

    def should_be_searchable(self):
        return self.published

    def to_searchable_content(self):
        return ContentItem(
            id=f"post-{self.pk}",
            title=self.title,
            body_html=self.body,           # real HTML, cleaned by the indexer
            url=self.get_absolute_url(),
            date=self.updated_at.strftime("%Y-%m-%d"),
            site_name="Scolta Django Demo",
        )
