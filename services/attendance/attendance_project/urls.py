from django.urls import include, path

from .health import health

urlpatterns = [
    path("health", health, name="health"),
    path("api/", include("bus_tracker_app.attendance.urls")),
]
