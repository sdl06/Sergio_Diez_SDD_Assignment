from django.http import JsonResponse
from django.urls import include, path

from .health import health

urlpatterns = [
    path("health", health, name="health"),
    path("", include("bus_tracker_app.urls")),
]


def handler403(request, exception):
    return JsonResponse({"error": "permission_denied"}, status=403)


def handler404(request, exception):
    return JsonResponse({"error": "not_found"}, status=404)


def csrf_failure(request, reason=""):
    return JsonResponse({"error": "csrf_failed"}, status=403)
