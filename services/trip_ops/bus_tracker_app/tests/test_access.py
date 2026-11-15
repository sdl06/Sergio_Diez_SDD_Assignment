"""Named regressions for changing access and tracking."""
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta

from bus_tracker_app.models import Monitor, Trip
from bus_tracker_app.tracking.models import ParentChildAccess, TripLocation
from bus_tracker_app.tracking.views import save_sample_once, validate_location_json
from .helpers import DomainCase, grant
import json


class AdministratorTrackingTests(DomainCase):
    def test_admin_sees_all_children_without_parent_links(self):
        self.login(self.admin)
        response = self.client.get("/parents/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({child["id"] for child in response.json()["children"]}, {self.child.pk, self.sibling.pk, self.foreign_child.pk})

    def test_admin_reads_location_and_eta_across_routes(self):
        other_trip = Trip.objects.create(route=self.other, bus=self.bus, monitor=self.other_monitor,
            date=self.trip.date, leg=1, status=Trip.Status.ACTIVE)
        other_trip.students.add(self.foreign_child)
        for trip, child in ((self.trip, self.child), (other_trip, self.foreign_child)):
            Trip.objects.filter(pk=trip.pk).update(status=Trip.Status.ACTIVE)
            TripLocation.objects.create(trip=trip, source="test", **validate_location_json(
                json.dumps({**self.fix(), "observed_at": (timezone.now() - timedelta(minutes=2)).isoformat()}).encode()))
            self.login(self.admin)
            root = f"/api/children/{child.pk}/trips/{trip.pk}/"
            for suffix in ("location/", "eta/"):
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


    def test_monitor_location_permission_is_reported_and_enforced(self):
        self.login()
        path = f"/trips/{self.trip.pk}/"
        response = self.client.get(path)
        self.assertTrue(response.json()["can_share"])
        self.assertEqual(response.json()["status"], Trip.Status.PREPARED)
        self.trip.status = Trip.Status.ACTIVE
        self.trip.save()
        self.assertEqual(self.client.get(path).json()["status"], Trip.Status.ACTIVE)
        self.monitor_user.user_permissions.remove(*self.monitor_user.user_permissions.filter(codename="post_trip_location"))
        response = self.client.get(path)
        self.assertFalse(response.json()["can_share"])
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
        grant(self.outsider, "prepare_trip", "post_trip_location")
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


    def test_deleted_parent_link_revokes_all_child_endpoints(self):
        self.login(self.parent)
        root = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/"
        self.assertEqual(self.client.get(root + "location/").status_code, 200)
        ParentChildAccess.objects.filter(user=self.parent, student=self.child).delete()
        for suffix in ["location/", "eta/"]:
            with self.subTest(endpoint=suffix):
                self.assertEqual(self.client.get(root + suffix).status_code, 404)
        self.assertEqual(self.client.get(f"/parents/live/?child={self.child.pk}").status_code, 404)


    def test_monitor_moved_to_another_route_cannot_prepare_original_route(self):
        self.login()
        Monitor.objects.filter(pk=self.monitor.pk).update(route=self.other)
        self.assertEqual(self.client.get(f"/routes/{self.route.pk}/prepare/").status_code, 403)
        self.assertEqual(self.client.post(f"/routes/{self.route.pk}/prepare/submit/",
            {"bus": self.bus.pk, "date": self.trip.date, "leg": 2}).status_code, 403)
        self.assertFalse(Trip.objects.filter(leg=2).exists())


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
