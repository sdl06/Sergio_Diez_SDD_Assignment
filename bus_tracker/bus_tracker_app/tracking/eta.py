import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from ..models import Trip
from .models import TripStopEta


class EtaProviderError(Exception):
    """Raised when a traffic-aware ETA cannot be obtained safely."""


@dataclass(frozen=True)
class ProviderRoute:
    travel_time_seconds: int
    traffic_delay_seconds: int
    route_distance_m: int


@dataclass(frozen=True)
class EtaResult:
    estimate: TripStopEta | None
    state: str
    refreshed: bool


def distance_between_metres(latitude_1, longitude_1, latitude_2, longitude_2):
    """Return great-circle distance between two WGS84 points."""

    earth_radius_m = 6_371_000
    latitude_1_rad = math.radians(latitude_1)
    latitude_2_rad = math.radians(latitude_2)
    latitude_delta = math.radians(latitude_2 - latitude_1)
    longitude_delta = math.radians(longitude_2 - longitude_1)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1_rad)
        * math.cos(latitude_2_rad)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * earth_radius_m * math.asin(math.sqrt(haversine))


class TomTomRoutingProvider:
    """Small adapter for TomTom Orbis Routing API v3."""

    def __init__(self, api_key=None, endpoint=None, timeout=None):
        self.api_key = settings.TOMTOM_API_KEY if api_key is None else api_key
        self.endpoint = settings.TOMTOM_ROUTING_URL if endpoint is None else endpoint
        self.timeout = settings.TOMTOM_TIMEOUT_SECONDS if timeout is None else timeout

    def estimate_route(self, *, origin, destination):
        if not self.api_key:
            raise EtaProviderError("TomTom API key is not configured.")

        body = json.dumps(
            {
                "routePlanningLocations": {
                    "origin": {
                        "type": "Point",
                        "coordinates": [origin[1], origin[0]],
                    },
                    "destination": {
                        "type": "Point",
                        "coordinates": [destination[1], destination[0]],
                    },
                },
                "travelMode": "bus",
                "routeType": "fastest",
                "traffic": "live",
                "departureDateTime": "now",
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Attributes": "routes.summary",
                "Content-Type": "application/json",
                "TomTom-Api-Key": self.api_key,
                "TomTom-Api-Version": "3",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise EtaProviderError("TomTom routing request failed.") from error

        try:
            summary = payload["routes"][0]["summary"]
            travel_time_seconds = int(summary["travelDurationInSeconds"])
            traffic_delay_seconds = int(summary.get("trafficDelayDurationInSeconds", 0))
            route_distance_m = int(summary["lengthInMeters"])
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise EtaProviderError("TomTom returned an unexpected routing response.") from error

        if travel_time_seconds < 0 or traffic_delay_seconds < 0 or route_distance_m < 0:
            raise EtaProviderError("TomTom returned invalid negative route values.")

        return ProviderRoute(
            travel_time_seconds=travel_time_seconds,
            traffic_delay_seconds=traffic_delay_seconds,
            route_distance_m=route_distance_m,
        )


def get_or_refresh_eta(*, trip, stop, location, provider=None, now=None):
    """Reuse a recent ETA or refresh it through the configured routing provider."""

    now = timezone.now() if now is None else now
    previous = TripStopEta.objects.filter(trip=trip, stop=stop).first()
    should_refresh = previous is None

    if previous is not None:
        estimate_age = now - previous.calculated_at
        distance_moved = distance_between_metres(
            previous.origin_latitude,
            previous.origin_longitude,
            location.latitude,
            location.longitude,
        )
        minimum_age = timedelta(seconds=float(settings.ETA_MIN_REFRESH_SECONDS))
        maximum_age = timedelta(seconds=float(settings.ETA_MAX_REFRESH_SECONDS))
        movement_threshold = max(
            float(settings.ETA_MIN_MOVEMENT_METRES),
            float(previous.origin_accuracy_m + location.accuracy_m),
        )
        should_refresh = estimate_age >= maximum_age or (
            estimate_age >= minimum_age and distance_moved >= movement_threshold
        )

    if not should_refresh:
        return EtaResult(estimate=previous, state="cached", refreshed=False)

    provider = TomTomRoutingProvider() if provider is None else provider
    try:
        route = provider.estimate_route(
            origin=(location.latitude, location.longitude),
            destination=(stop.latitude, stop.longitude),
        )
    except EtaProviderError:
        if previous is not None:
            return EtaResult(estimate=previous, state="stale_eta", refreshed=False)
        return EtaResult(estimate=None, state="eta_unavailable", refreshed=False)

    estimate, _ = TripStopEta.objects.update_or_create(
        trip=trip,
        stop=stop,
        defaults={
            "origin_latitude": location.latitude,
            "origin_longitude": location.longitude,
            "origin_accuracy_m": location.accuracy_m,
            "estimated_arrival": now + timedelta(seconds=route.travel_time_seconds),
            "calculated_at": now,
            "travel_time_seconds": route.travel_time_seconds,
            "traffic_delay_seconds": route.traffic_delay_seconds,
            "route_distance_m": route.route_distance_m,
            "provider": "tomtom",
        },
    )
    return EtaResult(estimate=estimate, state="fresh_eta", refreshed=True)


def scheduled_arrival_for(trip, stop):
    """Combine the trip date and leg-specific stop time in the school timezone."""

    scheduled_time = (
        stop.configured_leg1_arrival
        if trip.leg == Trip.Leg.TO_SCHOOL
        else stop.configured_leg2_arrival
    )
    try:
        school_timezone = ZoneInfo(settings.SCHOOL_TIME_ZONE)
    except ZoneInfoNotFoundError as error:
        raise EtaProviderError("The configured school timezone is invalid.") from error
    return datetime.combine(trip.date, scheduled_time, tzinfo=school_timezone)
