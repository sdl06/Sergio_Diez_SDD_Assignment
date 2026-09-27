import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def validate_latitude(value):
    if not math.isfinite(value) or not -90 <= value <= 90:
        raise ValidationError("Latitude must be a finite number between -90 and 90.")


def validate_longitude(value):
    if not math.isfinite(value) or not -180 <= value <= 180:
        raise ValidationError("Longitude must be a finite number between -180 and 180.")


class Route(models.Model):
    route_name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["route_name"]

    def __str__(self):
        return self.route_name


class Stop(models.Model):
    descriptor = models.CharField(max_length=100)
    longitude = models.FloatField()
    latitude = models.FloatField()
    assigned_route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="stops")
    configured_leg1_arrival = models.TimeField()
    configured_leg2_arrival = models.TimeField()

    class Meta:
        ordering = ["assigned_route__route_name", "descriptor"]
        constraints = [models.UniqueConstraint(fields=["assigned_route", "descriptor"], name="unique_stop_per_route")]

    def __str__(self):
        return f"{self.descriptor} ({self.assigned_route})"


class Bus(models.Model):
    license_plate = models.CharField(max_length=10, unique=True)
    capacity = models.PositiveIntegerField()
    bus_model = models.CharField(max_length=100)
    bus_contractor = models.CharField(max_length=100)
    current_longitude = models.FloatField(default=0)

    class Meta:
        ordering = ["license_plate"]

    def __str__(self):
        return f"{self.license_plate} · {self.bus_model}"


class Monitor(models.Model):
    name = models.CharField(max_length=100)
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="monitors")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="monitor_profile",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Student(models.Model):
    name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="students")
    assigned_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="students")

    class Meta:
        ordering = ["name"]

    def clean(self):
        if self.route_id and self.assigned_stop_id and self.assigned_stop.assigned_route_id != self.route_id:
            raise ValidationError({"assigned_stop": "The assigned stop must belong to the student's route."})

    def __str__(self):
        return self.name


class Trip(models.Model):
    class Leg(models.IntegerChoices):
        TO_SCHOOL = 1, "To school"
        FROM_SCHOOL = 2, "From school"

    class Status(models.TextChoices):
        PREPARED = "prepared", "Prepared"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="trips")
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name="trips")
    monitor = models.ForeignKey(Monitor, on_delete=models.PROTECT, related_name="trips")
    date = models.DateField()
    leg = models.PositiveSmallIntegerField(choices=Leg.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PREPARED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    students = models.ManyToManyField(Student, blank=True, related_name="trips")

    class Meta:
        ordering = ["-date", "route__route_name", "leg"]
        constraints = [models.UniqueConstraint(fields=["route", "date", "leg"], name="one_trip_per_route_day_leg")]
        permissions = [
            ("prepare_trip", "Can prepare trips"),
            ("manage_operational_data", "Can manage operational data"),
        ]

    def clean(self):
        if self.route_id and self.monitor_id and self.monitor.route_id != self.route_id:
            raise ValidationError({"monitor": "The monitor must be assigned to this route."})

    def __str__(self):
        return f"{self.route} · {self.date:%d %b %Y} · {self.get_leg_display()}"


class TripLocation(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="location_samples")
    latitude = models.FloatField(validators=[validate_latitude])
    longitude = models.FloatField(validators=[validate_longitude])
    accuracy_m = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20)
    client_sample_id = models.UUIDField()

    class Meta:
        ordering = ["-observed_at", "-received_at"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "client_sample_id"], name="unique_location_sample_per_trip")
        ]
        indexes = [models.Index(fields=["trip", "-observed_at", "-received_at"], name="trip_location_latest_idx")]

    def clean(self):
        if self.observed_at and not timezone.is_aware(self.observed_at):
            raise ValidationError({"observed_at": "The observed time must include a timezone."})

    def __str__(self):
        return f"{self.trip} · {self.observed_at}"


class StudentAttendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="attendance_records")
    presence = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "trip"], name="one_attendance_record_per_student_trip")]

    def clean(self):
        if self.trip_id and self.student_id and not self.trip.students.filter(pk=self.student_id).exists():
            raise ValidationError({"student": "The student must be assigned to the selected trip."})

    def __str__(self):
        return f"{self.student} · {self.trip}"
