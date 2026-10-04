from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import Client, override_settings
from django.utils import timezone

from bus_tracker_app.attendance.models import AbsenceNotice, StudentAttendance
from bus_tracker_app.attendance.services import (
    AttendanceStateError, build_attendance_roster, record_attendance, set_absence_notice,
)
from bus_tracker_app.attendance.validators import AttendancePayloadError
from bus_tracker_app.models import Route, Trip
from bus_tracker_app.tracking.models import TripLocation
from bus_tracker_app.tracking.views import (
    LocationTripStateError, save_sample_once, validate_location_json,
)
from bus_tracker_app.trips.services import TripStateError, operational_trips, transition_trip
from .helpers import DomainCase
import json


class LoginRedirectTests(DomainCase):
    def test_default_login_reaches_home_for_each_role(self):
        for user in (self.admin, self.monitor_user, self.parent):
            with self.subTest(username=user.username):
                self.client.logout()
                response = self.client.post("/accounts/login/", {
                    "username": user.username, "password": "test-pass",
                }, follow=True)
                self.assertEqual(response.redirect_chain, [("/", 302)])
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "bus_tracker_app/home.html")
                self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_preserves_local_next_destination(self):
        response = self.client.post("/accounts/login/", {
            "username": self.monitor_user.username, "password": "test-pass",
            "next": "/trips/",
        })
        self.assertRedirects(response, "/trips/")

    def test_login_rejects_external_next_destination(self):
        response = self.client.post("/accounts/login/", {
            "username": self.parent.username, "password": "test-pass",
            "next": "https://example.test/",
        })
        self.assertRedirects(response, "/")


class PreparationTests(DomainCase):
    def test_permission_and_route_matrix(self):
        path = f"/routes/{self.route.pk}/prepare/submit/"
        for user, expected in [(None, 302), (self.parent, 403), (self.other_user, 403)]:
            self.client.logout()
            if user:
                self.login(user)
            self.assertEqual(self.client.post(path, {}).status_code, expected)
        self.assertEqual(Trip.objects.count(), 1)
        self.login()
        for path, expected in [("/admin/trips/new/", 200),
            (f"/admin/trips/new/?route={self.route.pk}", 200),
            (f"/admin/trips/new/?route={self.other.pk}", 403),
            ("/admin/trips/new/?route=bad", 404), ("/routes/99999/prepare/", 404),
            (f"/routes/{self.route.pk}/prepare/", 200)]:
            self.assertEqual(self.client.get(path).status_code, expected)

    def test_prepare_two_legs_idempotently_from_sqlite_roster(self):
        self.login()
        path = f"/routes/{self.route.pk}/prepare/submit/"
        data = {"bus": self.bus.pk, "monitor": self.other_monitor.pk, "date": self.trip.date, "leg": 2}
        self.assertEqual(self.client.post(path, data).status_code, 302)
        afternoon = Trip.objects.get(route=self.route, date=self.trip.date, leg=2)
        self.assertEqual(afternoon.monitor, self.monitor)
        self.assertSetEqual(set(afternoon.students.all()), {self.child, self.sibling})
        self.assertEqual(self.client.post(path, data).status_code, 302)
        self.assertEqual(Trip.objects.count(), 2)
        self.assertEqual(self.client.post(path, {**data, "bus": "bad"}).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 405)

    def test_admin_selection_and_existing_other_monitor(self):
        self.login(self.admin)
        self.assertEqual(self.client.get(f"/admin/trips/new/?route={self.route.pk}").status_code, 200)
        self.assertEqual(self.client.get("/manage/").status_code, 200)
        self.trip.monitor = self.other_monitor
        self.trip.save()
        self.login()
        response = self.client.post(f"/routes/{self.route.pk}/prepare/submit/", {
            "bus": self.bus.pk, "date": self.trip.date, "leg": 1})
        self.assertRedirects(response, "/trips/")
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.monitor, self.other_monitor)

    def test_preparation_rolls_back_if_roster_assignment_fails(self):
        self.login()
        manager_type = type(self.trip.students)
        with patch.object(manager_type, "set", side_effect=RuntimeError("roster failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(f"/routes/{self.route.pk}/prepare/submit/", {
                    "bus": self.bus.pk, "date": self.trip.date, "leg": 2})
        self.assertFalse(Trip.objects.filter(leg=2).exists())


class LifecycleTests(DomainCase):
    def test_scope_and_transitions(self):
        with self.assertRaises(PermissionDenied):
            operational_trips(AnonymousUser())
        with self.assertRaises(PermissionDenied):
            operational_trips(self.parent)
        self.assertFalse(operational_trips(self.other_user).exists())
        self.assertEqual(operational_trips(self.admin).count(), 1)
        with self.assertRaises(Http404):
            transition_trip(user=self.other_user, trip_id=self.trip.pk, target="active")
        with self.assertRaises(ValueError):
            transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="bogus")
        with self.assertRaises(TripStateError):
            transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="completed")
        trip, changed = transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="active")
        self.assertTrue(changed)
        started = trip.started_at
        trip, changed = transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="active")
        self.assertFalse(changed)
        self.assertEqual(trip.started_at, started)
        trip, changed = transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="completed")
        self.assertTrue(changed)
        self.assertIsNotNone(trip.completed_at)
        with self.assertRaises(TripStateError):
            transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target="active")

    def test_lifecycle_http_and_workspace(self):
        self.login()
        for path in ["/trips/", f"/trips/{self.trip.pk}/", f"/trips/{self.trip.pk}/state/"]:
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(f"/trips/{self.trip.pk}/complete/").status_code, 409)
        self.assertEqual(self.client.get(f"/trips/{self.trip.pk}/start/").status_code, 405)
        for action in ["start", "start", "complete", "complete"]:
            self.assertEqual(self.client.post(f"/trips/{self.trip.pk}/{action}/").status_code, 302)
        self.assertEqual(self.client.post(f"/trips/{self.trip.pk}/start/").status_code, 409)


class AttendanceTests(DomainCase):
    def setUp(self):
        self.notice_url = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/absence/"
        self.roster_url = f"/api/trips/{self.trip.pk}/attendance/"
        self.record_url = f"{self.roster_url}{self.child.pk}/"

    def test_notice_cancel_and_independent_monitor_observation(self):
        self.login(self.parent)
        response = self.client.get(self.notice_url)
        self.assertEqual(response.json()["attendance"], "unrecorded")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(self.json_post(self.notice_url, {"absent": True}).status_code, 201)
        self.assertEqual(self.json_post(self.notice_url, {"absent": False}).status_code, 200)
        self.assertEqual(AbsenceNotice.objects.get().status, "cancelled")
        self.assertFalse(StudentAttendance.objects.exists())
        self.trip.status = "active"
        self.trip.save()
        self.assertEqual(self.json_post(self.notice_url, {"absent": True}).status_code, 409)
        self.login()
        for status, code in [("present", 201), ("absent", 200)]:
            self.assertEqual(self.json_post(self.record_url, {"status": status}).status_code, code)
        row = StudentAttendance.objects.get()
        self.assertEqual(row.recorded_by, self.monitor_user)
        self.assertEqual(row.status, "absent")
        self.assertIsNotNone(row.recorded_at)
        with self.assertNumQueries(3):
            roster = build_attendance_roster(self.trip)
        self.assertEqual(roster["students"][0]["attendance"], "absent")
        self.assertEqual(roster["students"][1]["attendance"], "unrecorded")
        self.assertTrue(str(row))
        self.assertTrue(str(AbsenceNotice.objects.get()))

    def test_attendance_http_edge_cases(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.notice_url).status_code, 404)
        self.assertEqual(self.client.get(self.roster_url).status_code, 403)
        self.login(self.other_user)
        self.assertEqual(self.client.get(self.roster_url).status_code, 403)
        self.login(self.parent)
        self.assertEqual(self.client.post(self.notice_url, {}).status_code, 415)
        self.assertEqual(self.json_post(self.notice_url, {"absent": "false"}).status_code, 400)
        self.assertEqual(self.client.delete(self.notice_url).status_code, 405)
        self.login()
        self.assertEqual(self.client.get(self.roster_url).status_code, 200)
        self.assertEqual(self.client.post(self.record_url, {}).status_code, 415)
        self.assertEqual(self.json_post(self.record_url, {"status": "unknown"}).status_code, 400)
        self.assertEqual(self.json_post(self.record_url, {"status": "present"}).status_code, 409)
        self.assertEqual(self.client.get("/api/trips/99999/attendance/").status_code, 404)
        self.trip.status = "active"
        self.trip.save()
        self.assertEqual(self.json_post(f"{self.roster_url}{self.foreign_child.pk}/", {"status": "present"}).status_code, 404)
        self.trip.status = "completed"
        self.trip.save()
        self.assertEqual(self.json_post(self.record_url, {"status": "present"}).status_code, 409)
        self.assertFalse(StudentAttendance.objects.exists())

    def test_direct_services_revalidate_authorization_and_state(self):
        with self.assertRaises(AttendancePayloadError):
            set_absence_notice(user=self.parent, child=self.child, trip=self.trip, absent=1)
        with self.assertRaises(AttendancePayloadError):
            record_attendance(user=self.monitor_user, trip=self.trip, student_id=self.child.pk, status=True)
        with self.assertRaises(Http404):
            set_absence_notice(user=self.outsider, child=self.child, trip=self.trip, absent=True)
        with self.assertRaises(AttendanceStateError):
            record_attendance(user=self.monitor_user, trip=self.trip, student_id=self.child.pk, status="present")
        self.trip.status = "active"
        self.trip.save()
        with self.assertRaises(PermissionDenied):
            record_attendance(user=self.other_user, trip=self.trip, student_id=self.child.pk, status="present")
        row, created = record_attendance(user=self.admin, trip=self.trip, student_id=self.child.pk, status="present")
        self.assertTrue(created)
        row.clean()
        row.student = self.foreign_child
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            row.clean()
        notice = AbsenceNotice(student=self.foreign_child, trip=self.trip)
        with self.assertRaises(ValidationError):
            notice.clean()


class LocationTests(DomainCase):
    def setUp(self):
        self.post_url = f"/api/trips/{self.trip.pk}/locations/"
        self.read_url = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/location/"

    def test_impossible_calendar_date_is_a_client_error_not_a_server_error(self):
        """Regression: invalid client dates must not become server failures."""
        client = Client(raise_request_exception=False)
        client.force_login(self.monitor_user)
        self.trip.status = "active"
        self.trip.save()
        payload = self.fix()
        payload["observed_at"] = "2026-02-30T12:00:00Z"
        response = client.post(self.post_url, payload, content_type="application/json")
        self.assertFalse(TripLocation.objects.exists())
        self.assertEqual(response.status_code, 400)

    @override_settings(LOCATION_MIN_SAMPLE_INTERVAL_SECONDS=0)
    def test_leap_year_dates_over_http(self):
        self.login()
        self.trip.status = "active"
        self.trip.save()
        for year, expected in [(2000, 201), (2024, 201), (1900, 400), (2025, 400), (2100, 400)]:
            payload = self.fix()
            payload["observed_at"] = f"{year}-02-29T12:00:00Z"
            with self.subTest(year=year):
                response = self.json_post(self.post_url, payload)
                self.assertEqual(response.status_code, expected)
                if expected == 400:
                    self.assertEqual(response.json()["error"], "invalid_location")
        self.assertEqual(TripLocation.objects.count(), 2)

    def test_location_role_lifecycle_idempotency_and_rate_limit(self):
        self.login(self.parent)
        self.assertEqual(self.json_post(self.post_url, self.fix()).status_code, 403)
        self.login(self.other_user)
        self.assertEqual(self.json_post(self.post_url, self.fix()).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.json_post(self.post_url, self.fix()).status_code, 403)
        self.login()
        self.assertEqual(self.json_post(self.post_url, self.fix()).status_code, 409)
        self.trip.status = "active"
        self.trip.save()
        self.assertEqual(self.client.post(self.post_url, {}).status_code, 415)
        self.assertEqual(self.json_post(self.post_url, {}).status_code, 400)
        payload = self.fix()
        created = self.json_post(self.post_url, payload)
        self.assertEqual(created.status_code, 201)
        duplicate = self.json_post(self.post_url, payload)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(duplicate.json()["sample_id"], created.json()["sample_id"])
        response = self.json_post(self.post_url, self.fix())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "2")
        self.assertEqual(TripLocation.objects.count(), 1)

    @override_settings(LOCATION_MIN_SAMPLE_INTERVAL_SECONDS=0)
    def test_parent_scope_fresh_stale_completed_and_observation_order(self):
        self.login(self.parent)
        self.assertEqual(self.client.get(self.read_url).json()["state"], "no_fix")
        self.login()
        self.trip.status = "active"
        self.trip.save()
        current = self.fix()
        self.json_post(self.post_url, current)
        old = self.fix()
        old["observed_at"] = (timezone.now() - timedelta(minutes=2)).isoformat()
        self.json_post(self.post_url, old)
        self.login(self.parent)
        response = self.client.get(self.read_url)
        self.assertEqual(response.json()["state"], "fresh")
        self.assertEqual(response.json()["observed_at"], current["observed_at"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        TripLocation.objects.update(observed_at=timezone.now() - timedelta(minutes=2))
        self.assertEqual(self.client.get(self.read_url).json()["state"], "stale")
        self.trip.status = "completed"
        self.trip.save()
        self.assertEqual(self.client.get(self.read_url).json()["state"], "completed")
        self.login(self.outsider)
        self.assertEqual(self.client.get(self.read_url).status_code, 404)

    def test_service_rechecks_changed_trip_and_assignment(self):
        payload = validate_location_json(json.dumps(self.fix()).encode())
        with self.assertRaises(LocationTripStateError):
            save_sample_once(self.trip, payload, user=self.monitor_user)
        with self.assertRaises(PermissionDenied):
            save_sample_once(self.trip, payload, user=self.other_user)


class ManagementTests(DomainCase):
    def test_crud_and_protected_delete(self):
        self.login(self.admin)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
        for resource in ["routes", "stops", "buses", "monitors", "students", "trips", "attendance", "parent-access"]:
            self.assertEqual(self.client.get(f"/manage/{resource}/").status_code, 200)
            self.assertEqual(self.client.get(f"/manage/{resource}/new/").status_code, 200)
        self.assertEqual(self.client.get("/manage/unknown/").status_code, 404)
        self.assertEqual(self.client.post("/manage/routes/new/", {"route_name": "New route"}).status_code, 302)
        route = Route.objects.get(route_name="New route")
        path = f"/manage/routes/{route.pk}"
        self.assertEqual(self.client.get(path + "/edit/").status_code, 200)
        self.assertEqual(self.client.post(path + "/edit/", {"route_name": "Updated"}).status_code, 302)
        route.refresh_from_db()
        self.assertEqual(route.route_name, "Updated")
        self.assertEqual(self.client.post(path + "/edit/", {"route_name": ""}).status_code, 200)
        self.assertEqual(self.client.get(path + "/delete/").status_code, 200)
        self.assertTrue(Route.objects.filter(pk=route.pk).exists())
        self.assertEqual(self.client.post(path + "/delete/").status_code, 302)
        self.assertFalse(Route.objects.filter(pk=route.pk).exists())
        self.client.post(f"/manage/routes/{self.route.pk}/delete/")
        self.assertTrue(Route.objects.filter(pk=self.route.pk).exists())
        self.assertEqual(self.client.post("/manage/routes/new/", {"route_name": self.route.route_name}).status_code, 200)

    def test_parent_page_scope_and_empty_states(self):
        self.login(self.outsider)
        self.assertEqual(self.client.get("/parents/live/").status_code, 200)
        self.assertEqual(self.client.get(f"/parents/live/?child={self.child.pk}").status_code, 404)
        self.login(self.parent)
        for query, code in [("", 200), (f"?child={self.child.pk}&trip={self.trip.pk}", 200),
            ("?child=bad", 404), ("?trip=99999", 404)]:
            self.assertEqual(self.client.get("/parents/live/" + query).status_code, code)
        self.trip.status = "active"
        self.trip.save()
        self.assertEqual(self.client.get("/parents/live/").context["trip"], self.trip)

    def test_csrf_enforced_for_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.monitor_user)
        path = f"/trips/{self.trip.pk}/start/"
        self.assertEqual(client.post(path).status_code, 403)
        client.get(f"/trips/{self.trip.pk}/")
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(path, HTTP_X_CSRFTOKEN=token).status_code, 302)
