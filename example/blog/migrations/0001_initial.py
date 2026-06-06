import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Post",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=200)),
                ("slug", models.SlugField(unique=True)),
                ("body", models.TextField(help_text="HTML body")),
                ("published", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
    ]
