from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import (
    BusForm,
    MonitorForm,
    PrepareTripForm,
    RouteForm,
    StopForm,
    StudentAttendanceForm,
    StudentForm,
    TripForm,
)
from .models import Bus, Monitor, Route, Stop, Student, StudentAttendance, Trip


def home(request):
    return render(request, "bus_tracker_app/home.html")


@login_required
@permission_required("bus_tracker_app.prepare_trip", raise_exception=True)
@require_GET
def create_trip(request):
    route_id = request.GET.get("route")
    if route_id and not route_id.isdecimal():
        raise Http404("Unknown route.")

    is_admin = request.user.has_perm("bus_tracker_app.manage_operational_data")
    routes = Route.objects.all() if is_admin else Route.objects.filter(monitors__user=request.user)
    selected_route = get_object_or_404(Route, pk=route_id) if route_id else None
    if selected_route and not is_admin and not routes.filter(pk=selected_route.pk).exists():
        raise PermissionDenied("This route is not assigned to you.")
    children = (
        selected_route.students.select_related("assigned_stop").order_by("assigned_stop__descriptor", "name")
        if selected_route else Student.objects.none()
    )
    return render(
        request,
        "bus_tracker_app/admin/create_trip.html",
        {
            "routes": routes,
            "selected_route": selected_route,
            "monitors": (
                selected_route.monitors.all() if is_admin else selected_route.monitors.filter(user=request.user)
            ) if selected_route else Monitor.objects.none(),
            "children": children,
        },
    )


def authorized_trip_route(user, route_id):
    route = get_object_or_404(Route, pk=route_id)
    if user.has_perm("bus_tracker_app.manage_operational_data"):
        return route, None
    monitor = Monitor.objects.filter(user=user, route=route).first()
    if monitor is None:
        raise PermissionDenied("This route is not assigned to you.")
    return route, monitor


@login_required
@permission_required("bus_tracker_app.prepare_trip", raise_exception=True)
@require_GET
def prepare_trip_form(request, route_id):
    route, monitor = authorized_trip_route(request.user, route_id)
    form = PrepareTripForm(route=route, assigned_monitor=monitor)
    return render(request, "bus_tracker_app/admin/prepare_trip.html", {"route": route, "form": form})


@login_required
@permission_required("bus_tracker_app.prepare_trip", raise_exception=True)
@require_POST
def prepare_trip(request, route_id):
    route, monitor = authorized_trip_route(request.user, route_id)
    form = PrepareTripForm(request.POST, route=route, assigned_monitor=monitor)
    if form.is_valid():
        with transaction.atomic():
            trip, created = Trip.objects.get_or_create(
                route=route,
                date=form.cleaned_data["date"],
                defaults={"bus": form.cleaned_data["bus"], "monitor": form.cleaned_data["monitor"]},
            )
            if created:
                trip.students.set(route.students.all())
        if created:
            messages.success(request, f"{trip} was prepared with the route's students.")
        else:
            messages.info(request, f"{trip} already exists; no details were changed.")
        return redirect("bus_tracker_app:prepare_trip_form", route_id=route.pk)
    return render(request, "bus_tracker_app/admin/prepare_trip.html", {"route": route, "form": form})


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


@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
def management_home(request):
    resources = [
        {"key": key, "label": config["label"], "count": config["model"].objects.count()}
        for key, config in CRUD_RESOURCES.items()
    ]
    return render(request, "bus_tracker_app/crud/index.html", {"resources": resources})


@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
def record_list(request, resource):
    config = get_resource(resource)
    records = config["model"].objects.all()
    return render(
        request,
        "bus_tracker_app/crud/list.html",
        {"resource": resource, "label": config["label"], "singular": config["singular"], "records": records},
    )


@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
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


@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
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


@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
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
