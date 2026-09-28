from django.urls import path

from . import views


app_name = "tracking"

urlpatterns = [
    path("trips/<int:trip_id>/locations/", views.post_trip_location, name="post_trip_location"),
    path(
        "children/<int:child_id>/trips/<int:trip_id>/location/",
        views.latest_child_trip_location,
        name="latest_child_trip_location",
    ),
]
