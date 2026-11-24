"""Register the models owned by the attendance app."""

from django.db import models

from .attendance.models import AbsenceNotice, StudentAttendance

__all__ = ["AbsenceNotice", "DatabaseHealthCheck", "StudentAttendance"]


class DatabaseHealthCheck(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True)
    checked_at = models.DateTimeField()
