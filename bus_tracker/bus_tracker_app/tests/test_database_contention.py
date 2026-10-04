"""HTTP exception classification; real overlap/rollback is tested separately."""
import sqlite3
from unittest.mock import Mock, patch

from django.db import OperationalError

from bus_tracker_app.models import Trip
from .helpers import DomainCase


def sqlite_failure(code=None):
    cause = sqlite3.OperationalError("test SQLite failure")
    if code is not None:
        cause.sqlite_errorcode = code
    error = OperationalError("test database failure")
    error.__cause__ = cause
    return error


class ContentionResponseTests(DomainCase):
    def absence_request(self):
        self.login(self.parent)
        return self.json_post(f"/api/children/{self.child.pk}/trips/{self.trip.pk}/absence/", {"absent": True})

    def attendance_request(self):
        self.login()
        Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.ACTIVE)
        return self.json_post(f"/api/trips/{self.trip.pk}/attendance/{self.child.pk}/", {"status": "present"})

    def assert_busy(self, response):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "database_busy")
        self.assertIn("Refresh", response.json()["detail"])
        self.assertEqual(response.headers["Retry-After"], "1")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_busy_parent_notice_returns_retryable_json(self):
        with patch("bus_tracker_app.attendance.views.set_absence_notice", side_effect=sqlite_failure(sqlite3.SQLITE_BUSY)):
            self.assert_busy(self.absence_request())

    def test_locked_monitor_observation_returns_retryable_json(self):
        with patch("bus_tracker_app.attendance.views.record_attendance", side_effect=sqlite_failure(sqlite3.SQLITE_LOCKED)):
            self.assert_busy(self.attendance_request())

    def test_extended_sqlite_busy_and_locked_codes_are_recognized(self):
        for code in [sqlite3.SQLITE_BUSY_SNAPSHOT, sqlite3.SQLITE_LOCKED_SHAREDCACHE]:
            with self.subTest(code=code), patch("bus_tracker_app.attendance.views.record_attendance", side_effect=sqlite_failure(code)):
                self.assert_busy(self.attendance_request())

    def test_unrelated_sqlite_error_is_not_disguised_as_contention(self):
        with patch("bus_tracker_app.attendance.views.set_absence_notice", side_effect=sqlite_failure(sqlite3.SQLITE_ERROR)):
            with self.assertRaises(OperationalError):
                self.absence_request()

    def test_operational_error_without_sqlite_code_is_not_swallowed(self):
        for error in [OperationalError("unknown database failure"), sqlite_failure()]:
            with self.subTest(error=error), patch("bus_tracker_app.attendance.views.set_absence_notice", side_effect=error):
                with self.assertRaises(OperationalError):
                    self.absence_request()

    def test_other_database_backend_is_not_given_sqlite_handling(self):
        with patch("bus_tracker_app.attendance.views.connection", Mock(vendor="postgresql")), patch(
            "bus_tracker_app.attendance.views.set_absence_notice", side_effect=sqlite_failure(sqlite3.SQLITE_BUSY)):
            with self.assertRaises(OperationalError):
                self.absence_request()
