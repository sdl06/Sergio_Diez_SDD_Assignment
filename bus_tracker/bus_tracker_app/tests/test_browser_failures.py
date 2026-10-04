"""Focused real-browser regressions for offline, stale and denied-access states.

Browser networking/geolocation is controlled deliberately. Application scripts,
HTTP authorization, CSRF and database writes are real; TomTom is isolated.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.db import connections
from django.test import override_settings
from django.utils import timezone

from bus_tracker_app.attendance.models import StudentAttendance
from bus_tracker_app.models import Trip
from bus_tracker_app.tracking.eta import ProviderRoute
from bus_tracker_app.tracking.models import ParentChildAccess, TripLocation
from .helpers import fixtures


@skipUnless(os.environ.get("RUN_BROWSER_TESTS") == "1", "Set RUN_BROWSER_TESTS=1 after installing Chromium")
@override_settings(LOCATION_MIN_SAMPLE_INTERVAL_SECONDS=0)
class BrowserFailureTests(StaticLiveServerTestCase):
    host = "localhost"

    def setUp(self):
        from playwright.sync_api import sync_playwright, expect
        super().setUp()
        for key, value in fixtures().items():
            setattr(self, key, value)
        Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.ACTIVE)
        self.expect = expect
        self.errors = []
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.database = stack.enter_context(ThreadPoolExecutor(max_workers=1))
        playwright = stack.enter_context(sync_playwright())
        self.browser = playwright.chromium.launch()
        stack.callback(self.browser.close)
        self.provider = stack.enter_context(patch(
            "bus_tracker_app.tracking.eta.TomTomRoutingProvider.estimate_route",
            return_value=ProviderRoute(180, 30, 900)))
        self.context = self.browser.new_context(permissions=["geolocation"],
            geolocation={"latitude": 40.4199, "longitude": -3.6895, "accuracy": 5})
        # Finish interceptors before disposing the request context/browser.
        self.addCleanup(self.context.unroute_all, behavior="wait")
        self.context.route("https://www.openstreetmap.org/**", lambda route: route.fulfill(body="Map isolated for E2E"))
        self.page = self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.assertEqual(self.errors, [], "Uncaught browser JavaScript errors")
        super().tearDown()

    def db(self, function, *args, **kwargs):
        def query():
            try:
                return function(*args, **kwargs)
            finally:
                connections.close_all()
        return self.database.submit(query).result()

    def login(self, username):
        self.page.goto(self.live_server_url + "/accounts/login/")
        self.page.locator("#id_username").fill(username)
        self.page.locator("#id_password").fill("test-pass")
        self.page.get_by_role("button", name="Sign in", exact=True).click()
        self.expect(self.page).to_have_url(self.live_server_url + "/")
        self.expect(self.page.locator("#id_password")).to_have_count(0)

    def monitor_page(self):
        self.login("monitor")
        self.page.goto(self.live_server_url + f"/trips/{self.trip.pk}/")
        self.expect(self.page.locator("[data-attendance-status]")).to_contain_text("Trip active")

    def parent_page(self):
        self.db(TripLocation.objects.create, trip=self.trip, latitude=40.4199, longitude=-3.6895,
            accuracy_m=5, observed_at=timezone.now(), client_sample_id=uuid4(), source="simulated_iot")
        self.login("parent")
        self.page.goto(self.live_server_url + f"/parents/live/?child={self.child.pk}&trip={self.trip.pk}")
        self.expect(self.page.locator("[data-bus-map]")).to_be_visible()
        self.expect(self.page.locator("[data-estimated]")).not_to_have_text("Not available")
        self.expect(self.page.locator("[data-notice-status]")).to_have_text("No absence has been reported.")

    def refresh_parent(self):
        self.page.get_by_role("button", name="Refresh update").click()

    def test_parent_network_failure_clears_previously_displayed_eta_and_map(self):
        self.parent_page()
        self.context.route("**/eta/", lambda route: route.abort("failed"))
        self.refresh_parent()
        self.expect(self.page.locator("[data-journey-status]")).to_contain_text("Update unavailable")
        self.expect(self.page.locator("[data-estimated]")).to_have_text("Not available")
        self.expect(self.page.locator("[data-bus-map]")).to_be_hidden()
        self.expect(self.page.locator("[data-absent]")).to_be_disabled()

    def test_removed_parent_link_clears_data_on_next_browser_refresh(self):
        self.parent_page()
        self.db(lambda: ParentChildAccess.objects.filter(user=self.parent, student=self.child).delete())
        with self.page.expect_response(lambda response: response.url.endswith("/eta/")) as denied:
            self.refresh_parent()
        self.assertEqual(denied.value.status, 404)
        # Tracking's scoped 404 is HTML, so the frontend's JSON parser reports
        # a generic error. Assert revoked access/data removal, not exact copy.
        self.expect(self.page.locator("[data-journey-status]")).to_contain_text("Update unavailable")
        self.expect(self.page.locator("[data-estimated]")).to_have_text("Not available")
        self.expect(self.page.locator("[data-bus-map]")).to_be_hidden()

    def test_stale_location_is_labelled_without_requesting_a_new_traffic_estimate(self):
        self.parent_page()
        self.db(lambda: TripLocation.objects.filter(trip=self.trip).update(observed_at=timezone.now() - timedelta(minutes=2)))
        calls_before = self.provider.call_count
        self.refresh_parent()
        self.expect(self.page.locator("[data-journey-status]")).to_contain_text("out of date")
        self.expect(self.page.locator("[data-map-status]")).to_have_text("Out-of-date position shown.")
        self.expect(self.page.locator("[data-estimated]")).not_to_have_text("Not available")
        self.assertEqual(self.provider.call_count, calls_before)

    def test_denied_browser_gps_permission_does_not_post_a_location(self):
        self.monitor_page()
        session = self.context.new_cdp_session(self.page)
        context_id = session.send("Target.getTargetInfo")["targetInfo"]["browserContextId"]
        session.send("Browser.setPermission", {"permission": {"name": "geolocation"},
            "setting": "denied", "origin": self.live_server_url, "browserContextId": context_id})
        self.page.get_by_role("button", name="Share location", exact=True).click()
        self.expect(self.page.locator("[data-share-status]")).to_contain_text("Location permission denied")
        self.expect(self.page.locator("[data-share-start]")).to_be_visible()
        self.expect(self.page.locator("[data-share-stop]")).to_be_hidden()
        self.assertFalse(self.db(TripLocation.objects.exists))

    def test_state_connection_failure_stops_sharing_before_any_gps_post(self):
        self.monitor_page()
        self.context.route("**/state/", lambda route: route.abort("failed"))
        self.page.get_by_role("button", name="Share location", exact=True).click()
        self.expect(self.page.locator("[data-share-status]")).to_contain_text("Connection lost")
        self.expect(self.page.locator("[data-share-start]")).to_be_visible()
        self.assertFalse(self.db(TripLocation.objects.exists))

    def test_lost_success_response_retries_same_uuid_without_duplicate_database_row(self):
        self.monitor_page()
        payloads, statuses = [], []

        def lose_first_response(route):
            payloads.append(route.request.post_data_json)
            response = route.fetch()  # Real server receives and persists the POST.
            statuses.append(response.status)
            if len(payloads) == 1:
                route.abort("failed")  # Simulate loss AFTER successful persistence.
            else:
                route.fulfill(response=response)

        self.context.route("**/locations/", lose_first_response)
        self.page.get_by_role("button", name="Share location", exact=True).click()
        self.expect(self.page.locator("[data-share-status]")).to_contain_text("Retrying the same sample", timeout=15000)
        self.assertEqual(self.db(TripLocation.objects.count), 1)
        self.expect(self.page.locator("[data-share-status]")).to_contain_text("Sharing location", timeout=15000)
        self.page.get_by_role("button", name="Stop sharing", exact=True).click()
        self.assertEqual(statuses, [201, 200])
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(self.db(TripLocation.objects.count), 1)

    def test_attendance_controls_lock_when_trip_completed_in_another_session(self):
        self.monitor_page()
        self.db(lambda: Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.COMPLETED))
        row = self.page.locator(f'[data-attendance-row][data-student-id="{self.child.pk}"]')
        row.locator("select").select_option("present")
        row.get_by_role("button", name="Save observation").click()
        self.expect(self.page.locator("[data-attendance-status]")).to_contain_text("read-only")
        self.expect(row.locator("select")).to_be_disabled()
        self.expect(row.get_by_role("button", name="Save observation")).to_be_disabled()
        self.assertFalse(self.db(StudentAttendance.objects.exists))
