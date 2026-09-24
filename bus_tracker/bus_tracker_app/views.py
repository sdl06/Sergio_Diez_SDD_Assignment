from django.contrib import messages
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    BusForm,
    MonitorForm,
    RouteForm,
    StopForm,
    StudentAttendanceForm,
    StudentForm,
    TripForm,
)
from .models import Bus, Monitor, Route, Stop, Student, StudentAttendance, Trip


def home(request):
    return render(request, "bus_tracker_app/home.html")


def create_trip(request):
    route_id = request.GET.get("route")
    if route_id and not route_id.isdecimal():
        raise Http404("Unknown route.")

    selected_route = get_object_or_404(Route, pk=route_id) if route_id else None
    children = (
        selected_route.students.select_related("assigned_stop").order_by("assigned_stop__descriptor", "name")
        if selected_route else Student.objects.none()
    )
    return render(
        request,
        "bus_tracker_app/admin/create_trip.html",
        {
            "routes": Route.objects.all(),
            "selected_route": selected_route,
            "monitors": selected_route.monitors.all() if selected_route else Monitor.objects.none(),
            "children": children,
        },
    )

def get_trip_info(trip_id, request):
    trip = get_object_or_404()


def parent_live(request):
    return render(request, "bus_tracker_app/parents/live.html")


CRUD_RESOURCES = {
    "routes": {"model": Route, "form": RouteForm, "label": "Routes", "singular": "route"},
    "stops": {"model": Stop, "form": StopForm, "label": "Stops", "singular": "stop"},
    "buses": {"model": Bus, "form": BusForm, "label": "Buses", "singular": "bus"},
    "monitors": {"model": Monitor, "form": MonitorForm, "label": "Monitors", "singular": "monitor"},
    "students": {"model": Student, "form": StudentForm, "label": "Students", "singular": "student"},
    "trips": {"model": Trip, "form": TripForm, "label": "Trips", "singular": "trip"},
    "attendance": {
        "model": StudentAttendance,
        "form": StudentAttendanceForm,
        "label": "Attendance records",
        "singular": "attendance record",
    },
}


def get_resource(resource):
    try:
        return CRUD_RESOURCES[resource]
    except KeyError as error:
        raise Http404("Unknown management resource.") from error


def management_home(request):
    resources = [
        {"key": key, "label": config["label"], "count": config["model"].objects.count()}
        for key, config in CRUD_RESOURCES.items()
    ]
    return render(request, "bus_tracker_app/crud/index.html", {"resources": resources})


def record_list(request, resource):
    config = get_resource(resource)
    records = config["model"].objects.all()
    return render(
        request,
        "bus_tracker_app/crud/list.html",
        {"resource": resource, "label": config["label"], "singular": config["singular"], "records": records},
    )


@require_http_methods(["GET", "POST"])
def record_create(request, resource):
    config = get_resource(resource)
    form = config["form"](request.POST or None)
    if request.method == "POST" and form.is_valid():
        record = form.save()
        messages.success(request, f"{record} was created.")
        return redirect("bus_tracker_app:record_list", resource=resource)
    return render(
        request,
        "bus_tracker_app/crud/form.html",
        {"resource": resource, "label": config["label"], "singular": config["singular"], "form": form, "mode": "Create"},
    )


@require_http_methods(["GET", "POST"])
def record_update(request, resource, pk):
    config = get_resource(resource)
    record = get_object_or_404(config["model"], pk=pk)
    form = config["form"](request.POST or None, instance=record)
    if request.method == "POST" and form.is_valid():
        record = form.save()
        messages.success(request, f"{record} was updated.")
        return redirect("bus_tracker_app:record_list", resource=resource)
    return render(
        request,
        "bus_tracker_app/crud/form.html",
        {"resource": resource, "label": config["label"], "singular": config["singular"], "form": form, "mode": "Edit", "record": record},
    )


@require_http_methods(["GET", "POST"])
def record_delete(request, resource, pk):
    config = get_resource(resource)
    record = get_object_or_404(config["model"], pk=pk)
    if request.method == "POST":
        try:
            record.delete()
        except ProtectedError:
            messages.error(request, "This record is still used elsewhere and cannot be deleted.")
        else:
            messages.success(request, f"{record} was deleted.")
        return redirect("bus_tracker_app:record_list", resource=resource)
    return render(
        request,
        "bus_tracker_app/crud/confirm_delete.html",
        {"resource": resource, "label": config["label"], "singular": config["singular"], "record": record},
    )
