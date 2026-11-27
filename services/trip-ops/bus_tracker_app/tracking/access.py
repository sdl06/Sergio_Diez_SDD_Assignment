"""Child visibility for parent and operational administrator read workflows."""
from ..models import Student


def visible_children(user):
    children = Student.objects.select_related("assigned_stop")
    if not user.is_authenticated:
        return children.none()
    if user.has_perm("bus_tracker_app.manage_operational_data"):
        return children
    return children.filter(parent_accesses__user=user)
