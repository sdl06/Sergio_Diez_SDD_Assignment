import json
from datetime import datetime, timedelta, timezone as datetime_timezone
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.utils import timezone

from bus_tracker_app.attendance.validators import (
    AttendancePayloadError, parse_absent_json, parse_attendance_json,
)
from bus_tracker_app.forms import PrepareTripForm, StudentForm, TripForm, StudentAttendanceForm
from bus_tracker_app.models import Trip, validate_latitude, validate_longitude
from bus_tracker_app.tracking.models import TripLocation, TripStopEta
from bus_tracker_app.tracking.views import LocationPayloadError, _validate_calendar_date, validate_location_json
from .helpers import DomainCase


class CommandTests(SimpleTestCase):
    def test_gregorian_calendar_boundaries(self):
        for date in ["2000-02-29", "2024-02-29", "2400-02-29", "2025-02-28", "2025-04-30", "2025-01-31"]:
            with self.subTest(date=date):
                _validate_calendar_date(date + "T12:00:00Z")
        for date in ["1900-02-29", "2025-02-29", "2100-02-29", "2024-02-30",
            "2025-04-31", "2025-00-01", "2025-13-01", "2025-01-00", "0000-01-01"]:
            with self.subTest(date=date), self.assertRaises(LocationPayloadError):
                _validate_calendar_date(date + "T12:00:00Z")

    def test_attendance_commands(self):
        self.assertTrue(parse_absent_json(b'{"absent":true}'))
        self.assertFalse(parse_absent_json(b'{"absent":false}'))
        for status in ["present", "absent"]:
            self.assertEqual(parse_attendance_json(json.dumps({"status": status}).encode()), status)

    def test_invalid_commands(self):
        for parser, field in [(parse_absent_json, "absent"), (parse_attendance_json, "status")]:
            for body in [b"", b"\xff", b"[]", b"null", b"{" , b"x" * 4097,
                b'{"extra":true}', ('{"%s":null}' % field).encode(),
                ('{"%s":true,"%s":false}' % (field, field)).encode(),
                ('{"%s":1}' % field).encode(), b"[" * 1100 + b"]" * 1100]:
                with self.subTest(parser=parser.__name__, body=body[:40]):
                    with self.assertRaises(AttendancePayloadError):
                        parser(body)

    def test_coordinate_boundaries(self):
        for validator, bound in [(validate_latitude, 90), (validate_longitude, 180)]:
            for value in [-bound, 0, bound]:
                validator(value)
            for value in [-bound - 1, bound + 1, float("nan"), float("inf")]:
                with self.assertRaises(ValidationError):
                    validator(value)


class ValidationTests(DomainCase):
    def test_leap_dates_through_complete_location_validator(self):
        # Freeze the clock beyond all examples so future-fix protection remains
        # enabled but does not obscure the Gregorian calendar cases.
        with patch("bus_tracker_app.tracking.views.timezone.now",
            return_value=datetime(2500, 1, 1, tzinfo=datetime_timezone.utc)):
            for year in [2000, 2024, 2400]:
                payload = self.fix()
                payload["observed_at"] = f"{year}-02-29T12:00:00Z"
                result = validate_location_json(json.dumps(payload).encode())
                self.assertEqual(result["observed_at"].day, 29)
            for timestamp in ["1900-02-29T12:00:00Z", "2025-02-29T12:00:00Z",
                "2100-02-29T12:00:00Z", "2024-02-29T25:00:00Z", "2024-2-30T12:00:00Z"]:
                payload = self.fix()
                payload["observed_at"] = timestamp
                with self.subTest(timestamp=timestamp), self.assertRaises(LocationPayloadError):
                    validate_location_json(json.dumps(payload).encode())

    def test_location_payload_edges(self):
        valid = self.fix()
        self.assertEqual(validate_location_json(json.dumps(valid).encode())["latitude"], valid["latitude"])
        invalid = [b"", b"\xff", b"[]", b"x" * 4097]
        for field, values in {
            "latitude": [True, "40", None, 91, float("nan")],
            "longitude": [-181, float("inf")], "accuracy_m": [True, 1.5, 0, 1001],
            "observed_at": [None, "bad", "2026-01-01T12:00:00", "2026-02-30T12:00:00Z",
                (timezone.now() + timedelta(minutes=6)).isoformat()],
            "client_sample_id": [None, "bad"],
        }.items():
            invalid.extend(json.dumps({**valid, field: value}).encode() for value in values)
        invalid.extend([json.dumps({**valid, "extra": 1}).encode(), b'{}'])
        for body in invalid:
            with self.subTest(body=body[:100]):
                with self.assertRaises(LocationPayloadError):
                    validate_location_json(body)

    def test_disabled_monitor_ignores_forged_value(self):
        form = PrepareTripForm({"bus": self.bus.pk, "monitor": self.other_monitor.pk,
            "date": self.trip.date, "leg": 2}, route=self.route, assigned_monitor=self.monitor)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["monitor"], self.monitor)
        admin_form = PrepareTripForm(form.data, route=self.route)
        self.assertFalse(admin_form.is_valid())

    def test_forms_reject_cross_route_relations(self):
        form = StudentForm({"name": "Bad", "date_of_birth": "2015-01-01",
            "route": self.route.pk, "assigned_stop": self.other_stop.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("assigned_stop", form.errors)
        data = {"route": self.route.pk, "bus": self.bus.pk, "monitor": self.other_monitor.pk,
            "date": self.trip.date, "leg": 2, "students": [self.foreign_child.pk]}
        form = TripForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("monitor", form.errors)
        self.assertIn("students", form.errors)
        form = StudentAttendanceForm({"student": self.foreign_child.pk, "trip": self.trip.pk,
            "status": "present", "recorded_by": self.monitor_user.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("student", form.errors)

    def test_model_clean_and_database_uniqueness(self):
        self.trip.full_clean()
        self.child.full_clean()
        for obj in [self.trip, self.child]:
            self.assertTrue(str(obj))
        self.trip.monitor = self.other_monitor
        with self.assertRaises(ValidationError):
            self.trip.clean()
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Trip.objects.create(route=self.route, bus=self.bus, monitor=self.monitor,
                date=self.trip.date, leg=1)
        sample = TripLocation(trip=self.trip, latitude=0, longitude=0, accuracy_m=1,
            observed_at=timezone.now().replace(tzinfo=None), source="test")
        with self.assertRaises(ValidationError):
            sample.clean()
        sample.observed_at = timezone.now()
        sample.clean()
        self.assertTrue(str(sample))
        eta = TripStopEta(trip=self.trip, stop=self.other_stop)
        with self.assertRaises(ValidationError):
            eta.clean()
        eta.stop = self.stop
        eta.clean()
