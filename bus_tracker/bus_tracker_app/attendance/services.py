"""Attendance authorization, lifecycle rules and database operations."""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Prefetch
from django.shortcuts import get_object_or_404

from ..models import Student, Trip
from .models import AbsenceNotice, StudentAttendance
from .validators import AttendancePayloadError


class AttendanceStateError(Exception):
    """The trip lifecycle does not allow this action."""


def get_authorized_trip_for_attendance(user, trip_id):
    if not user.is_authenticated or not user.has_perm("bus_tracker_app.record_trip_attendance"):
        raise PermissionDenied("You cannot record trip attendance.")
    trip = get_object_or_404(Trip.objects.select_related("monitor"), pk=trip_id)
    if not user.is_superuser and trip.monitor.user_id != user.pk:
        raise PermissionDenied("You are not the monitor assigned to this trip.")
    return trip


def _writable_trip(trip_id, expected_status):
    # The conditional no-op UPDATE checks the current state and acquires a write
    # lock before subsequent reads. Unlike select_for_update(), this also works
    # on SQLite. The surrounding transaction holds the lock until the upsert ends.
    matched = Trip.objects.filter(pk=trip_id, status=expected_status).update(status=F("status"))
    if not matched:
        get_object_or_404(Trip, pk=trip_id)
        raise AttendanceStateError(f"This action requires a {expected_status} trip.")
    return get_object_or_404(Trip, pk=trip_id)


@transaction.atomic
def set_absence_notice(*, user, child, trip, absent):
    if type(absent) is not bool:
        raise AttendancePayloadError("absent must be a Boolean.")
    # Check access again here so callers other than HTTP views cannot bypass it.
    child = get_object_or_404(Student, pk=child.pk, parent_accesses__user=user)
    trip = _writable_trip(trip.pk, Trip.Status.PREPARED)
    get_object_or_404(trip.students, pk=child.pk)
    return AbsenceNotice.objects.update_or_create(
        student=child,
        trip=trip,
        defaults={
            "status": AbsenceNotice.Status.REPORTED if absent else AbsenceNotice.Status.CANCELLED,
            "reported_by": user,
        },
    )


@transaction.atomic
def record_attendance(*, user, trip, student_id, status):
    if not isinstance(status, str) or status not in StudentAttendance.Status.values:
        raise AttendancePayloadError("status must be 'present' or 'absent'.")
    # Re-authorize against current assignment, not a possibly stale view object.
    get_authorized_trip_for_attendance(user, trip.pk)
    trip = _writable_trip(trip.pk, Trip.Status.ACTIVE)
    trip = get_authorized_trip_for_attendance(user, trip.pk)
    student = get_object_or_404(trip.students, pk=student_id)
    return StudentAttendance.objects.update_or_create(
        student=student,
        trip=trip,
        defaults={"status": status, "recorded_by": user},
    )


def build_attendance_roster(trip):
    students = trip.students.select_related("assigned_stop").prefetch_related(
        Prefetch("absence_notices", queryset=AbsenceNotice.objects.filter(trip=trip), to_attr="trip_notices"),
        Prefetch(
            "attendance_records", queryset=StudentAttendance.objects.filter(trip=trip),
            to_attr="trip_observations",
        ),
    ).order_by("name", "pk")
    roster = []
    for student in students:
        notice = next(iter(student.trip_notices), None)
        observation = next(iter(student.trip_observations), None)
        roster.append({
            "student_id": student.pk,
            "name": student.name,
            "stop_id": student.assigned_stop_id,
            "stop_name": student.assigned_stop.descriptor,
            "absence_notice": notice.status if notice else None,
            "attendance": observation.status if observation else "unrecorded",
            "recorded_at": observation.recorded_at if observation else None,
        })
    return {"trip_id": trip.pk, "leg": trip.leg, "status": trip.status, "students": roster}
