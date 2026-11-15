from django import forms

from .models import Bus, Monitor, Route, Stop, Student, Trip
from .tracking.models import ParentChildAccess


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = ["route_name"]


class StopForm(forms.ModelForm):
    class Meta:
        model = Stop
        fields = ["descriptor", "assigned_route", "longitude", "latitude", "configured_leg1_arrival", "configured_leg2_arrival"]
        widgets = {
            "configured_leg1_arrival": forms.TimeInput(attrs={"type": "time"}),
            "configured_leg2_arrival": forms.TimeInput(attrs={"type": "time"}),
        }


class BusForm(forms.ModelForm):
    class Meta:
        model = Bus
        fields = ["license_plate", "capacity", "bus_model", "bus_contractor", "current_longitude"]


class MonitorForm(forms.ModelForm):
    class Meta:
        model = Monitor
        fields = ["name", "route", "user"]


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["name", "date_of_birth", "route", "assigned_stop"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ["route", "bus", "monitor", "date", "leg", "students"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "students": forms.CheckboxSelectMultiple(),
        }

    def clean(self):
        cleaned_data = super().clean()
        route = cleaned_data.get("route")
        monitor = cleaned_data.get("monitor")
        students = cleaned_data.get("students")

        if route and monitor and monitor.route_id != route.id:
            self.add_error("monitor", "The monitor must be assigned to the selected route.")
        if route and students and students.exclude(route=route).exists():
            self.add_error("students", "Every selected student must belong to the selected route.")
        return cleaned_data


class PrepareTripForm(forms.ModelForm):
    """Collect only choices needed to prepare a dated trip for a known route."""

    class Meta:
        model = Trip
        fields = ["bus", "monitor", "date", "leg"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, route, assigned_monitor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["monitor"].queryset = route.monitors.all()
        if assigned_monitor is not None:
            self.fields["monitor"].initial = assigned_monitor
            self.fields["monitor"].disabled = True


class ParentChildAccessForm(forms.ModelForm):
    class Meta:
        model = ParentChildAccess
        fields = ["user", "student"]
