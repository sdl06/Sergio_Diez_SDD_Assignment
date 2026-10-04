"""Isolated database fixtures: never seed the development SQLite database."""
from datetime import date, time
from uuid import uuid4

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone

from bus_tracker_app.models import Bus, Monitor, Route, Stop, Student, Trip
from bus_tracker_app.tracking.models import ParentChildAccess


def grant(user, *codenames):
    user.user_permissions.add(*Permission.objects.filter(
        content_type__app_label="bus_tracker_app", codename__in=codenames,
    ))
    return user


def fixtures():
    """A test-only Madrid corridor; not an ordered or certified bus itinerary."""
    route = Route.objects.create(route_name="Madrid · Alcalá–Prado")
    other = Route.objects.create(route_name="Other route")
    stop = Stop.objects.create(descriptor="Cibeles, Paseo del Prado", latitude=40.4181,
        longitude=-3.6938, assigned_route=route,
        configured_leg1_arrival=time(8, 30), configured_leg2_arrival=time(17))
    other_stop = Stop.objects.create(descriptor="Other stop", latitude=40.4168,
        longitude=-3.6945, assigned_route=other,
        configured_leg1_arrival=time(8, 30), configured_leg2_arrival=time(17))
    bus = Bus.objects.create(license_plate="TEST123", capacity=30,
        bus_model="Test bus", bus_contractor="Test operator")
    monitor_user = grant(User.objects.create_user("monitor", password="test-pass"),
        "prepare_trip", "post_trip_location", "record_trip_attendance")
    other_user = grant(User.objects.create_user("other-monitor", password="test-pass"),
        "prepare_trip", "post_trip_location", "record_trip_attendance")
    monitor = Monitor.objects.create(name="Monitor", route=route, user=monitor_user)
    other_monitor = Monitor.objects.create(name="Other monitor", route=other, user=other_user)
    parent = User.objects.create_user("parent", password="test-pass")
    outsider = User.objects.create_user("outsider", password="test-pass")
    admin = User.objects.create_superuser("admin", "admin@example.test", "test-pass")
    child = Student.objects.create(name="Ana", date_of_birth=date(2015, 1, 1), route=route, assigned_stop=stop)
    sibling = Student.objects.create(name="Luis", date_of_birth=date(2016, 1, 1), route=route, assigned_stop=stop)
    foreign_child = Student.objects.create(name="Elsewhere", date_of_birth=date(2015, 1, 1), route=other, assigned_stop=other_stop)
    ParentChildAccess.objects.create(user=parent, student=child)
    ParentChildAccess.objects.create(user=parent, student=sibling)
    trip = Trip.objects.create(route=route, bus=bus, monitor=monitor, date=timezone.localdate(), leg=1)
    trip.students.set([child, sibling])
    return locals()


class DomainCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, value in fixtures().items():
            setattr(cls, name, value)

    def login(self, user=None):
        self.client.force_login(user or self.monitor_user)

    def fix(self, **changes):
        return dict(latitude=40.4199, longitude=-3.6895, accuracy_m=5,
            observed_at=timezone.now().isoformat(), client_sample_id=str(uuid4()), **changes)

    def json_post(self, path, payload):
        return self.client.post(path, payload, content_type="application/json")
