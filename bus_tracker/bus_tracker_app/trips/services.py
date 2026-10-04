"""Permission-scoped trip access and atomic lifecycle transitions."""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Trip


class TripStateError(ValueError):
    pass


def operational_trips(user, *, transition=False):
    admin = user.has_perm("bus_tracker_app.manage_operational_data")
    permissions = ["prepare_trip"] if transition else [
        "prepare_trip", "post_trip_location", "record_trip_attendance",
    ]
    if not user.is_authenticated or not (admin or any(
        user.has_perm(f"bus_tracker_app.{permission}") for permission in permissions
    )):
        raise PermissionDenied("You cannot operate trips.")
    trips = Trip.objects.select_related("route", "bus", "monitor")
    return trips if admin else trips.filter(monitor__user=user)


@transaction.atomic
def transition_trip(*, user, trip_id, target):
    if target not in {Trip.Status.ACTIVE, Trip.Status.COMPLETED}:
        raise ValueError("Unknown trip transition.")
    trips = operational_trips(user, transition=True)
    expected = Trip.Status.PREPARED if target == Trip.Status.ACTIVE else Trip.Status.ACTIVE
    timestamp = "started_at" if target == Trip.Status.ACTIVE else "completed_at"
    changed = trips.filter(pk=trip_id, status=expected).update(
        status=target, **{timestamp: timezone.now()},
    )
    trip = get_object_or_404(trips, pk=trip_id)
    if not changed and trip.status != target:
        raise TripStateError(f"Cannot change a {trip.status} trip to {target}.")
    return trip, bool(changed)
