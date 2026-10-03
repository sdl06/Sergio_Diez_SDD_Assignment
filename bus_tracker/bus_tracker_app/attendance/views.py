"""Session-authenticated, CSRF-protected JSON attendance endpoints."""

from functools import wraps
import sqlite3

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import OperationalError, connection
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ..models import Student, Trip
from .models import AbsenceNotice, StudentAttendance
from .services import (
    AttendanceStateError, build_attendance_roster,
    get_authorized_trip_for_attendance, record_attendance, set_absence_notice,
)
from .validators import AttendancePayloadError, parse_absent_json, parse_attendance_json


def _json(payload, status=200):
    return JsonResponse(payload, status=status, headers={"Cache-Control": "no-store"})


def _api_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except PermissionDenied:
            return _json({"error": "permission_denied"}, 403)
        except Http404:
            return _json({"error": "not_found"}, 404)
        except OperationalError as error:
            cause = error.__cause__
            code = getattr(cause, "sqlite_errorcode", None)
            # SQLite extended codes retain the primary code in the low byte.
            # Do not hide missing tables, connection failures or other DB errors.
            if (
                connection.vendor != "sqlite"
                or not isinstance(cause, sqlite3.OperationalError)
                or not isinstance(code, int)
                or (code & 0xFF) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
            ):
                raise
            # Atomic service calls have already unwound/rolled back here.
            # Do not automatically retry with an out-of-date trip state.
            response = _json({
                "error": "database_busy",
                "detail": "Another request is updating the database. Refresh the trip and try again.",
            }, 503)
            response["Retry-After"] = "1"
            return response
    return wrapped


def _notice_state(child, trip, notice):
    observation = StudentAttendance.objects.filter(student=child, trip=trip).first()
    return {
        "student_id": child.pk,
        "trip_id": trip.pk,
        "leg": trip.leg,
        "status": notice.status if notice else "not_reported",
        "absent": bool(notice and notice.status == AbsenceNotice.Status.REPORTED),
        "reported_at": notice.reported_at if notice else None,
        "updated_at": notice.updated_at if notice else None,
        "attendance": observation.status if observation else "unrecorded",
        "recorded_at": observation.recorded_at if observation else None,
    }


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
@_api_errors
def child_trip_absence(request, child_id, trip_id):
    child = get_object_or_404(Student, pk=child_id, parent_accesses__user=request.user)
    trip = get_object_or_404(Trip, pk=trip_id, students=child)
    if request.method == "GET":
        notice = AbsenceNotice.objects.filter(student=child, trip=trip).first()
        return _json(_notice_state(child, trip, notice))
    if request.content_type != "application/json":
        return _json({"error": "content_type_must_be_json"}, 415)
    try:
        absent = parse_absent_json(request.body)
        notice, created = set_absence_notice(user=request.user, child=child, trip=trip, absent=absent)
    except AttendancePayloadError as error:
        return _json({"error": "invalid_absence", "detail": str(error)}, 400)
    except AttendanceStateError as error:
        return _json({"error": "trip_not_prepared", "detail": str(error)}, 409)
    return _json(_notice_state(child, trip, notice), 201 if created else 200)


@never_cache
@login_required
@require_GET
@_api_errors
def trip_attendance_roster(request, trip_id):
    trip = get_authorized_trip_for_attendance(request.user, trip_id)
    return _json(build_attendance_roster(trip))


@never_cache
@login_required
@require_POST
@_api_errors
def trip_attendance_record(request, trip_id, student_id):
    trip = get_authorized_trip_for_attendance(request.user, trip_id)
    if request.content_type != "application/json":
        return _json({"error": "content_type_must_be_json"}, 415)
    try:
        status = parse_attendance_json(request.body)
        observation, created = record_attendance(
            user=request.user, trip=trip, student_id=student_id, status=status,
        )
    except AttendancePayloadError as error:
        return _json({"error": "invalid_attendance", "detail": str(error)}, 400)
    except AttendanceStateError as error:
        return _json({"error": "trip_not_active", "detail": str(error)}, 409)
    return _json({
        "trip_id": trip.pk,
        "student_id": observation.student_id,
        "status": observation.status,
        "recorded_at": observation.recorded_at,
    }, 201 if created else 200)
