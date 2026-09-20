from django.db import models
from .models import Student
from ..tracking.models import Trip

class StudentAttendance:
    student = models.ForeignKey(Student)
    trip = models.ForeignKey(Trip)
    presence = models.BooleanField()

