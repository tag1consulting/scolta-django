import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ScoltaTracker",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("content_id", models.CharField(max_length=255)),
                ("content_type", models.CharField(max_length=255)),
                ("action", models.CharField(default="index", max_length=16)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                "db_table": "scolta_tracker",
                "unique_together": {("content_id", "content_type")},
            },
        ),
    ]
