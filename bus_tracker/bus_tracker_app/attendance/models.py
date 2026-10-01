"""Parent absence notices and monitor attendance observations for individual trips."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from ..models import Route, Student, Trip


class AbsenceNotice(models.Model):
    class Status(models.TextChoices):
        REPORTED = "reported", "Reported absent"
        CANCELLED = "cancelled", "Cancelled"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="absence_notices")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="absence_notices")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_absences"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED)
    reported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "trip"], name="one_absence_notice_per_student_trip")
        ]

    def clean(self):
        if self.trip_id and self.student_id and not self.trip.students.filter(pk=self.student_id).exists():
            raise ValidationError({"student": "The student must be assigned to the selected trip."})

    def __str__(self):
        return f"{self.student} · {self.trip} · {self.get_status_display()}"


class StudentAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=8, choices=Status.choices)
    # Historical Boolean records have no known recorder or observation timestamp.
    # null allows migration of that data; blank=False requires an actor in new forms.
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_attendance", null=True
    )
    recorded_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "trip"], name="one_attendance_record_per_student_trip")
        ]
        permissions = [("record_trip_attendance", "Can record attendance for an assigned trip")]

    def clean(self):
        if self.trip_id and self.student_id and not self.trip.students.filter(pk=self.student_id).exists():
            raise ValidationError({"student": "The student must be assigned to the selected trip."})

    def __str__(self):
        return f"{self.student} · {self.trip} · {self.get_status_display()}"


__all__ = ["AbsenceNotice", "Route", "Student", "StudentAttendance", "Trip"]
