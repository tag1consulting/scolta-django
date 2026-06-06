from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("scolta_django", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="ScoltaAmazeeConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("litellm_token", models.TextField(default="")),
                ("litellm_api_url", models.TextField(default="")),
                ("region", models.CharField(default="", max_length=128)),
                ("ai_model", models.CharField(default="", max_length=128)),
                ("ai_expansion_model", models.CharField(default="", max_length=128)),
            ],
            options={"db_table": "scolta_amazee_config"},
        ),
    ]
