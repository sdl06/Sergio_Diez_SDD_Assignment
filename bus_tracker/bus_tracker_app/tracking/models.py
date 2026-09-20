from django.db import models
from ..attendance.models import Route


class Stop(models.Model):
    descriptor = models.CharField(max_length = 100)
    longitude = models.FloatField(null=False)
    latitude = models.FloatField(null=False)
    assigned_route = models.ForeignKey(Route)
    configured_leg1_arrival = models.TimeField()
    configured_leg2_arrival = models.TimeField()

    def __str__(self):
        return self.descriptor

class Bus(models.Model):
    license_plate = models.CharField(max_length=10)
    capacity = models.IntegerField()
    bus_model = models.CharField(max_length = 100)
    bus_contractor = models.CharField(max_length = 100)
    current_longitude = models.FloatField()

class Trip(models.Model):
    route = models.ForeignKey(Route)
    bus = models.ForeignKey(Bus)
    date = models.DateField()

    def __str__(self):
        return f"{self.route} | {self.date}"