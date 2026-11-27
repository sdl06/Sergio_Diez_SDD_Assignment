from datetime import datetime, timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AttendanceMigrationTests(TransactionTestCase):
    def test_rename_preserves_existing_attendance(self):
        previous = [("bus_tracker_app", "0002_databasehealthcheck")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        old_apps = executor.migrate(previous).apps
        old_attendance = old_apps.get_model("bus_tracker_app", "StudentAttendance")
        recorded = old_attendance.objects.create(
            trip_id=2, student_id=1, status="present", recorded_by_id=4,
        )
        historical = old_attendance.objects.create(trip_id=2, student_id=2, status="absent")
        timestamp = datetime(2026, 11, 27, 7, 58, 51, 594484, tzinfo=timezone.utc)
        old_attendance.objects.filter(pk=recorded.pk).update(recorded_at=timestamp)
        old_attendance.objects.filter(pk=historical.pk).update(recorded_at=None)

        new_apps = MigrationExecutor(connection).migrate(latest).apps
        attendance = new_apps.get_model("bus_tracker_app", "StudentAttendance")
        rows = attendance.objects.order_by("student_id").values_list(
            "pk", "trip_id", "student_id", "status", "recorded_by_id", "recorded_at",
        )
        self.assertEqual(list(rows), [
            (recorded.pk, 2, 1, "present", 4, timestamp),
            (historical.pk, 2, 2, "absent", None, None),
        ])
        with connection.cursor() as cursor:
            fields = connection.introspection.get_table_description(cursor, attendance._meta.db_table)
        columns = {field.name for field in fields}
        self.assertIn("last_recorded_at", columns)
        self.assertNotIn("recorded_at", columns)
