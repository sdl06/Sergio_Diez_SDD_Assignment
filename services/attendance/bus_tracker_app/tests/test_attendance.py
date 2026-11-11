from dataclasses import replace
from unittest.mock import patch

from django.db import connection
from django.test import TestCase

from bus_tracker_app.attendance.models import AbsenceNotice, StudentAttendance
from bus_tracker_app.attendance.trip_context import RosterStudent, TripContext


class AttendanceTests(TestCase):
    notice_url = "/api/children/12/trips/30/absence/"
    roster_url = "/api/trips/30/attendance/"
    record_url = "/api/trips/30/attendance/12/"

    def setUp(self):
        self.parent = TripContext(
            trip_id=30, status="prepared", leg=1, actor_id=51,
            roster=(RosterStudent(12, "Ana", 4, "School"), RosterStudent(13, "Luis", 4, "School")),
            parent_child_ids=frozenset({12}),
        )
        self.monitor = replace(
            self.parent, status="active", actor_id=52,
            parent_child_ids=frozenset(), can_record_attendance=True,
        )

    def post(self, url, data):
        return self.client.post(url, data, content_type="application/json")

    def test_absence_and_definitive_attendance_are_separate(self):
        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=self.parent):
            self.assertEqual(self.client.get(self.notice_url).json()["attendance"], "unrecorded")
            self.assertEqual(self.post(self.notice_url, {"absent": True}).status_code, 201)
            self.assertEqual(self.post(self.notice_url, {"absent": False}).status_code, 200)
        notice = AbsenceNotice.objects.get()
        self.assertEqual((notice.trip_id, notice.student_id, notice.reported_by_id), (30, 12, 51))
        self.assertEqual(notice.status, "cancelled")
        self.assertFalse(StudentAttendance.objects.exists())

        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=self.monitor):
            self.assertEqual(self.post(self.record_url, {"status": "present"}).status_code, 201)
            self.assertEqual(self.post(self.record_url, {"status": "absent"}).status_code, 200)
            roster = self.client.get(self.roster_url).json()["students"]
        observation = StudentAttendance.objects.get()
        self.assertEqual((observation.trip_id, observation.student_id, observation.recorded_by_id), (30, 12, 52))
        self.assertEqual(roster[0]["attendance"], "absent")
        self.assertEqual(roster[0]["absence_notice"], "cancelled")
        self.assertEqual(roster[1]["attendance"], "unrecorded")

    def test_verified_access_roster_and_lifecycle_are_required(self):
        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=self.parent):
            self.assertEqual(self.post(self.record_url, {"status": "present"}).status_code, 403)
            self.assertEqual(self.post(self.notice_url.replace("/12/", "/13/"), {"absent": True}).status_code, 404)
            self.assertEqual(self.post(self.notice_url, {"absent": "true"}).status_code, 400)

        active_parent = replace(self.parent, status="active")
        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=active_parent):
            self.assertEqual(self.post(self.notice_url, {"absent": True}).status_code, 409)

        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=self.monitor):
            self.assertEqual(self.post(self.roster_url + "99/", {"status": "present"}).status_code, 404)

        completed = replace(self.monitor, status="completed")
        with patch("bus_tracker_app.attendance.views.get_trip_context", return_value=completed):
            self.assertEqual(self.post(self.record_url, {"status": "present"}).status_code, 409)

        self.assertFalse(AbsenceNotice.objects.exists())
        self.assertFalse(StudentAttendance.objects.exists())

    def test_requests_fail_closed_without_verified_context(self):
        response = self.client.post(
            self.record_url, {"status": "present"}, content_type="application/json",
            headers={"X-User-ID": "52"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "trip_context_unavailable"})
        self.assertEqual(self.client.get(self.roster_url).status_code, 503)
        self.assertFalse(StudentAttendance.objects.exists())

    def test_migration_creates_only_attendance_tables_without_foreign_keys(self):
        tables = {name for name in connection.introspection.table_names() if name != "django_migrations"}
        self.assertEqual(tables, {"bus_tracker_app_absencenotice", "bus_tracker_app_studentattendance"})
        with connection.cursor() as cursor:
            for table in tables:
                constraints = connection.introspection.get_constraints(cursor, table)
                self.assertFalse(any(item["foreign_key"] for item in constraints.values()))
                self.assertTrue(any(
                    item["unique"] and item["columns"] == ["trip_id", "student_id"]
                    for item in constraints.values()
                ))
