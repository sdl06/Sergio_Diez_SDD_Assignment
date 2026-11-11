"""Attendance rules and persistence using verified trip facts."""

from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import AbsenceNotice, StudentAttendance
from .trip_context import TripContext
from .validators import AttendancePayloadError


class AttendanceStateError(Exception):
    """The trip lifecycle does not allow this action."""


def _check_child(trip, student_id, *, parent_only):
    can_view = not parent_only and trip.can_view_all_children
    if not can_view and student_id not in trip.parent_child_ids:
        raise Http404
    _check_roster_member(trip, student_id)


def _check_roster_member(trip, student_id):
    if not any(student.student_id == student_id for student in trip.roster):
        raise Http404


def _check_monitor(trip):
    if not trip.can_record_attendance:
        raise PermissionDenied


def _notice_state(trip, student_id, notice):
    observation = StudentAttendance.objects.filter(trip_id=trip.trip_id, student_id=student_id).first()
    return {
        "student_id": student_id,
        "trip_id": trip.trip_id,
        "leg": trip.leg,
        "status": notice.status if notice else "not_reported",
        "absent": bool(notice and notice.status == AbsenceNotice.Status.REPORTED),
        "reported_at": notice.reported_at if notice else None,
        "updated_at": notice.updated_at if notice else None,
        "attendance": observation.status if observation else "unrecorded",
        "recorded_at": observation.recorded_at if observation else None,
    }


def get_absence_state(trip: TripContext, student_id: int):
    _check_child(trip, student_id, parent_only=False)
    notice = AbsenceNotice.objects.filter(trip_id=trip.trip_id, student_id=student_id).first()
    return _notice_state(trip, student_id, notice)


def set_absence_notice(trip: TripContext, student_id: int, absent: bool):
    if type(absent) is not bool:
        raise AttendancePayloadError("absent must be a Boolean.")
    _check_child(trip, student_id, parent_only=True)
    if trip.status != "prepared":
        raise AttendanceStateError("This action requires a prepared trip.")
    notice, created = AbsenceNotice.objects.update_or_create(
        trip_id=trip.trip_id,
        student_id=student_id,
        defaults={
            "status": AbsenceNotice.Status.REPORTED if absent else AbsenceNotice.Status.CANCELLED,
            "reported_by_id": trip.actor_id,
        },
    )
    return _notice_state(trip, student_id, notice), created


def record_attendance(trip: TripContext, student_id: int, status: str):
    _check_monitor(trip)
    if not isinstance(status, str) or status not in StudentAttendance.Status.values:
        raise AttendancePayloadError("status must be 'present' or 'absent'.")
    if trip.status != "active":
        raise AttendanceStateError("This action requires an active trip.")
    _check_roster_member(trip, student_id)
    return StudentAttendance.objects.update_or_create(
        trip_id=trip.trip_id,
        student_id=student_id,
        defaults={"status": status, "recorded_by_id": trip.actor_id},
    )


def build_attendance_roster(trip: TripContext):
    _check_monitor(trip)
    notices = {row.student_id: row for row in AbsenceNotice.objects.filter(trip_id=trip.trip_id)}
    observations = {row.student_id: row for row in StudentAttendance.objects.filter(trip_id=trip.trip_id)}
    roster = []
    for student in sorted(trip.roster, key=lambda row: (row.name, row.student_id)):
        notice = notices.get(student.student_id)
        observation = observations.get(student.student_id)
        roster.append({
            "student_id": student.student_id,
            "name": student.name,
            "stop_id": student.stop_id,
            "stop_name": student.stop_name,
            "absence_notice": notice.status if notice else None,
            "attendance": observation.status if observation else "unrecorded",
            "recorded_at": observation.recorded_at if observation else None,
        })
    return {"trip_id": trip.trip_id, "leg": trip.leg, "status": trip.status, "students": roster}
