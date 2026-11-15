import json
import math
import re
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from ..models import Trip
from .eta import EtaProviderError, EtaResult, get_or_refresh_eta, scheduled_arrival_for
from .models import TripLocation, TripStopEta
from .access import visible_children


MAX_LOCATION_BODY_BYTES = 4_096
MAX_ACCURACY_METRES = 1_000
FUTURE_FIX_TOLERANCE = timedelta(minutes=5)


class LocationPayloadError(ValueError):
    """Raised when a monitor submits a malformed or unsafe location fix."""


class LocationRateLimitError(Exception):
    """Raised when a trip is receiving new samples too quickly."""


class LocationTripStateError(Exception):
    """The trip stopped accepting fixes before persistence."""


def _finite_number(payload, field, minimum, maximum):
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocationPayloadError(f"{field} must be a number.")
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise LocationPayloadError(f"{field} must be between {minimum} and {maximum}.")
    return value


def _validate_calendar_date(timestamp):
    """Check an ISO date prefix; Django still validates the complete timestamp."""
    match = re.match(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?=[T ])", timestamp)
    if match is None:
        return  # Let parse_datetime handle malformed or alternative date formats.
    year, month, day = map(int, match.groups())
    if year == 0 or not 1 <= month <= 12:
        raise LocationPayloadError("observed_at contains an invalid calendar date.")
    # Gregorian rule: century years are leap years only when divisible by 400.
    leap_year = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_per_month = (31, 29 if leap_year else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if not 1 <= day <= days_per_month[month - 1]:
        raise LocationPayloadError("observed_at contains an invalid calendar date.")


def validate_location_json(raw_body):
    """Parse and validate the untrusted JSON body sent by a monitor's phone."""

    if len(raw_body) > MAX_LOCATION_BODY_BYTES:
        raise LocationPayloadError("The location payload is too large.")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LocationPayloadError("The request body must contain valid JSON.") from error

    if not isinstance(payload, dict):
        raise LocationPayloadError("The JSON payload must be an object.")

    required_fields = {"latitude", "longitude", "accuracy_m", "observed_at", "client_sample_id"}
    missing_fields = required_fields - payload.keys()
    if missing_fields:
        raise LocationPayloadError(f"Missing fields: {', '.join(sorted(missing_fields))}.")

    unexpected_fields = payload.keys() - required_fields
    if unexpected_fields:
        raise LocationPayloadError(f"Unexpected fields: {', '.join(sorted(unexpected_fields))}.")

    latitude = _finite_number(payload, "latitude", -90, 90)
    longitude = _finite_number(payload, "longitude", -180, 180)

    accuracy_m = payload["accuracy_m"]
    if isinstance(accuracy_m, bool) or not isinstance(accuracy_m, int):
        raise LocationPayloadError("accuracy_m must be an integer.")
    if not 1 <= accuracy_m <= MAX_ACCURACY_METRES:
        raise LocationPayloadError(f"accuracy_m must be between 1 and {MAX_ACCURACY_METRES}.")

    if not isinstance(payload["observed_at"], str):
        raise LocationPayloadError("observed_at must be an ISO-8601 timestamp.")
    _validate_calendar_date(payload["observed_at"])
    try:
        observed_at = parse_datetime(payload["observed_at"])
    except ValueError as error:
        # Includes invalid time components and date formats not checked above.
        raise LocationPayloadError("observed_at must be a valid ISO-8601 timestamp.") from error
    if observed_at is None or not timezone.is_aware(observed_at):
        raise LocationPayloadError("observed_at must be a timezone-aware ISO-8601 timestamp.")
    if observed_at > timezone.now() + FUTURE_FIX_TOLERANCE:
        raise LocationPayloadError("observed_at is too far in the future.")

    try:
        client_sample_id = UUID(str(payload["client_sample_id"]))
    except (TypeError, ValueError, AttributeError) as error:
        raise LocationPayloadError("client_sample_id must be a valid UUID.") from error

    return {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy_m": accuracy_m,
        "observed_at": observed_at,
        "client_sample_id": client_sample_id,
    }


@transaction.atomic
def save_sample_once(trip, payload, *, user):
    """Persist a fix once and identify harmless retries by client sample ID."""

    # Serialize with lifecycle transitions and recheck current assignment/state.
    # SQLite also acquires a write lock for this conditional no-op update.
    matched = Trip.objects.filter(
        pk=trip.pk, status=Trip.Status.ACTIVE, monitor__user=user,
    ).update(status=F("status"))
    if not matched:
        current = get_object_or_404(Trip.objects.select_related("monitor"), pk=trip.pk)
        if current.monitor.user_id != user.pk:
            raise PermissionDenied("You are not the monitor assigned to this trip.")
        raise LocationTripStateError

    existing = TripLocation.objects.filter(
        trip=trip,
        client_sample_id=payload["client_sample_id"],
    ).first()
    if existing is not None:
        return existing, False

    minimum_interval = float(getattr(settings, "LOCATION_MIN_SAMPLE_INTERVAL_SECONDS", 2))
    if minimum_interval > 0:
        cutoff = timezone.now() - timedelta(seconds=minimum_interval)
        if TripLocation.objects.filter(trip=trip, received_at__gte=cutoff).exists():
            raise LocationRateLimitError

    try:
        with transaction.atomic():
            sample = TripLocation.objects.create(
                trip=trip,
                source="monitor_phone",
                **payload,
            )
    except IntegrityError:
        # A concurrent retry can win the unique constraint between the initial
        # lookup and insert. Treat it as the same successful observation.
        sample = TripLocation.objects.get(
            trip=trip,
            client_sample_id=payload["client_sample_id"],
        )
        return sample, False

    return sample, True


def build_safe_location_state(trip, sample):
    """Serialize only the current state and latest coordinates a parent needs."""

    if trip.status == Trip.Status.COMPLETED:
        state = "completed"
    elif sample is None:
        state = "no_fix"
    else:
        stale_after = timedelta(seconds=float(getattr(settings, "LOCATION_STALE_AFTER_SECONDS", 45)))
        state = "stale" if timezone.now() - sample.observed_at > stale_after else "fresh"

    response = {"trip_id": trip.pk, "state": state}
    if sample is not None:
        response.update(
            {
                "latitude": sample.latitude,
                "longitude": sample.longitude,
                "accuracy_m": sample.accuracy_m,
                "observed_at": sample.observed_at.isoformat(),
                "received_at": sample.received_at.isoformat(),
            }
        )
    return response


@login_required
@permission_required("bus_tracker_app.post_trip_location", raise_exception=True)
@require_POST
def post_trip_location(request, trip_id):
    trip = get_object_or_404(Trip.objects.select_related("monitor__user"), pk=trip_id)

    if trip.monitor.user_id != request.user.id:
        raise PermissionDenied("You are not the monitor assigned to this trip.")
    if trip.status != Trip.Status.ACTIVE:
        return JsonResponse({"error": "trip_not_active"}, status=409)
    if request.content_type != "application/json":
        return JsonResponse({"error": "content_type_must_be_json"}, status=415)

    try:
        payload = validate_location_json(request.body)
        sample, created = save_sample_once(trip, payload, user=request.user)
    except LocationPayloadError as error:
        return JsonResponse({"error": "invalid_location", "detail": str(error)}, status=400)
    except LocationRateLimitError:
        return JsonResponse(
            {"error": "location_updates_too_frequent"},
            status=429,
            headers={"Retry-After": "2"},
        )
    except LocationTripStateError:
        return JsonResponse({"error": "trip_not_active"}, status=409)

    return JsonResponse(
        {"accepted": True, "sample_id": sample.pk, "duplicate": not created},
        status=201 if created else 200,
    )


@login_required
@require_GET
def latest_child_trip_location(request, child_id, trip_id):
    child = get_object_or_404(
        visible_children(request.user),
        pk=child_id,
    )
    trip = get_object_or_404(Trip, pk=trip_id, students=child)
    sample = trip.location_samples.order_by("-observed_at", "-received_at").first()

    return JsonResponse(
        build_safe_location_state(trip, sample),
        headers={"Cache-Control": "no-store"},
    )


def build_parent_eta_state(*, child, trip, sample, eta_result):
    """Combine safe location data with the stop-specific cached ETA."""

    response = build_safe_location_state(trip, sample)
    response.update(
        {
            "student_id": child.pk,
            "stop_id": child.assigned_stop_id,
            "stop_name": child.assigned_stop.descriptor,
            "eta_state": eta_result.state,
            "estimate_refreshed": eta_result.refreshed,
            "estimated_arrival": None,
            "scheduled_arrival": None,
            "delay_seconds": None,
            "eta_calculated_at": None,
            "travel_time_seconds": None,
            "traffic_delay_seconds": None,
        }
    )

    estimate = eta_result.estimate
    scheduled_arrival = scheduled_arrival_for(trip, child.assigned_stop)
    response["scheduled_arrival"] = scheduled_arrival.isoformat()
    if estimate is None:
        return response

    response.update(
        {
            "estimated_arrival": estimate.estimated_arrival.isoformat(),
            "scheduled_arrival": scheduled_arrival.isoformat(),
            "delay_seconds": int((estimate.estimated_arrival - scheduled_arrival).total_seconds()),
            "eta_calculated_at": estimate.calculated_at.isoformat(),
            "travel_time_seconds": estimate.travel_time_seconds,
            "traffic_delay_seconds": estimate.traffic_delay_seconds,
        }
    )
    return response


@login_required
@require_GET
def latest_child_trip_eta(request, child_id, trip_id):
    """Return live location plus a cached traffic-aware ETA for a child's stop."""

    child = get_object_or_404(
        visible_children(request.user),
        pk=child_id,
    )
    trip = get_object_or_404(Trip, pk=trip_id, students=child)
    sample = trip.location_samples.order_by("-observed_at", "-received_at").first()

    if trip.status != Trip.Status.ACTIVE:
        eta_result = EtaResult(estimate=None, state=trip.status, refreshed=False)
    elif sample is None:
        eta_result = EtaResult(estimate=None, state="no_location", refreshed=False)
    else:
        stale_after = timedelta(seconds=float(getattr(settings, "LOCATION_STALE_AFTER_SECONDS", 45)))
        if timezone.now() - sample.observed_at > stale_after:
            eta_result = EtaResult(
                estimate=TripStopEta.objects.filter(
                    trip=trip,
                    stop=child.assigned_stop,
                ).first(),
                state="stale_location",
                refreshed=False,
            )
        else:
            eta_result = get_or_refresh_eta(
                trip=trip,
                stop=child.assigned_stop,
                location=sample,
            )

    try:
        payload = build_parent_eta_state(
            child=child,
            trip=trip,
            sample=sample,
            eta_result=eta_result,
        )
    except EtaProviderError:
        payload = build_safe_location_state(trip, sample)
        payload.update(
            {
                "student_id": child.pk,
                "stop_id": child.assigned_stop_id,
                "stop_name": child.assigned_stop.descriptor,
                "eta_state": "eta_unavailable",
                "estimate_refreshed": False,
                "estimated_arrival": None,
                "scheduled_arrival": None,
                "delay_seconds": None,
                "eta_calculated_at": None,
                "travel_time_seconds": None,
                "traffic_delay_seconds": None,
            }
        )

    return JsonResponse(payload, headers={"Cache-Control": "no-store"})
