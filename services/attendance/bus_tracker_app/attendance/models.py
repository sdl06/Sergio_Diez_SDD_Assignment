"""Parent absence notices and monitor attendance observations for individual trips."""

from django.db import models


class AbsenceNotice(models.Model):
    class Status(models.TextChoices):
        REPORTED = "reported", "Reported absent"
        CANCELLED = "cancelled", "Cancelled"

    student_id = models.PositiveBigIntegerField()
    trip_id = models.PositiveBigIntegerField()
    reported_by_id = models.PositiveBigIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED)
    reported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["trip_id", "student_id"], name="one_absence_notice_per_student_trip")
        ]

    def __str__(self):
        return f"Student {self.student_id} · Trip {self.trip_id} · {self.get_status_display()}"


class StudentAttendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"

    student_id = models.PositiveBigIntegerField()
    trip_id = models.PositiveBigIntegerField()
    status = models.CharField(max_length=8, choices=Status.choices)
    # Historical Boolean records have no known recorder or observation timestamp.
    recorded_by_id = models.PositiveBigIntegerField(null=True)
    recorded_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["trip_id", "student_id"], name="one_attendance_record_per_student_trip")
        ]

    def __str__(self):
        return f"Student {self.student_id} · Trip {self.trip_id} · {self.get_status_display()}"
