from django.test import Client

from bus_tracker_app.models import ParentChildAccess, Trip

from .helpers import DomainCase, grant


class AttendanceContextTests(DomainCase):
    def setUp(self):
        self.url = f"/api/trips/{self.trip.pk}/attendance-context/"

    def test_only_assigned_monitor_with_permission_can_record(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.login()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        grant(self.monitor_user, "record_trip_attendance")
        grant(self.other_user, "record_trip_attendance")
        Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.ACTIVE)
        self.login(self.other_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context = response.json()
        self.assertEqual(context["actor_id"], self.monitor_user.pk)
        self.assertEqual(context["status"], "active")
        self.assertTrue(context["can_record_attendance"])
        self.assertEqual({row["student_id"] for row in context["roster"]}, {self.child.pk, self.sibling.pk})

    def test_parent_context_contains_only_linked_children(self):
        ParentChildAccess.objects.filter(user=self.parent, student=self.sibling).delete()
        self.login(self.parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        context = response.json()
        self.assertEqual(context["parent_child_ids"], [self.child.pk])
        self.assertEqual([row["student_id"] for row in context["roster"]], [self.child.pk])
        self.assertFalse(context["can_record_attendance"])

    def test_write_context_requires_csrf(self):
        grant(self.monitor_user, "record_trip_attendance")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.monitor_user)
        self.assertEqual(client.post(self.url).status_code, 403)
        token = client.get("/accounts/login/").json()["csrf_token"]
        self.assertEqual(client.post(self.url, headers={"X-CSRFToken": token}).status_code, 200)
