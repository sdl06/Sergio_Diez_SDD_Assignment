"""Concurrent tracking writes against a shared test database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import connections, transaction
from django.db.models.query import QuerySet
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from bus_tracker_app.models import Trip
from bus_tracker_app.tracking.models import TripLocation
from bus_tracker_app.tracking.views import save_sample_once
from bus_tracker_app.trips.services import transition_trip
from .helpers import fixtures


@override_settings(LOCATION_MIN_SAMPLE_INTERVAL_SECONDS=0)
class ConcurrentWritesTests(TransactionTestCase):
    def setUp(self):
        name = str(connections["default"].settings_dict["NAME"])
        if name == ":memory:" or "mode=memory" in name:
            self.skipTest("Use FileSQLiteRunner to exercise file-backed SQLite locking")
        for key, value in fixtures().items():
            setattr(self, key, value)

    def worker(self, action):
        try:
            return action()
        finally:
            connections.close_all()

    def hold_transition(self, target, locked, release):
        user = User.objects.get(pk=self.monitor_user.pk)
        # Resolve permissions before holding the lock; the contender still uses
        # the complete, unmodified HTTP authentication/authorization workflow.
        user.has_perm("bus_tracker_app.manage_operational_data")
        user.has_perm("bus_tracker_app.prepare_trip")
        with transaction.atomic():
            transition_trip(user=user, trip_id=self.trip.pk, target=target)
            locked.set()
            if not release.wait(10):
                raise RuntimeError("The test did not release the transition transaction")

    def test_simultaneous_gps_retry_creates_one_sample(self):
        Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.ACTIVE)
        gate = Barrier(2, timeout=5)
        payload = dict(latitude=40.4199, longitude=-3.6895, accuracy_m=5,
            observed_at=timezone.now(), client_sample_id=uuid4())

        def post():
            user = User.objects.get(pk=self.monitor_user.pk)
            trip = Trip.objects.get(pk=self.trip.pk)
            gate.wait()
            sample, created = save_sample_once(trip, payload, user=user)
            return sample.pk, created

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, post) for _ in range(2)]
            results = [future.result(timeout=8) for future in futures]
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(TripLocation.objects.count(), 1)

    def test_gps_post_waiting_on_completion_returns_conflict(self):
        Trip.objects.filter(pk=self.trip.pk).update(status=Trip.Status.ACTIVE)
        client = Client(raise_request_exception=False)
        client.force_login(self.monitor_user)
        locked, release, attempted = Event(), Event(), Event()
        validated, continue_save = Event(), Event()
        original_update = QuerySet.update

        def pause_after_validation(*args, **kwargs):
            # Let the request actually read the active trip before SQL Server locks it.
            validated.set()
            if not continue_save.wait(10):
                raise RuntimeError("The test did not release the GPS request")
            return save_sample_once(*args, **kwargs)

        def observed_update(queryset, **kwargs):
            if queryset.model is Trip and "status" in kwargs and not isinstance(kwargs["status"], str):
                attempted.set()  # GPS's conditional no-op UPDATE, not the transition.
            return original_update(queryset, **kwargs)

        payload = dict(latitude=40.4199, longitude=-3.6895, accuracy_m=5,
            observed_at=timezone.now().isoformat(), client_sample_id=str(uuid4()))
        with (
            ThreadPoolExecutor(max_workers=2) as pool,
            patch.object(QuerySet, "update", observed_update),
            patch("bus_tracker_app.tracking.views.save_sample_once", side_effect=pause_after_validation),
        ):
            reader = pool.submit(self.worker, lambda: client.post(
                f"/api/trips/{self.trip.pk}/locations/", payload, content_type="application/json"))
            try:
                self.assertTrue(validated.wait(5))
                holder = pool.submit(self.worker, lambda: self.hold_transition("completed", locked, release))
                self.assertTrue(locked.wait(5))
                continue_save.set()
                self.assertTrue(attempted.wait(5))
            finally:
                continue_save.set()
                release.set()
            holder.result(timeout=8)
            response = reader.result(timeout=8)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(TripLocation.objects.exists())
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, Trip.Status.COMPLETED)
