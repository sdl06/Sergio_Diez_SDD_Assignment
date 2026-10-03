from django.contrib.auth import views as auth_views
from django.urls import include, path

from . import views
from .trips import views as trip_views
from .forms import StyledAuthenticationForm


app_name = "bus_tracker_app"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/", include("bus_tracker_app.tracking.urls")),
    path("api/", include("bus_tracker_app.attendance.urls")),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html", authentication_form=StyledAuthenticationForm
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="bus_tracker_app:home"), name="logout"),
    path("admin/trips/new/", views.create_trip, name="create_trip"),
    path("routes/<int:route_id>/prepare/", views.prepare_trip_form, name="prepare_trip_form"),
    path("routes/<int:route_id>/prepare/submit/", views.prepare_trip, name="prepare_trip"),
    path("parents/live/", views.parent_live, name="parent_live"),
    path("trips/", trip_views.trip_list, name="trip_list"),
    path("trips/<int:trip_id>/", trip_views.trip_detail, name="trip_detail"),
    path("trips/<int:trip_id>/state/", trip_views.trip_state, name="trip_state"),
    path("trips/<int:trip_id>/start/", trip_views.start_trip, name="start_trip"),
    path("trips/<int:trip_id>/complete/", trip_views.complete_trip, name="complete_trip"),
    path("manage/", views.management_home, name="management_home"),
    path("manage/<str:resource>/", views.record_list, name="record_list"),
    path("manage/<str:resource>/new/", views.record_create, name="record_create"),
    path("manage/<str:resource>/<int:pk>/edit/", views.record_update, name="record_update"),
    path("manage/<str:resource>/<int:pk>/delete/", views.record_delete, name="record_delete"),
]
