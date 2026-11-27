from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..auth import login_required
from ..models import ParentChildAccess, Trip
from .services import TripStateError, operational_trips, transition_trip


def trip_data(trip):
    return {
        "id": trip.pk,
        "route_id": trip.route_id,
        "route_name": trip.route.route_name,
        "bus_id": trip.bus_id,
        "bus_plate": trip.bus.license_plate,
        "monitor_id": trip.monitor_id,
        "monitor_name": trip.monitor.name,
        "date": trip.date,
        "leg": trip.leg,
        "status": trip.status,
        "started_at": trip.started_at,
        "completed_at": trip.completed_at,
    }


def can_share_location(user, trip):
    return user.has_perm("bus_tracker_app.post_trip_location") and trip.monitor.user_id == user.pk


def can_record_attendance(user, trip):
    return user.has_perm("bus_tracker_app.record_trip_attendance") and (
        user.is_superuser or trip.monitor.user_id == user.pk
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def attendance_context(request, trip_id):
    """Return current attendance facts scoped to the authenticated caller."""
    trip = get_object_or_404(Trip.objects.select_related("monitor"), pk=trip_id)
    user = request.user
    can_record = can_record_attendance(user, trip)
    can_view_all = user.has_perm("bus_tracker_app.manage_operational_data")
    students = trip.students.all()
    child_ids = list(ParentChildAccess.objects.filter(
        user=user, student__in=students,
    ).values_list("student_id", flat=True))
    if not (can_record or can_view_all or child_ids):
        raise Http404
    if not (can_record or can_view_all):
        students = students.filter(pk__in=child_ids)
    return JsonResponse({
        "trip_id": trip.pk,
        "status": trip.status,
        "leg": trip.leg,
        "actor_id": user.pk,
        "parent_child_ids": child_ids,
        "can_view_all_children": can_view_all,
        "can_record_attendance": can_record,
        "roster": [
            {"student_id": pk, "name": name, "stop_id": stop_id, "stop_name": stop_name}
            for pk, name, stop_id, stop_name in students.values_list(
                "id", "name", "assigned_stop_id", "assigned_stop__descriptor",
            )
        ],
    })


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
        "can_record": can_record_attendance(request.user, trip),
        "can_transition": request.user.has_perm("bus_tracker_app.prepare_trip")
        or request.user.has_perm("bus_tracker_app.manage_operational_data"),
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
