from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from .models import Bus, Monitor, Route, Stop, Student, Trip


class FrontendPageTests(TestCase):
    def setUp(self):
        self.north_route = Route.objects.create(route_name="North route")
        self.riverside_route = Route.objects.create(route_name="Riverside route")
        north_stop = Stop.objects.create(
            descriptor="Oak Street",
            assigned_route=self.north_route,
            longitude=1.0,
            latitude=2.0,
            configured_leg1_arrival=time(8, 0),
            configured_leg2_arrival=time(15, 0),
        )
        riverside_stop = Stop.objects.create(
            descriptor="River Park",
            assigned_route=self.riverside_route,
            longitude=3.0,
            latitude=4.0,
            configured_leg1_arrival=time(8, 10),
            configured_leg2_arrival=time(15, 10),
        )
        self.north_student = Student.objects.create(
            name="Maya Patel", date_of_birth=date(2016, 1, 1), route=self.north_route, assigned_stop=north_stop
        )
        Student.objects.create(
            name="Leo Garcia", date_of_birth=date(2017, 1, 1), route=self.riverside_route, assigned_stop=riverside_stop
        )
        Monitor.objects.create(name="Jordan Lee", route=self.north_route)
        Monitor.objects.create(name="Sam Rivera", route=self.riverside_route)

    def test_home_links_to_both_user_journeys(self):
        response = self.client.get(reverse("bus_tracker_app:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("bus_tracker_app:create_trip"))
        self.assertContains(response, reverse("bus_tracker_app:parent_live"))

    def test_trip_builder_contains_children_and_form_controls(self):
        response = self.client.get(reverse("bus_tracker_app:create_trip"), {"route": self.north_route.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a new trip")
        self.assertContains(response, "Maya Patel")
        self.assertContains(response, "Oak Street")
        self.assertContains(response, "Jordan Lee")
        self.assertContains(response, f'value="{self.north_student.pk}"')
        self.assertNotContains(response, "Leo Garcia")
        self.assertNotContains(response, "Sam Rivera")
        self.assertContains(response, "data-trip-form")

    def test_trip_builder_prompts_for_route_before_listing_children(self):
        response = self.client.get(reverse("bus_tracker_app:create_trip"))

        self.assertContains(response, "Select a route to see its children.")
        self.assertNotContains(response, "Maya Patel")
        self.assertNotContains(response, "Leo Garcia")

    def test_trip_builder_shows_empty_route_message(self):
        empty_route = Route.objects.create(route_name="Central route")

        response = self.client.get(reverse("bus_tracker_app:create_trip"), {"route": empty_route.pk})

        self.assertContains(response, "No children are assigned to this route yet.")
        self.assertNotContains(response, "Maya Patel")

    def test_trip_builder_rejects_unknown_route(self):
        for route_id in ("99999", "not-a-route"):
            with self.subTest(route_id=route_id):
                response = self.client.get(reverse("bus_tracker_app:create_trip"), {"route": route_id})
                self.assertEqual(response.status_code, 404)

    def test_parent_page_does_not_claim_unrecorded_live_activity(self):
        response = self.client.get(reverse("bus_tracker_app:parent_live"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No live updates available")
        self.assertNotContains(response, "Maya Patel")
        self.assertNotContains(response, "Bus left River Park")


class InitialDataManagementTests(TestCase):
    def test_management_page_is_the_entry_point_for_initial_records(self):
        response = self.client.get(reverse("bus_tracker_app:management_home"))

        self.assertEqual(Route.objects.count(), 0)
        self.assertEqual(Student.objects.count(), 0)
        self.assertContains(response, "Set up initial data here")
        self.assertContains(response, reverse("bus_tracker_app:record_create", kwargs={"resource": "routes"}))
        self.assertContains(response, reverse("bus_tracker_app:record_create", kwargs={"resource": "students"}))

    def test_initial_route_can_be_added_through_management_form(self):
        response = self.client.post(
            reverse("bus_tracker_app:record_create", kwargs={"resource": "routes"}),
            {"route_name": "New route"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Route.objects.filter(route_name="New route").exists())


class CrudViewTests(TestCase):
    def setUp(self):
        self.north_route = Route.objects.create(route_name="North route")
        self.riverside_route = Route.objects.create(route_name="Riverside route")
        self.north_stop = Stop.objects.create(
            descriptor="Oak Street",
            assigned_route=self.north_route,
            longitude=1.0,
            latitude=2.0,
            configured_leg1_arrival=time(8, 0),
            configured_leg2_arrival=time(15, 0),
        )
        self.student = Student.objects.create(
            name="Maya Patel",
            date_of_birth=date(2016, 1, 1),
            route=self.north_route,
            assigned_stop=self.north_stop,
        )
        self.north_monitor = Monitor.objects.create(name="Jordan Lee", route=self.north_route)
        self.riverside_monitor = Monitor.objects.create(name="Sam Rivera", route=self.riverside_route)
        self.bus = Bus.objects.create(
            license_plate="BUS-007",
            capacity=40,
            bus_model="Sprinter",
            bus_contractor="School Transport",
        )

    def test_route_can_be_created_updated_and_deleted(self):
        create_url = reverse("bus_tracker_app:record_create", kwargs={"resource": "routes"})
        response = self.client.post(create_url, {"route_name": "Central route"})
        self.assertRedirects(response, reverse("bus_tracker_app:record_list", kwargs={"resource": "routes"}))

        route = Route.objects.get(route_name="Central route")
        update_url = reverse("bus_tracker_app:record_update", kwargs={"resource": "routes", "pk": route.pk})
        response = self.client.post(update_url, {"route_name": "Central express"})
        self.assertRedirects(response, reverse("bus_tracker_app:record_list", kwargs={"resource": "routes"}))
        route.refresh_from_db()
        self.assertEqual(route.route_name, "Central express")

        delete_url = reverse("bus_tracker_app:record_delete", kwargs={"resource": "routes", "pk": route.pk})
        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("bus_tracker_app:record_list", kwargs={"resource": "routes"}))
        self.assertFalse(Route.objects.filter(pk=route.pk).exists())

    def test_trip_form_creates_trip_and_assigns_students(self):
        response = self.client.post(
            reverse("bus_tracker_app:record_create", kwargs={"resource": "trips"}),
            {
                "route": self.north_route.pk,
                "bus": self.bus.pk,
                "monitor": self.north_monitor.pk,
                "date": "2026-09-22",
                "students": [self.student.pk],
            },
        )

        self.assertRedirects(response, reverse("bus_tracker_app:record_list", kwargs={"resource": "trips"}))
        trip = Trip.objects.get(route=self.north_route, date=date(2026, 9, 22))
        self.assertQuerySetEqual(trip.students.all(), [self.student])

    def test_trip_form_rejects_monitor_from_another_route(self):
        response = self.client.post(
            reverse("bus_tracker_app:record_create", kwargs={"resource": "trips"}),
            {
                "route": self.north_route.pk,
                "bus": self.bus.pk,
                "monitor": self.riverside_monitor.pk,
                "date": "2026-09-22",
                "students": [self.student.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The monitor must be assigned to the selected route.")
        self.assertFalse(Trip.objects.exists())
