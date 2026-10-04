from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..models import Trip
from .services import TripStateError, operational_trips, transition_trip


def _workspace(request, trip, *, error=None, status=200):
    return render(request, "bus_tracker_app/trips/detail.html", {
        "trip": trip,
        "children": trip.students.select_related("assigned_stop").order_by("name", "pk"),
        "can_transition": request.user.has_perm("bus_tracker_app.manage_operational_data")
            or request.user.has_perm("bus_tracker_app.prepare_trip"),
        "can_share": request.user.has_perm("bus_tracker_app.post_trip_location")
            and trip.monitor.user_id == request.user.pk,
        "can_attend": request.user.has_perm("bus_tracker_app.record_trip_attendance")
            and (request.user.is_superuser or trip.monitor.user_id == request.user.pk),
        "error": error,
    }, status=status)


@never_cache
@login_required
@require_GET
def trip_list(request):
    return render(request, "bus_tracker_app/trips/list.html", {
        "trips": operational_trips(request.user).order_by("-date", "leg", "pk"),
        "today": timezone.localdate(),
    })


@never_cache
@login_required
@require_GET
def trip_detail(request, trip_id):
    return _workspace(request, get_object_or_404(operational_trips(request.user), pk=trip_id))


@never_cache
@login_required
@require_GET
def trip_state(request, trip_id):
    trip = get_object_or_404(operational_trips(request.user), pk=trip_id)
    can_share = request.user.has_perm("bus_tracker_app.post_trip_location") and trip.monitor.user_id == request.user.pk
    return JsonResponse({"status": trip.status, "can_share": can_share})


def _transition(request, trip_id, target):
    try:
        trip, changed = transition_trip(user=request.user, trip_id=trip_id, target=target)
    except TripStateError as error:
        trip = get_object_or_404(operational_trips(request.user, transition=True), pk=trip_id)
        return _workspace(request, trip, error=str(error), status=409)
    messages.success(request, f"Trip is {trip.status}." if changed else f"Trip was already {trip.status}.")
    return redirect("bus_tracker_app:trip_detail", trip_id=trip.pk)


@login_required
@require_POST
def start_trip(request, trip_id):
    return _transition(request, trip_id, Trip.Status.ACTIVE)


@login_required
@require_POST
def complete_trip(request, trip_id):
    return _transition(request, trip_id, Trip.Status.COMPLETED)
