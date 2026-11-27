import logging
import os

from django.db import DatabaseError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_safe

from bus_tracker_app.models import DatabaseHealthCheck


logger = logging.getLogger(__name__)


@require_safe
def health(request):
    version = os.environ.get("APP_VERSION", "local")
    try:
        DatabaseHealthCheck.objects.update_or_create(
            pk=1,
            defaults={"checked_at": timezone.now()},
        )
    except DatabaseError:
        logger.warning("Database health check failed")
        return JsonResponse({"status": "unavailable", "db": "unavailable", "version": version}, status=503)

    return JsonResponse({"status": "ok", "db": "ok", "version": version})
