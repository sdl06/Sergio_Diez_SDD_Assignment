from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("bus_tracker_app", "0002_databasehealthcheck")]

    operations = [
        migrations.AlterField(
            model_name="studentattendance",
            name="recorded_at",
            field=models.DateTimeField(auto_now=True, null=True, db_column="last_recorded_at"),
        ),
    ]
