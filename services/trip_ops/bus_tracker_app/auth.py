from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST


def login_required(view):
    @wraps(view)
    def authenticated(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "authentication_required"}, status=401)
        return view(request, *args, **kwargs)

    return authenticated


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
