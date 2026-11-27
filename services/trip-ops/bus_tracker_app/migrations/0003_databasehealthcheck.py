from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bus_tracker_app", "0002_trip_attendance_permission")]

    operations = [
        migrations.CreateModel(
            name="DatabaseHealthCheck",
            fields=[
                ("id", models.PositiveSmallIntegerField(primary_key=True, serialize=False)),
                ("checked_at", models.DateTimeField()),
            ],
        ),
    ]
