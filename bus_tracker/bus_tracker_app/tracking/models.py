from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from ..models import Student, Trip, validate_latitude, validate_longitude


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


class ParentChildAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="child_accesses",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_accesses",
    )

    class Meta:
        ordering = ["student__name", "user__username"]
        constraints = [
            models.UniqueConstraint(fields=["user", "student"], name="unique_parent_child_access")
        ]

    def __str__(self):
        return f"{self.user} can view {self.student}"


__all__ = ["ParentChildAccess", "TripLocation"]
