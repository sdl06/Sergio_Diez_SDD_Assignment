import bus_tracker_app.models
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def require_explicit_historical_legs(apps, schema_editor):
    Trip = apps.get_model("bus_tracker_app", "Trip")
    if Trip.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "Existing trips need an explicit leg assignment before this migration can run. "
            "Do not silently classify historical trips as leg 1."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("bus_tracker_app", "0002_monitor_user_trip_permissions"),
    ]

    operations = [
        migrations.RunPython(require_explicit_historical_legs, migrations.RunPython.noop),
        migrations.AddField(
            model_name="trip",
            name="leg",
            field=models.PositiveSmallIntegerField(choices=[(1, "To school"), (2, "From school")], null=True),
        ),
        migrations.AlterField(
            model_name="trip",
            name="leg",
            field=models.PositiveSmallIntegerField(choices=[(1, "To school"), (2, "From school")]),
        ),
        migrations.AddField(
            model_name="trip",
            name="status",
            field=models.CharField(
                choices=[("prepared", "Prepared"), ("active", "Active"), ("completed", "Completed")],
                default="prepared",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="trip",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="trip",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="trip",
            options={
                "ordering": ["-date", "route__route_name", "leg"],
                "permissions": [
                    ("prepare_trip", "Can prepare trips"),
                    ("manage_operational_data", "Can manage operational data"),
                ],
            },
        ),
        migrations.RemoveConstraint(
            model_name="trip",
            name="one_trip_per_route_day",
        ),
        migrations.AddConstraint(
            model_name="trip",
            constraint=models.UniqueConstraint(fields=("route", "date", "leg"), name="one_trip_per_route_day_leg"),
        ),
        migrations.CreateModel(
            name="TripLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("latitude", models.FloatField(validators=[bus_tracker_app.models.validate_latitude])),
                ("longitude", models.FloatField(validators=[bus_tracker_app.models.validate_longitude])),
                ("accuracy_m", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ("observed_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(max_length=20)),
                ("client_sample_id", models.UUIDField()),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="location_samples",
                        to="bus_tracker_app.trip",
                    ),
                ),
            ],
            options={
                "ordering": ["-observed_at", "-received_at"],
                "indexes": [
                    models.Index(
                        fields=["trip", "-observed_at", "-received_at"], name="trip_location_latest_idx"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("trip", "client_sample_id"), name="unique_location_sample_per_trip"
                    )
                ],
            },
        ),
    ]
