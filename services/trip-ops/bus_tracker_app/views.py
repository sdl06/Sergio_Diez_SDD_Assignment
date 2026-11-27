from django import forms
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.forms.models import model_to_dict
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .auth import login_required
from .forms import (
    BusForm,
    MonitorForm,
    PrepareTripForm,
    ParentChildAccessForm,
    RouteForm,
    StopForm,
    StudentForm,
    TripForm,
)
from .models import Bus, Monitor, Route, Stop, Student, Trip
from .tracking.access import visible_children
from .tracking.models import ParentChildAccess
from .trips.views import trip_data


@never_cache
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
    return JsonResponse({
        "routes": list(routes.values("id", "route_name")),
        "selected_route": _preparation_options(request.user, selected_route) if selected_route else None,
    })


def authorized_trip_route(user, route_id):
    route = get_object_or_404(Route, pk=route_id)
    if user.has_perm("bus_tracker_app.manage_operational_data"):
        return route, None
    monitor = Monitor.objects.filter(user=user, route=route).first()
    if monitor is None:
        raise PermissionDenied("This route is not assigned to you.")
    return route, monitor


@never_cache
@login_required
@permission_required("bus_tracker_app.prepare_trip", raise_exception=True)
@require_GET
def prepare_trip_form(request, route_id):
    route = get_object_or_404(Route, pk=route_id)
    return JsonResponse(_preparation_options(request.user, route))


def _preparation_options(user, route):
    route, monitor = authorized_trip_route(user, route.pk)
    monitors = route.monitors.filter(pk=monitor.pk) if monitor else route.monitors.all()
    return {
        "route_id": route.pk,
        "monitors": list(monitors.values("id", "name")),
        "buses": list(Bus.objects.values("id", "license_plate")),
        "students": list(route.students.values("id", "name", "assigned_stop_id")),
        "legs": list(Trip.Leg.values),
    }


@never_cache
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
                leg=form.cleaned_data["leg"],
                defaults={"bus": form.cleaned_data["bus"], "monitor": form.cleaned_data["monitor"]},
            )
            if created:
                trip.students.set(route.students.all())
        if not request.user.has_perm("bus_tracker_app.manage_operational_data") and trip.monitor.user_id != request.user.pk:
            return JsonResponse({"error": "trip_assigned_to_another_monitor"}, status=409)
        return JsonResponse({"trip": trip_data(trip), "created": created}, status=201 if created else 200)
    return JsonResponse({"errors": form.errors.get_json_data()}, status=400)


@never_cache
@login_required
@require_GET
def parent_live(request):
    children = visible_children(request.user).order_by("name", "pk")
    child_id = request.GET.get("child")
    trip_id = request.GET.get("trip")
    for value in (child_id, trip_id):
        if value and not value.isdecimal():
            raise Http404("Unknown journey.")
    child = get_object_or_404(children, pk=child_id) if child_id else children.first()
    trips = Trip.objects.filter(students=child).select_related("route", "bus", "monitor") if child else Trip.objects.none()
    trip = get_object_or_404(trips, pk=trip_id) if trip_id else (
        trips.filter(status=Trip.Status.ACTIVE).first() or trips.first()
    )
    return JsonResponse({
        "children": list(children.values("id", "name")),
        "child": {
            "id": child.pk,
            "name": child.name,
            "stop": {
                "id": child.assigned_stop_id,
                "name": child.assigned_stop.descriptor,
                "latitude": child.assigned_stop.latitude,
                "longitude": child.assigned_stop.longitude,
            },
        } if child else None,
        "trips": [trip_data(item) for item in trips],
        "trip": trip_data(trip) if trip else None,
        "can_report_absence": bool(child and ParentChildAccess.objects.filter(
            user=request.user, student=child,
        ).exists()),
    })


CRUD_RESOURCES = {
    "parent-access": {
        "model": ParentChildAccess, "form": ParentChildAccessForm,
        "label": "Parent-child access",
    },
    "routes": {"model": Route, "form": RouteForm, "label": "Routes"},
    "stops": {"model": Stop, "form": StopForm, "label": "Stops"},
    "buses": {"model": Bus, "form": BusForm, "label": "Buses"},
    "monitors": {"model": Monitor, "form": MonitorForm, "label": "Monitors"},
    "students": {"model": Student, "form": StudentForm, "label": "Students"},
    "trips": {"model": Trip, "form": TripForm, "label": "Trips"},
}


def get_resource(resource):
    try:
        return CRUD_RESOURCES[resource]
    except KeyError as error:
        raise Http404("Unknown management resource.") from error


@never_cache
@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
@require_GET
def management_home(request):
    resources = [
        {"key": key, "label": config["label"], "count": config["model"].objects.count()}
        for key, config in CRUD_RESOURCES.items()
    ]
    return JsonResponse({"resources": resources})


def _record_data(record, form_class):
    fields = form_class.Meta.fields
    data = model_to_dict(record, fields=fields)
    for field in record._meta.many_to_many:
        if field.name in data:
            data[field.name] = [related.pk for related in data[field.name]]
    return {"id": record.pk, **data}


def _form_fields(form):
    field_types = {forms.DateField: "date", forms.TimeField: "time", forms.IntegerField: "number"}
    fields = []
    for name, field in form.fields.items():
        info = {
            "name": name,
            "label": field.label,
            "required": field.required,
            "type": field_types.get(type(field), "text"),
            "value": form[name].value(),
        }
        if isinstance(field, forms.ChoiceField):
            info["choices"] = [{"value": str(value), "label": str(label)} for value, label in field.choices]
            info["multiple"] = field.widget.allow_multiple_selected
        fields.append(info)
    return fields


@never_cache
@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
@require_GET
def record_list(request, resource):
    config = get_resource(resource)
    records = config["model"].objects.all()
    return JsonResponse({"records": [_record_data(record, config["form"]) for record in records]})


@never_cache
@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
@require_http_methods(["GET", "POST"])
def record_create(request, resource):
    form_class = get_resource(resource)["form"]
    if request.method == "GET":
        return JsonResponse({"fields": form_class.Meta.fields, "form": _form_fields(form_class())})
    form = form_class(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    return JsonResponse(_record_data(form.save(), form_class), status=201)


@never_cache
@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
@require_http_methods(["GET", "POST"])
def record_update(request, resource, pk):
    config = get_resource(resource)
    record = get_object_or_404(config["model"], pk=pk)
    form_class = config["form"]
    if request.method == "GET":
        return JsonResponse({
            **_record_data(record, form_class),
            "form": _form_fields(form_class(instance=record)),
        })
    form = form_class(request.POST, instance=record)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    return JsonResponse(_record_data(form.save(), form_class))


@never_cache
@login_required
@permission_required("bus_tracker_app.manage_operational_data", raise_exception=True)
@require_POST
def record_delete(request, resource, pk):
    config = get_resource(resource)
    record = get_object_or_404(config["model"], pk=pk)
    try:
        record.delete()
    except ProtectedError:
        return JsonResponse({"error": "record_in_use"}, status=409)
    return JsonResponse({"deleted": True})
