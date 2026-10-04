"""Non-interactive, single-process startup for local assignment assessment."""

import os
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command


class Command(BaseCommand):
    help = "Apply migrations, then serve on 0.0.0.0:$PORT (default 8000)."
    # Migration checks belong after migrate, not before the database exists.
    requires_system_checks = []

    def handle(self, *args, **options):
        try:
            port = int(os.environ.get("PORT", "8000"))
        except ValueError as exc:
            raise CommandError("PORT must be an integer between 1 and 65535.") from exc
        if not 1 <= port <= 65535:
            raise CommandError("PORT must be an integer between 1 and 65535.")

        database = settings.DATABASES["default"]
        if database["ENGINE"] == "django.db.backends.sqlite3":
            Path(database["NAME"]).parent.mkdir(parents=True, exist_ok=True)

        call_command("migrate", interactive=False, stdout=self.stdout, stderr=self.stderr)
        # No reloader subprocess. Serve the committed CSS/JS even with DEBUG off.
        # This is an assessment server, not a production deployment server.
        call_command(
            "runserver", f"0.0.0.0:{port}", use_reloader=False, insecure=True,
            stdout=self.stdout, stderr=self.stderr,
        )
