"""Record which operator action established the Amazee.ai connection.

Additive and defaulted: an existing row keeps its credentials and gets an empty
connection source, which reads as "not recorded". That is the honest answer for
a connection made before Scolta recorded it — nothing here guesses a value for
rows that predate the column, because guessing is the defect the column exists
to remove.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("scolta_django", "0002_amazee")]
    operations = [
        migrations.AddField(
            model_name="scoltaamazeeconfig",
            name="connection_source",
            field=models.CharField(default="", max_length=32),
        ),
    ]
