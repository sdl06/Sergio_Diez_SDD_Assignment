from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bus_tracker_app", "0003_trip_legs_and_locations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="trip",
            options={
                "ordering": ["-date", "route__route_name", "leg"],
                "permissions": [
                    ("prepare_trip", "Can prepare trips"),
                    ("manage_operational_data", "Can manage operational data"),
                    ("post_trip_location", "Can post trip locations"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ParentChildAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parent_accesses",
                        to="bus_tracker_app.student",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="child_accesses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["student__name", "user__username"],
                "constraints": [
                    models.UniqueConstraint(fields=("user", "student"), name="unique_parent_child_access")
                ],
            },
        ),
    ]
