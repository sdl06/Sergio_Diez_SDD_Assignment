from django.urls import path

from . import views


app_name = "attendance"

urlpatterns = [
    path("children/<int:child_id>/trips/<int:trip_id>/absence/", views.child_trip_absence, name="child_trip_absence"),
    path("trips/<int:trip_id>/attendance/", views.trip_attendance_roster, name="trip_attendance_roster"),
    path(
        "trips/<int:trip_id>/attendance/<int:student_id>/",
        views.trip_attendance_record, name="trip_attendance_record",
    ),
]
