"""Register the two models owned by the attendance app."""

from .attendance.models import AbsenceNotice, StudentAttendance

__all__ = ["AbsenceNotice", "StudentAttendance"]
