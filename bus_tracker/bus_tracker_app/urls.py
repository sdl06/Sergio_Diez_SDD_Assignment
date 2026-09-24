from django.urls import path

from . import views


app_name = "bus_tracker_app"

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/trips/new/", views.create_trip, name="create_trip"),
    path("parents/live/", views.parent_live, name="parent_live"),
    path("manage/", views.management_home, name="management_home"),
    path("manage/<str:resource>/", views.record_list, name="record_list"),
    path("manage/<str:resource>/new/", views.record_create, name="record_create"),
    path("manage/<str:resource>/<int:pk>/edit/", views.record_update, name="record_update"),
    path("manage/<str:resource>/<int:pk>/delete/", views.record_delete, name="record_delete"),
]
