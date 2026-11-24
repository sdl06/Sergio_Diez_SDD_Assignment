from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bus_tracker_app", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="DatabaseHealthCheck",
            fields=[
                ("id", models.PositiveSmallIntegerField(primary_key=True, serialize=False)),
                ("checked_at", models.DateTimeField()),
            ],
        ),
    ]
