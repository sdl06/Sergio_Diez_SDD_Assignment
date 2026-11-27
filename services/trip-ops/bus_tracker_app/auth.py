import json
import re
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.sessions.backends.db import SessionStore
from django.http import JsonResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST


class BearerSessionMiddleware:
    """Load browser API sessions from their explicit Authorization header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        authorization = request.headers.get("Authorization")
        if authorization is None:
            return self.get_response(request)

        match = re.fullmatch(r"Bearer ([a-z0-9]{32})", authorization, re.IGNORECASE)
        if match is None:
            return JsonResponse({"error": "authentication_required"}, status=401)

        session = SessionStore(session_key=match.group(1))
        if not session.get("schoolrun_browser_session"):
            return JsonResponse({"error": "authentication_required"}, status=401)

        request.session = session
        request.schoolrun_bearer_session = True
        return self.get_response(request)


class BearerAwareCsrfMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if getattr(request, "schoolrun_bearer_session", False):
            # The browser must explicitly attach the token. Cookie requests still use CSRF.
            return None
        return super().process_view(request, callback, callback_args, callback_kwargs)


def login_required(view):
    @wraps(view)
    def authenticated(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        return view(request, *args, **kwargs)

    return authenticated


@never_cache
@csrf_exempt
@require_POST
def browser_login(request):
    if request.headers.get("Origin") != settings.UI_ORIGIN:
        return JsonResponse({"error": "invalid_origin"}, status=403)
    if request.content_type != "application/json":
        return JsonResponse({"error": "content_type_must_be_json"}, status=415)
    try:
        credentials = json.loads(request.body)
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "invalid_credentials"}, status=400)
    if not isinstance(credentials, dict):
        return JsonResponse({"error": "invalid_credentials"}, status=400)

    username = credentials.get("username")
    password = credentials.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return JsonResponse({"error": "invalid_credentials"}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({"error": "invalid_credentials"}, status=401)

    request.session = SessionStore()
    login(request, user)
    request.session["schoolrun_browser_session"] = True
    request.session.set_expiry(3600)
    request.session.save()
    can_prepare = user.has_perm("bus_tracker_app.prepare_trip")
    can_manage = user.has_perm("bus_tracker_app.manage_operational_data")
    return JsonResponse({
        "token": request.session.session_key,
        "can_prepare": can_prepare,
        "can_manage": can_manage,
        "can_operate": can_prepare or can_manage or user.has_perm("bus_tracker_app.post_trip_location"),
    })


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "GET":
        return JsonResponse({"csrf_token": get_token(request)})
    user = authenticate(
        request, username=request.POST.get("username"), password=request.POST.get("password")
    )
    if user is None:
        return JsonResponse({"error": "invalid_credentials"}, status=401)
    login(request, user)
    return JsonResponse({"user_id": user.pk, "csrf_token": get_token(request)})


@never_cache
@require_POST
@login_required
def logout_view(request):
    logout(request)
    return JsonResponse({"logged_out": True})
