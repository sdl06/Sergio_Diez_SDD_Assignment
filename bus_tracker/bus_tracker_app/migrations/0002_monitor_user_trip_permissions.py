from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bus_tracker_app", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="monitor",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="monitor_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="trip",
            options={
                "ordering": ["-date", "route__route_name"],
                "permissions": [
                    ("prepare_trip", "Can prepare trips"),
                    ("manage_operational_data", "Can manage operational data"),
                ],
            },
        ),
    ]
