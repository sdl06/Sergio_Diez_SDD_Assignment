"""Named regressions for changing access and independent daily journey legs."""
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils import timezone
from datetime import timedelta

from bus_tracker_app.attendance.models import AbsenceNotice, StudentAttendance
from bus_tracker_app.attendance.services import build_attendance_roster, record_attendance, set_absence_notice
from bus_tracker_app.models import Monitor, Trip
from bus_tracker_app.tracking.models import ParentChildAccess, TripLocation
from bus_tracker_app.tracking.views import save_sample_once, validate_location_json
from bus_tracker_app.trips.services import transition_trip
from .helpers import DomainCase, grant
import json


class AdministratorTrackingTests(DomainCase):
    def test_admin_sees_all_children_without_parent_links(self):
        self.login(self.admin)
        response = self.client.get("/parents/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["children"]), {self.child, self.sibling, self.foreign_child})
        self.assertFalse(response.context["can_report_absence"])
        self.assertContains(response, "All journeys")

    def test_admin_reads_location_eta_and_notice_across_routes(self):
        other_trip = Trip.objects.create(route=self.other, bus=self.bus, monitor=self.other_monitor,
            date=self.trip.date, leg=1, status=Trip.Status.ACTIVE)
        other_trip.students.add(self.foreign_child)
        for trip, child in ((self.trip, self.child), (other_trip, self.foreign_child)):
            Trip.objects.filter(pk=trip.pk).update(status=Trip.Status.ACTIVE)
            TripLocation.objects.create(trip=trip, source="test", **validate_location_json(
                json.dumps({**self.fix(), "observed_at": (timezone.now() - timedelta(minutes=2)).isoformat()}).encode()))
            self.login(self.admin)
            root = f"/api/children/{child.pk}/trips/{trip.pk}/"
            for suffix in ("location/", "eta/", "absence/"):
                with self.subTest(child=child.name, endpoint=suffix):
                    response = self.client.get(root + suffix)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("no-store", {value.strip() for value in response.headers["Cache-Control"].split(",")})
            self.assertEqual(self.client.get(root + "location/").json()["latitude"], 40.4199)
            self.assertEqual(self.client.get(f"/parents/live/?child={child.pk}&trip={trip.pk}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/children/{self.foreign_child.pk}/trips/{self.trip.pk}/location/").status_code, 404)

    def test_management_permission_grants_reads_but_staff_flag_does_not(self):
        self.outsider.is_staff = True
        self.outsider.save(update_fields=["is_staff"])
        self.login(self.outsider)
        path = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/location/"
        self.assertEqual(self.client.get(path).status_code, 404)
        grant(self.outsider, "manage_operational_data")
        self.assertEqual(self.client.get(path).status_code, 200)

    def test_admin_read_access_does_not_grant_parent_notice_writes(self):
        self.login(self.admin)
        root = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/absence/"
        self.assertEqual(self.client.get(root).status_code, 200)
        self.assertEqual(self.json_post(root, {"absent": True}).status_code, 404)
        self.assertFalse(AbsenceNotice.objects.exists())

    def test_monitor_share_control_follows_status_and_permission(self):
        self.login()
        path = f"/trips/{self.trip.pk}/"
        response = self.client.get(path)
        self.assertContains(response, "Start this trip to enable location sharing.")
        self.assertContains(response, "data-share-start disabled")
        self.assertNotContains(response, "data-location-sender")
        self.trip.status = Trip.Status.ACTIVE
        self.trip.save()
        self.assertContains(self.client.get(path), "data-location-sender")
        self.monitor_user.user_permissions.remove(*self.monitor_user.user_permissions.filter(codename="post_trip_location"))
        response = self.client.get(path)
        self.assertNotContains(response, "data-share-start")
        self.assertEqual(self.json_post(f"/api/trips/{self.trip.pk}/locations/", self.fix()).status_code, 403)


class AccessChangesTests(DomainCase):
    def revoke(self, codename):
        self.monitor_user.user_permissions.remove(
            *self.monitor_user.user_permissions.filter(codename=codename)
        )

    def activate(self):
        self.trip.status = Trip.Status.ACTIVE
        self.trip.save()

    def reassign(self):
        grant(self.outsider, "prepare_trip", "post_trip_location", "record_trip_attendance")
        replacement = Monitor.objects.create(name="Replacement", route=self.route, user=self.outsider)
        Trip.objects.filter(pk=self.trip.pk).update(monitor=replacement)
        # Deliberately keep self.trip stale to exercise service-level rechecks.

    def test_revoked_prepare_permission_blocks_preparation(self):
        self.login()
        self.assertEqual(self.client.get(f"/routes/{self.route.pk}/prepare/").status_code, 200)
        self.revoke("prepare_trip")
        response = self.client.post(f"/routes/{self.route.pk}/prepare/submit/",
            {"bus": self.bus.pk, "date": self.trip.date, "leg": 2})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Trip.objects.filter(leg=2).exists())

    def test_revoked_prepare_permission_blocks_trip_start(self):
        self.login()
        self.revoke("prepare_trip")
        self.assertEqual(self.client.post(f"/trips/{self.trip.pk}/start/").status_code, 403)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, Trip.Status.PREPARED)
        self.assertIsNone(self.trip.started_at)

    def test_revoked_location_permission_blocks_post(self):
        self.activate()
        self.login()
        self.revoke("post_trip_location")
        response = self.json_post(f"/api/trips/{self.trip.pk}/locations/", self.fix())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TripLocation.objects.exists())

    def test_revoked_attendance_permission_blocks_read_and_write(self):
        self.activate()
        self.login()
        self.revoke("record_trip_attendance")
        url = f"/api/trips/{self.trip.pk}/attendance/"
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.json_post(url + f"{self.child.pk}/", {"status": "present"}).status_code, 403)
        self.assertFalse(StudentAttendance.objects.exists())

    def test_deleted_parent_link_revokes_all_child_endpoints(self):
        self.login(self.parent)
        root = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/"
        self.assertEqual(self.client.get(root + "absence/").status_code, 200)
        ParentChildAccess.objects.filter(user=self.parent, student=self.child).delete()
        for suffix in ["absence/", "location/", "eta/"]:
            with self.subTest(endpoint=suffix):
                self.assertEqual(self.client.get(root + suffix).status_code, 404)
        self.assertEqual(self.json_post(root + "absence/", {"absent": True}).status_code, 404)
        self.assertEqual(self.client.get(f"/parents/live/?child={self.child.pk}").status_code, 404)
        self.assertFalse(AbsenceNotice.objects.exists())

    def test_deleted_parent_link_is_rechecked_by_direct_service(self):
        ParentChildAccess.objects.filter(user=self.parent, student=self.child).delete()
        with self.assertRaises(Http404):
            set_absence_notice(user=self.parent, child=self.child, trip=self.trip, absent=True)
        self.assertFalse(AbsenceNotice.objects.exists())

    def test_monitor_moved_to_another_route_cannot_prepare_original_route(self):
        self.login()
        Monitor.objects.filter(pk=self.monitor.pk).update(route=self.other)
        self.assertEqual(self.client.get(f"/routes/{self.route.pk}/prepare/").status_code, 403)
        self.assertEqual(self.client.post(f"/routes/{self.route.pk}/prepare/submit/",
            {"bus": self.bus.pk, "date": self.trip.date, "leg": 2}).status_code, 403)
        self.assertFalse(Trip.objects.filter(leg=2).exists())

    def test_reassigned_trip_rejects_old_monitor_attendance_even_with_stale_trip(self):
        self.activate()
        self.reassign()
        with self.assertRaises(PermissionDenied):
            record_attendance(user=self.monitor_user, trip=self.trip, student_id=self.child.pk, status="present")
        self.assertFalse(StudentAttendance.objects.exists())

    def test_reassigned_trip_rejects_old_monitor_gps_even_with_stale_trip(self):
        self.activate()
        payload = validate_location_json(json.dumps(self.fix()).encode())
        self.reassign()
        with self.assertRaises(PermissionDenied):
            save_sample_once(self.trip, payload, user=self.monitor_user)
        self.assertFalse(TripLocation.objects.exists())

    def test_reassigned_trip_is_hidden_from_old_monitor_workspace(self):
        self.login()
        self.reassign()
        for path in [f"/trips/{self.trip.pk}/", f"/trips/{self.trip.pk}/state/"]:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post(f"/trips/{self.trip.pk}/start/").status_code, 404)
        self.login(self.outsider)
        self.assertEqual(self.client.get(f"/trips/{self.trip.pk}/").status_code, 200)


class LegIsolationTests(DomainCase):
    def setUp(self):
        self.afternoon = Trip.objects.create(route=self.route, bus=self.bus, monitor=self.monitor,
            date=self.trip.date, leg=Trip.Leg.AFTERNOON)
        self.afternoon.students.set([self.child, self.sibling])

    def test_parent_notices_are_independent_by_leg(self):
        morning_notice, _ = set_absence_notice(user=self.parent, child=self.child, trip=self.trip, absent=True)
        afternoon_notice, _ = set_absence_notice(user=self.parent, child=self.child, trip=self.afternoon, absent=False)
        self.assertNotEqual(morning_notice.pk, afternoon_notice.pk)
        self.assertEqual(AbsenceNotice.objects.count(), 2)
        self.assertEqual(build_attendance_roster(self.trip)["students"][0]["absence_notice"], "reported")
        self.assertEqual(build_attendance_roster(self.afternoon)["students"][0]["absence_notice"], "cancelled")
        self.login(self.parent)
        for trip, expected in [(self.trip, True), (self.afternoon, False)]:
            response = self.client.get(f"/api/children/{self.child.pk}/trips/{trip.pk}/absence/")
            self.assertEqual(response.json()["absent"], expected)

    def test_monitor_observations_are_independent_by_leg(self):
        Trip.objects.filter(pk__in=[self.trip.pk, self.afternoon.pk]).update(status=Trip.Status.ACTIVE)
        morning, _ = record_attendance(user=self.monitor_user, trip=self.trip,
            student_id=self.child.pk, status="present")
        afternoon, _ = record_attendance(user=self.monitor_user, trip=self.afternoon,
            student_id=self.child.pk, status="absent")
        self.assertNotEqual(morning.pk, afternoon.pk)
        self.assertEqual(StudentAttendance.objects.count(), 2)
        self.assertEqual(build_attendance_roster(self.trip)["students"][0]["attendance"], "present")
        self.assertEqual(build_attendance_roster(self.afternoon)["students"][0]["attendance"], "absent")
        self.login(self.parent)
        for trip, expected in [(self.trip, "present"), (self.afternoon, "absent")]:
            response = self.client.get(f"/api/children/{self.child.pk}/trips/{trip.pk}/absence/")
            self.assertEqual(response.json()["attendance"], expected)

    def test_completing_morning_does_not_lock_afternoon_notice(self):
        transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target=Trip.Status.ACTIVE)
        transition_trip(user=self.monitor_user, trip_id=self.trip.pk, target=Trip.Status.COMPLETED)
        notice, created = set_absence_notice(user=self.parent, child=self.child, trip=self.afternoon, absent=True)
        self.assertTrue(created)
        self.assertEqual(notice.trip_id, self.afternoon.pk)
        self.afternoon.refresh_from_db()
        self.assertEqual(self.afternoon.status, Trip.Status.PREPARED)
