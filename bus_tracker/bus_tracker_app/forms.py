from django import forms

from .models import Bus, Monitor, Route, Stop, Student, StudentAttendance, Trip


class StyledModelForm(forms.ModelForm):
    """Keeps form presentation out of views while retaining Tailwind styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm shadow-sm outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-100",
            )


class RouteForm(StyledModelForm):
    class Meta:
        model = Route
        fields = ["route_name"]


class StopForm(StyledModelForm):
    class Meta:
        model = Stop
        fields = ["descriptor", "assigned_route", "longitude", "latitude", "configured_leg1_arrival", "configured_leg2_arrival"]
        widgets = {
            "configured_leg1_arrival": forms.TimeInput(attrs={"type": "time"}),
            "configured_leg2_arrival": forms.TimeInput(attrs={"type": "time"}),
        }


class BusForm(StyledModelForm):
    class Meta:
        model = Bus
        fields = ["license_plate", "capacity", "bus_model", "bus_contractor", "current_longitude"]


class MonitorForm(StyledModelForm):
    class Meta:
        model = Monitor
        fields = ["name", "route"]


class StudentForm(StyledModelForm):
    class Meta:
        model = Student
        fields = ["name", "date_of_birth", "route", "assigned_stop"]
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}


class TripForm(StyledModelForm):
    class Meta:
        model = Trip
        fields = ["route", "bus", "monitor", "date", "students"]
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


class StudentAttendanceForm(StyledModelForm):
    class Meta:
        model = StudentAttendance
        fields = ["student", "trip", "presence"]

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get("student")
        trip = cleaned_data.get("trip")
        if student and trip and not trip.students.filter(pk=student.pk).exists():
            self.add_error("student", "Assign the student to this trip before recording attendance.")
        return cleaned_data
