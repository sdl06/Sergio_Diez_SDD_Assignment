from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def convert_presence_to_status(apps, schema_editor):
    Attendance = apps.get_model("bus_tracker_app", "StudentAttendance")
    records = Attendance.objects.using(schema_editor.connection.alias)
    records.filter(presence=True).update(status="present")
    records.filter(presence=False).update(status="absent")
    # Keep legacy provenance unknown instead of inventing an actor or timestamp.
    records.update(recorded_by=None, recorded_at=None)


def convert_status_to_presence(apps, schema_editor):
    Attendance = apps.get_model("bus_tracker_app", "StudentAttendance")
    records = Attendance.objects.using(schema_editor.connection.alias)
    records.filter(status="present").update(presence=True)
    records.filter(status="absent").update(presence=False)


class Migration(migrations.Migration):
    dependencies = [
        ("bus_tracker_app", "0006_alter_trip_leg"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="studentattendance",
            name="status",
            field=models.CharField(choices=[("present", "Present"), ("absent", "Absent")], max_length=8, null=True),
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="recorded_by",
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="recorded_attendance",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="studentattendance",
            name="recorded_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.RunPython(convert_presence_to_status, convert_status_to_presence),
        migrations.AlterField(
            model_name="studentattendance",
            name="status",
            field=models.CharField(choices=[("present", "Present"), ("absent", "Absent")], max_length=8),
        ),
        migrations.RemoveField(model_name="studentattendance", name="presence"),
        migrations.AlterModelOptions(
            name="studentattendance",
            options={"permissions": [("record_trip_attendance", "Can record attendance for an assigned trip")]},
        ),
        migrations.CreateModel(
            name="AbsenceNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(
                    choices=[("reported", "Reported absent"), ("cancelled", "Cancelled")],
                    default="reported", max_length=12,
                )),
                ("reported_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reported_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    related_name="reported_absences",
                )),
                ("student", models.ForeignKey(
                    to="bus_tracker_app.student", on_delete=django.db.models.deletion.CASCADE,
                    related_name="absence_notices",
                )),
                ("trip", models.ForeignKey(
                    to="bus_tracker_app.trip", on_delete=django.db.models.deletion.CASCADE,
                    related_name="absence_notices",
                )),
            ],
            options={"constraints": [models.UniqueConstraint(
                fields=("student", "trip"), name="one_absence_notice_per_student_trip",
            )]},
        ),
    ]
