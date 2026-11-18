"""Verified caller and trip facts consumed by attendance."""

from dataclasses import dataclass
from http.client import HTTPException
from http.cookies import SimpleCookie
import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest


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


class TripAuthenticationRequired(Exception):
    """Trip Operations did not authenticate the caller."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get_trip_context(request: HttpRequest, trip_id: int) -> TripContext:
    if not request.COOKIES.get("trip_ops_sessionid"):
        raise TripAuthenticationRequired

    cookies = SimpleCookie()
    for name in ("trip_ops_sessionid", "trip_ops_csrftoken"):
        if name in request.COOKIES:
            cookies[name] = request.COOKIES[name]
    headers = {
        "Accept": "application/json",
        "Cookie": "; ".join(cookie.OutputString() for cookie in cookies.values()),
    }
    writing = request.method == "POST"
    if writing:
        # Trip Operations checks CSRF against the caller's original browser request.
        for name in ("X-CSRFToken", "Origin", "Referer"):
            if name in request.headers:
                headers[name] = request.headers[name]

    base_url = settings.TRIP_OPS_BASE_URL.rstrip("/")
    outbound = Request(
        f"{base_url}/api/trips/{trip_id}/attendance-context/",
        headers=headers,
        method="POST" if writing else "GET",
        data=b"" if writing else None,
    )
    try:
        with build_opener(NoRedirects()).open(outbound, timeout=settings.TRIP_OPS_TIMEOUT_SECONDS) as response:
            data = json.load(response)
        if (
            data["trip_id"] != trip_id
            or type(data["actor_id"]) is not int
            or type(data["can_record_attendance"]) is not bool
            or type(data["can_view_all_children"]) is not bool
            or data["status"] not in {"prepared", "active", "completed"}
        ):
            raise TripContextUnavailable
        return TripContext(
            trip_id=trip_id,
            status=data["status"],
            leg=data["leg"],
            actor_id=data["actor_id"],
            roster=tuple(RosterStudent(**student) for student in data["roster"]),
            parent_child_ids=frozenset(data["parent_child_ids"]),
            can_view_all_children=data["can_view_all_children"],
            can_record_attendance=data["can_record_attendance"],
        )
    except HTTPError as error:
        error.close()
        if error.code == 401:
            raise TripAuthenticationRequired from error
        if error.code == 403:
            raise PermissionDenied from error
        if error.code == 404:
            raise Http404 from error
        raise TripContextUnavailable from error
    except (URLError, OSError, HTTPException, KeyError, TypeError, ValueError) as error:
        raise TripContextUnavailable from error
