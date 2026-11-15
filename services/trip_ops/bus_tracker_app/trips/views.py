from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..auth import login_required
from ..models import Trip
from .services import TripStateError, operational_trips, transition_trip


def trip_data(trip):
    return {
        "id": trip.pk,
        "route_id": trip.route_id,
        "bus_id": trip.bus_id,
        "monitor_id": trip.monitor_id,
        "date": trip.date,
        "leg": trip.leg,
        "status": trip.status,
        "started_at": trip.started_at,
        "completed_at": trip.completed_at,
    }


def can_share_location(user, trip):
    return user.has_perm("bus_tracker_app.post_trip_location") and trip.monitor.user_id == user.pk


@never_cache
@login_required
@require_GET
def trip_list(request):
    trips = operational_trips(request.user).order_by("-date", "leg", "pk")
    return JsonResponse({"trips": [trip_data(trip) for trip in trips]})


@never_cache
@login_required
@require_GET
def trip_detail(request, trip_id):
    trip = get_object_or_404(operational_trips(request.user), pk=trip_id)
    students = trip.students.values("id", "name", "assigned_stop_id").order_by("name", "pk")
    return JsonResponse({
        **trip_data(trip),
        "students": list(students),
        "can_share": can_share_location(request.user, trip),
    })


@never_cache
@login_required
@require_GET
def trip_state(request, trip_id):
    trip = get_object_or_404(operational_trips(request.user), pk=trip_id)
    return JsonResponse({"status": trip.status, "can_share": can_share_location(request.user, trip)})


def _transition(request, trip_id, target):
    try:
        trip, changed = transition_trip(user=request.user, trip_id=trip_id, target=target)
    except TripStateError as error:
        return JsonResponse({"error": str(error)}, status=409)
    return JsonResponse({"trip": trip_data(trip), "changed": changed})


@login_required
@require_POST
def start_trip(request, trip_id):
    return _transition(request, trip_id, Trip.Status.ACTIVE)


@login_required
@require_POST
def complete_trip(request, trip_id):
    return _transition(request, trip_id, Trip.Status.COMPLETED)
