import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import bus_tracker_app.models


class Migration(migrations.Migration):

    dependencies = [
        ("bus_tracker_app", "0004_parent_child_access_and_location_permission"),
    ]

    operations = [
        migrations.CreateModel(
            name="TripStopEta",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "origin_latitude",
                    models.FloatField(validators=[bus_tracker_app.models.validate_latitude]),
                ),
                (
                    "origin_longitude",
                    models.FloatField(validators=[bus_tracker_app.models.validate_longitude]),
                ),
                (
                    "origin_accuracy_m",
                    models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1)]),
                ),
                ("estimated_arrival", models.DateTimeField()),
                ("calculated_at", models.DateTimeField()),
                ("travel_time_seconds", models.PositiveIntegerField()),
                ("traffic_delay_seconds", models.PositiveIntegerField(default=0)),
                ("route_distance_m", models.PositiveIntegerField()),
                ("provider", models.CharField(default="tomtom", max_length=20)),
                (
                    "stop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="trip_eta_estimates",
                        to="bus_tracker_app.stop",
                    ),
                ),
                (
                    "trip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stop_eta_estimates",
                        to="bus_tracker_app.trip",
                    ),
                ),
            ],
            options={
                "ordering": ["-calculated_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("trip", "stop"),
                        name="one_eta_per_trip_stop",
                    )
                ],
            },
        ),
    ]
