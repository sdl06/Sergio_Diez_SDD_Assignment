from django.urls import include, path

urlpatterns = [
    path("api/", include("bus_tracker_app.attendance.urls")),
]
