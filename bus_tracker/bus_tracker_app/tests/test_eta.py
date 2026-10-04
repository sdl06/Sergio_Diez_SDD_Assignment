"""Mocked contract checks and opt-in integration with actual TomTom.

RUN_LIVE_TOMTOM_TESTS=1 enables eight methods making nine remote requests.
The HTTP integration tests spy on real transport; no replies are mocked.
Run both live classes with:
python manage.py test bus_tracker_app.tests.test_eta.LiveTomTomTests \
    bus_tracker_app.tests.test_eta.LiveEtaIntegrationTests
Traffic changes, so assertions check invariants rather than exact journey times.
"""
import io
import json
import os
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import Mock, patch
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from bus_tracker_app.models import Trip
from bus_tracker_app.tracking.eta import (
    EtaProviderError, ProviderRoute, TomTomRoutingProvider,
    distance_between_metres, get_or_refresh_eta, scheduled_arrival_for,
)
from bus_tracker_app.tracking.models import TripLocation, TripStopEta
from bus_tracker_app.tracking.views import validate_location_json
from .helpers import DomainCase


class ProviderContractTests(SimpleTestCase):
    def test_real_adapter_request_and_response_contract(self):
        body = {"routes": [{"summary": {"travelDurationInSeconds": 120,
            "trafficDelayDurationInSeconds": 30, "lengthInMeters": 900}}]}
        with patch("bus_tracker_app.tracking.eta.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as transport:
            result = TomTomRoutingProvider(api_key="test-only", timeout=7).estimate_route(
                origin=(40.4199, -3.6895), destination=(40.4181, -3.6938))
        self.assertEqual(result, ProviderRoute(120, 30, 900))
        request = transport.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(payload["routePlanningLocations"]["origin"]["coordinates"], [-3.6895, 40.4199])
        self.assertEqual(payload["traffic"], "live")
        self.assertEqual(payload["routeType"], "fast")
        self.assertEqual(request.get_header("Tomtom-api-key"), "test-only")
        self.assertEqual(transport.call_args.kwargs["timeout"], 7)

    def test_missing_key_transport_and_schema_failures(self):
        with self.assertRaises(EtaProviderError):
            TomTomRoutingProvider(api_key="").estimate_route(origin=(0, 0), destination=(1, 1))
        for error in [URLError("offline"), TimeoutError(), OSError(), HTTPError("test", 429, "limited", {}, None)]:
            with self.subTest(error=type(error).__name__), patch("bus_tracker_app.tracking.eta.urlopen", side_effect=error):
                with self.assertRaises(EtaProviderError):
                    TomTomRoutingProvider(api_key="test").estimate_route(origin=(0, 0), destination=(1, 1))
        for body in [b"invalid", b"\xff", b"null", b'{"routes":[]}', b'{"routes":[{}]}',
            json.dumps({"routes": [{"summary": {"travelDurationInSeconds": True, "lengthInMeters": 1}}]}).encode(),
            json.dumps({"routes": [{"summary": {"travelDurationInSeconds": -1, "lengthInMeters": 1}}]}).encode()]:
            with self.subTest(body=body), patch("bus_tracker_app.tracking.eta.urlopen", return_value=io.BytesIO(body)):
                with self.assertRaises(EtaProviderError):
                    TomTomRoutingProvider(api_key="test").estimate_route(origin=(0, 0), destination=(1, 1))

    def test_distance(self):
        self.assertEqual(distance_between_metres(40, -3, 40, -3), 0)
        distance = distance_between_metres(40, -3, 40.001, -3)
        self.assertAlmostEqual(distance, 111.195, places=2)
        self.assertAlmostEqual(distance, distance_between_metres(40.001, -3, 40, -3))


@skipUnless(os.environ.get("RUN_LIVE_TOMTOM_TESTS") == "1", "Live TomTom check is opt-in; consumes provider quota")
@override_settings(TOMTOM_TIMEOUT_SECONDS=15)
class LiveTomTomTests(SimpleTestCase):
    castro_station = (43.37031, -3.21717)
    laredo_station = (43.40969, -3.41318)
    laredo_hospital = (43.4137803, -3.4407597)

    def setUp(self):
        self.assertTrue(bool(settings.TOMTOM_API_KEY), "Set TOMTOM_API_KEY in .env before opting into live tests")

    def assert_route_summary(self, route, minimum_distance):
        for value in (route.travel_time_seconds, route.route_distance_m, route.traffic_delay_seconds):
            self.assertIs(type(value), int)
        self.assertGreater(route.travel_time_seconds, 0)
        self.assertGreater(route.route_distance_m, minimum_distance)
        self.assertGreaterEqual(route.traffic_delay_seconds, 0)
        self.assertLessEqual(route.traffic_delay_seconds, route.travel_time_seconds)

    def test_madrid_route_using_actual_tomtom(self):
        route = TomTomRoutingProvider().estimate_route(
            origin=(40.4199, -3.6895), destination=(40.4154, -3.6934))
        self.assert_route_summary(route, 100)

    def test_castro_to_laredo_using_actual_tomtom(self):
        route = TomTomRoutingProvider().estimate_route(origin=self.castro_station, destination=self.laredo_station)
        self.assert_route_summary(route, 15000)

    def test_laredo_to_castro_using_actual_tomtom(self):
        route = TomTomRoutingProvider().estimate_route(origin=self.laredo_station, destination=self.castro_station)
        self.assert_route_summary(route, 15000)

    def test_laredo_hospital_to_station_using_actual_tomtom(self):
        route = TomTomRoutingProvider().estimate_route(origin=self.laredo_hospital, destination=self.laredo_station)
        self.assert_route_summary(route, 1000)

    def test_invalid_key_is_rejected_by_actual_tomtom(self):
        with self.assertRaises(EtaProviderError) as caught:
            TomTomRoutingProvider(api_key="invalid-integration-test-key").estimate_route(
                origin=self.castro_station, destination=self.laredo_station)
        self.assertIsInstance(caught.exception.__cause__, HTTPError)
        self.assertIn(caught.exception.__cause__.code, (401, 403))

    def test_invalid_coordinates_are_rejected_by_actual_tomtom(self):
        # Exercise the external request contract directly; normal GPS validation
        # would reject this latitude before it reached the provider.
        with self.assertRaises(EtaProviderError) as caught:
            TomTomRoutingProvider().estimate_route(origin=(91, -3.21717), destination=self.laredo_station)
        self.assertIsInstance(caught.exception.__cause__, HTTPError)
        self.assertEqual(caught.exception.__cause__.code, 400)


@skipUnless(os.environ.get("RUN_LIVE_TOMTOM_TESTS") == "1", "Live TomTom check is opt-in; consumes provider quota")
@override_settings(TOMTOM_TIMEOUT_SECONDS=15, ETA_MIN_REFRESH_SECONDS=30, ETA_MAX_REFRESH_SECONDS=60)
class LiveEtaIntegrationTests(DomainCase):
    def setUp(self):
        self.assertTrue(bool(settings.TOMTOM_API_KEY), "Set TOMTOM_API_KEY in .env before opting into live tests")
        self.trip.status = Trip.Status.ACTIVE
        self.trip.save(update_fields=["status"])
        self.stop.latitude, self.stop.longitude = 43.37031, -3.21717
        self.stop.save(update_fields=["latitude", "longitude"])
        payload = {**self.fix(), "latitude": 43.3714364, "longitude": -3.2049118}
        TripLocation.objects.create(trip=self.trip, source="integration_test",
            **validate_location_json(json.dumps(payload).encode()))
        self.login(self.parent)
        self.url = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/eta/"

    def test_real_eta_is_persisted_and_shared_stop_cache_avoids_more_calls(self):
        with patch("bus_tracker_app.tracking.eta.urlopen", wraps=urlopen) as transport:
            first = self.client.get(self.url)
            self.assertEqual(first.status_code, 200)
            data = first.json()
            self.assertEqual(data["eta_state"], "fresh_eta")
            self.assertTrue(data["estimate_refreshed"])
            estimate = TripStopEta.objects.get(trip=self.trip, stop=self.stop)
            self.assertGreater(estimate.travel_time_seconds, 0)
            self.assertEqual(data["estimated_arrival"], estimate.estimated_arrival.isoformat())
            self.assertEqual(estimate.provider, "tomtom")
            self.assertIn("no-store", first.headers["Cache-Control"])
            self.assertFalse(settings.TOMTOM_API_KEY in first.content.decode(), "The response must not expose the API key")
            for child in (self.child, self.sibling):
                cached = self.client.get(f"/api/children/{child.pk}/trips/{self.trip.pk}/eta/").json()
                self.assertEqual(cached["eta_state"], "cached")
                self.assertFalse(cached["estimate_refreshed"])
                self.assertEqual(cached["estimated_arrival"], data["estimated_arrival"])
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(TripStopEta.objects.count(), 1)

    def test_actual_provider_rejection_preserves_previous_real_estimate(self):
        self.assertEqual(self.client.get(self.url).json()["eta_state"], "fresh_eta")
        estimate = TripStopEta.objects.get(trip=self.trip, stop=self.stop)
        old_calculated = timezone.now() - timedelta(seconds=61)
        TripStopEta.objects.filter(pk=estimate.pk).update(calculated_at=old_calculated)
        with override_settings(TOMTOM_API_KEY="invalid-integration-test-key"), patch(
            "bus_tracker_app.tracking.eta.urlopen", wraps=urlopen) as transport:
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["eta_state"], "stale_eta")
            self.assertFalse(response.json()["estimate_refreshed"])
            self.assertEqual(transport.call_count, 1)
        estimate.refresh_from_db()
        self.assertEqual(estimate.calculated_at, old_calculated)
        self.assertEqual(response.json()["estimated_arrival"], estimate.estimated_arrival.isoformat())
        self.assertEqual(TripStopEta.objects.count(), 1)


@override_settings(ETA_MIN_REFRESH_SECONDS=30, ETA_MAX_REFRESH_SECONDS=60, ETA_MIN_MOVEMENT_METRES=150)
class EtaTests(DomainCase):
    def setUp(self):
        self.now = timezone.now()
        self.location = TripLocation.objects.create(trip=self.trip,
            **validate_location_json(json.dumps(self.fix()).encode()), source="test")
        self.provider = Mock()
        self.provider.estimate_route.return_value = ProviderRoute(120, 20, 700)

    def estimate(self, now=None):
        return get_or_refresh_eta(trip=self.trip, stop=self.stop, location=self.location,
            provider=self.provider, now=now or self.now)

    def test_first_cache_movement_and_max_age_boundaries(self):
        first = self.estimate()
        self.assertTrue(first.refreshed)
        self.assertEqual(first.estimate.estimated_arrival, self.now + timedelta(seconds=120))
        self.location.latitude += .003
        self.assertEqual(self.estimate(self.now + timedelta(seconds=29)).state, "cached")
        self.assertEqual(self.provider.estimate_route.call_count, 1)
        self.assertTrue(self.estimate(self.now + timedelta(seconds=30)).refreshed)
        self.assertEqual(self.estimate(self.now + timedelta(seconds=89)).state, "cached")
        self.assertTrue(self.estimate(self.now + timedelta(seconds=90)).refreshed)
        self.assertEqual(TripStopEta.objects.count(), 1)

    def test_poor_gps_accuracy_suppresses_movement_refresh(self):
        self.location.accuracy_m = 200
        self.estimate()
        self.location.latitude += .002
        self.assertEqual(self.estimate(self.now + timedelta(seconds=30)).state, "cached")
        self.assertTrue(self.estimate(self.now + timedelta(seconds=60)).refreshed)

    def test_provider_outage_preserves_old_estimate_without_fake_refresh(self):
        self.provider.estimate_route.side_effect = EtaProviderError("offline")
        self.assertEqual(self.estimate().state, "eta_unavailable")
        self.assertFalse(TripStopEta.objects.exists())
        self.provider.estimate_route.side_effect = None
        first = self.estimate().estimate
        self.provider.estimate_route.side_effect = EtaProviderError("offline")
        result = self.estimate(self.now + timedelta(seconds=60))
        self.assertEqual(result.state, "stale_eta")
        self.assertFalse(result.refreshed)
        first.refresh_from_db()
        self.assertEqual(first.calculated_at, self.now)

    def test_schedule_both_legs_and_bad_timezone(self):
        self.assertEqual(scheduled_arrival_for(self.trip, self.stop).hour, 8)
        self.trip.leg = 2
        self.assertEqual(scheduled_arrival_for(self.trip, self.stop).hour, 17)
        with override_settings(SCHOOL_TIME_ZONE="Not/AZone"), self.assertRaises(EtaProviderError):
            scheduled_arrival_for(self.trip, self.stop)

    def test_eta_http_states_privacy_and_no_provider_for_stale_location(self):
        self.login(self.parent)
        url = f"/api/children/{self.child.pk}/trips/{self.trip.pk}/eta/"
        with patch("bus_tracker_app.tracking.eta.TomTomRoutingProvider.estimate_route", return_value=ProviderRoute(100, 10, 500)) as provider:
            self.assertEqual(self.client.get(url).json()["eta_state"], "prepared")
            self.trip.status = "active"
            self.trip.save()
            self.assertEqual(self.client.get(url).json()["eta_state"], "fresh_eta")
            self.assertEqual(self.client.get(url).json()["eta_state"], "cached")
            self.assertEqual(provider.call_count, 1)
            TripLocation.objects.update(observed_at=self.now - timedelta(minutes=2))
            self.assertEqual(self.client.get(url).json()["eta_state"], "stale_location")
            self.assertEqual(provider.call_count, 1)
            with override_settings(SCHOOL_TIME_ZONE="Invalid/Zone"):
                response = self.client.get(url)
                self.assertEqual(response.json()["eta_state"], "eta_unavailable")
                self.assertIsNone(response.json()["estimated_arrival"])
            TripLocation.objects.all().delete()
            self.assertEqual(self.client.get(url).json()["eta_state"], "no_location")
            self.trip.status = "completed"
            self.trip.save()
            self.assertEqual(self.client.get(url).json()["eta_state"], "completed")
        self.login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
