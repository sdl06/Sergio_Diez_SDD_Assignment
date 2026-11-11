"""Verified caller and trip facts consumed by attendance."""

from dataclasses import dataclass

from django.http import HttpRequest


@dataclass(frozen=True)
class RosterStudent:
    student_id: int
    name: str
    stop_id: int
    stop_name: str


@dataclass(frozen=True)
class TripContext:
    trip_id: int
    status: str
    leg: int
    actor_id: int
    roster: tuple[RosterStudent, ...]
    parent_child_ids: frozenset[int] = frozenset()
    can_view_all_children: bool = False
    can_record_attendance: bool = False


class TripContextUnavailable(Exception):
    """Verified identity and trip facts are unavailable."""


def get_trip_context(request: HttpRequest, trip_id: int) -> TripContext:
    # The standalone extraction has no source for these facts yet.
    raise TripContextUnavailable
