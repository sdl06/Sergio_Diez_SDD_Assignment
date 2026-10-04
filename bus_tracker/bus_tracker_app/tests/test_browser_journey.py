"""Opt-in Chromium E2E: actual pages, CSRF, JS, SQLite and simulated GPS.

Only the traffic provider and external map tiles are isolated. This is not a
claim about physical GPS hardware, bus restrictions or TomTom road accuracy.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connections
from django.test import override_settings
from django.utils import timezone

from bus_tracker_app.models import Bus, Route, Student, Trip
from bus_tracker_app.attendance.models import AbsenceNotice, StudentAttendance
from bus_tracker_app.tracking.eta import ProviderRoute
from bus_tracker_app.tracking.models import TripLocation
from .helpers import grant


@skipUnless(os.environ.get("RUN_BROWSER_TESTS") == "1", "Set RUN_BROWSER_TESTS=1 after installing Chromium")
@override_settings(LOCATION_MIN_SAMPLE_INTERVAL_SECONDS=0)
class BrowserJourneyTests(StaticLiveServerTestCase):
    host = "localhost"

    def test_madrid_journey_from_creation_to_completion(self):
        from playwright.sync_api import sync_playwright, expect
        User.objects.create_superuser("admin", "admin@example.test", "test-pass")
        monitor = grant(User.objects.create_user("monitor", password="test-pass"),
            "prepare_trip", "record_trip_attendance", "post_trip_location")
        parent = User.objects.create_user("parent", password="test-pass")
        errors = []
        # Playwright's sync facade runs an event loop in this thread. Keep ORM
        # inspection on a dedicated synchronous worker, without disabling
        # Django's async-safety checks. Evaluate querysets inside that worker.
        with ThreadPoolExecutor(max_workers=1) as database, sync_playwright() as playwright, patch(
            "bus_tracker_app.tracking.eta.TomTomRoutingProvider.estimate_route",
            return_value=ProviderRoute(180, 30, 900),
        ) as provider:
            def db(function, *args, **kwargs):
                def query():
                    try:
                        return function(*args, **kwargs)
                    finally:
                        connections.close_all()
                return database.submit(query).result()

            browser = playwright.chromium.launch()
            admin_context = browser.new_context()
            monitor_context = browser.new_context(permissions=["geolocation"],
                geolocation={"latitude": 40.4199, "longitude": -3.6895, "accuracy": 5})
            parent_context = browser.new_context()
            for context in [admin_context, monitor_context, parent_context]:
                # Test the generated marker URL, not a third-party map renderer.
                context.route("https://www.openstreetmap.org/**", lambda route: route.fulfill(body="Map isolated for E2E"))
            admin_page, monitor_page, parent_page = [context.new_page()
                for context in [admin_context, monitor_context, parent_context]]
            for page in [admin_page, monitor_page, parent_page]:
                page.on("pageerror", lambda error: errors.append(str(error)))

            def login(page, username):
                page.goto(self.live_server_url + "/accounts/login/")
                page.locator("#id_username").fill(username)
                page.locator("#id_password").fill("test-pass")
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page).to_have_url(self.live_server_url + "/")
                expect(page.locator("#id_password")).to_have_count(0)

            def create(resource, fields):
                admin_page.goto(self.live_server_url + f"/manage/{resource}/new/")
                for field, value in fields.items():
                    locator = admin_page.locator(f"#id_{field}")
                    if locator.evaluate("element => element.tagName") == "SELECT":
                        locator.select_option(str(value))
                    else:
                        locator.fill(str(value))
                admin_page.get_by_role("button", name="Create record", exact=True).click()
                expect(admin_page).to_have_url(self.live_server_url + f"/manage/{resource}/")

            try:
                login(admin_page, "admin")
                create("routes", {"route_name": "Madrid · Alcalá–Prado"})
                route = db(Route.objects.get, route_name="Madrid · Alcalá–Prado")
                create("stops", {"descriptor": "Cibeles, Paseo del Prado", "assigned_route": route.pk,
                    "latitude": 40.4181, "longitude": -3.6938,
                    "configured_leg1_arrival": "08:30", "configured_leg2_arrival": "17:00"})
                stop = db(route.stops.get)
                create("buses", {"license_plate": "E2E123", "capacity": 30,
                    "bus_model": "Test bus", "bus_contractor": "Test operator", "current_longitude": 0})
                bus = db(Bus.objects.get, license_plate="E2E123")
                create("monitors", {"name": "Monitor", "route": route.pk, "user": monitor.pk})
                for name in ["Ana", "Luis"]:
                    create("students", {"name": name, "date_of_birth": "2015-01-01",
                        "route": route.pk, "assigned_stop": stop.pk})
                    student = db(Student.objects.get, name=name)
                    create("parent-access", {"user": parent.pk, "student": student.pk})
                child = db(Student.objects.get, name="Ana")
                sibling = db(Student.objects.get, name="Luis")

                login(monitor_page, "monitor")
                monitor_page.goto(self.live_server_url + f"/admin/trips/new/?route={route.pk}")
                monitor_page.locator("#id_bus").select_option(str(bus.pk))
                monitor_page.locator("#id_date").fill(timezone.localdate().isoformat())
                monitor_page.locator("#id_leg").select_option("1")
                monitor_page.get_by_role("button", name="Prepare and open trip").click()
                expect(monitor_page.get_by_role("button", name="Start trip", exact=True)).to_be_visible()
                trip = db(Trip.objects.get, route=route, leg=1)
                self.assertSetEqual(db(lambda: set(trip.students.values_list("pk", flat=True))), {child.pk, sibling.pk})

                login(parent_page, "parent")
                parent_page.goto(self.live_server_url + f"/parents/live/?child={child.pk}&trip={trip.pk}")
                expect(parent_page.locator("[data-absent]")).to_be_enabled()
                parent_page.locator("[data-absent]").check()
                parent_page.get_by_role("button", name="Save notice").click()
                expect(parent_page.locator("[data-notice-status]")).to_have_text("Absence reported for this journey.")
                self.assertEqual(db(AbsenceNotice.objects.get, student=child).status, "reported")
                parent_page.locator("[data-absent]").uncheck()
                parent_page.get_by_role("button", name="Save notice").click()
                expect(parent_page.locator("[data-notice-status]")).to_have_text("Absence notice cancelled.")
                self.assertFalse(db(StudentAttendance.objects.exists))

                monitor_page.get_by_role("button", name="Start trip", exact=True).click()
                expect(monitor_page.get_by_role("button", name="Share location", exact=True)).to_be_visible()
                for student, status in [(child, "present"), (sibling, "absent")]:
                    row = monitor_page.locator(f'[data-attendance-row][data-student-id="{student.pk}"]')
                    expect(row.locator("select")).to_be_enabled()
                    row.locator("select").select_option(status)
                    row.get_by_role("button", name="Save observation").click()
                    expect(row.locator("[data-child-facts]")).to_contain_text(f"Observed: {status}")
                self.assertEqual(db(lambda: StudentAttendance.objects.filter(status="present").count()), 1)
                self.assertEqual(db(lambda: StudentAttendance.objects.filter(status="absent").count()), 1)

                monitor_page.get_by_role("button", name="Share location", exact=True).click()
                expect(monitor_page.locator("[data-share-status]")).to_contain_text("Sharing location", timeout=15000)
                self.assertEqual(db(lambda: TripLocation.objects.filter(trip=trip).count()), 1)
                # Simulated IoT input through Chromium's geolocation API; the
                # app's real watchPosition callback posts each sample with CSRF.
                for latitude, longitude in [(40.4191, -3.6916), (40.4181, -3.6938)]:
                    with monitor_page.expect_response(lambda response: response.request.method == "POST"
                        and response.url.endswith(f"/api/trips/{trip.pk}/locations/")) as uploaded:
                        monitor_context.set_geolocation({"latitude": latitude, "longitude": longitude, "accuracy": 5})
                    self.assertEqual(uploaded.value.status, 201)
                    parent_page.get_by_role("button", name="Refresh update").click()
                    expect(parent_page.locator("[data-bus-map]")).to_have_attribute("src", re.compile(
                        f"marker={latitude}%2C{longitude}"), timeout=15000)
                self.assertEqual(db(lambda: TripLocation.objects.filter(trip=trip).count()), 3)
                self.assertGreaterEqual(provider.call_count, 1)
                expect(parent_page.locator("[data-estimated]")).not_to_have_text("Not available")
                expect(parent_page.locator("[data-child-observation]")).to_contain_text("Monitor observation: present")
                expect(parent_page.locator("[data-absent]")).to_be_disabled()
                admin_page.goto(self.live_server_url + f"/parents/live/?child={child.pk}&trip={trip.pk}")
                expect(admin_page.locator("#child option")).to_have_count(2)
                expect(admin_page.locator("[data-bus-map]")).to_be_visible()
                expect(admin_page.locator("[data-estimated]")).not_to_have_text("Not available")
                expect(admin_page.locator("[data-notice-status]")).to_have_text("Absence notice cancelled.")
                expect(admin_page.locator("[data-absent]")).to_be_disabled()
                artifact_dir = settings.BASE_DIR.parent / "output" / "testing"
                artifact_dir.mkdir(parents=True, exist_ok=True)
                parent_page.screenshot(path=str(artifact_dir / "parent-live-e2e.png"), full_page=True)

                monitor_page.get_by_role("button", name="Complete trip", exact=True).click()
                expect(monitor_page.locator("[data-location-sender]")).to_have_count(0)
                parent_page.get_by_role("button", name="Refresh update").click()
                expect(parent_page.locator("[data-journey-status]")).to_contain_text("Trip completed")
                db(trip.refresh_from_db)
                self.assertEqual(trip.status, "completed")
                self.assertIsNotNone(trip.started_at)
                self.assertIsNotNone(trip.completed_at)
                self.assertEqual(errors, [], "Uncaught browser JavaScript errors")
            except Exception:
                artifact_dir = settings.BASE_DIR.parent / "output" / "testing"
                artifact_dir.mkdir(parents=True, exist_ok=True)
                for name, page in [("admin", admin_page), ("monitor", monitor_page), ("parent", parent_page)]:
                    page.screenshot(path=str(artifact_dir / f"failure-{name}.png"), full_page=True)
                raise
            finally:
                browser.close()
