"""Startup orchestration checks; the real server is smoke-tested separately."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings


class StartupTests(SimpleTestCase):
    def invoke(self, port=None):
        environment = os.environ.copy()
        environment.pop("PORT", None)
        if port is not None:
            environment["PORT"] = port
        with patch.dict(os.environ, environment, clear=True):
            call_command("start")

    @patch("bus_tracker_app.management.commands.start.call_command")
    def test_default_port_migrates_before_single_process_server(self, dispatch):
        self.invoke()
        self.assertEqual([call.args[0] for call in dispatch.call_args_list], ["migrate", "runserver"])
        self.assertIs(dispatch.call_args_list[0].kwargs["interactive"], False)
        server = dispatch.call_args_list[1]
        self.assertEqual(server.args, ("runserver", "0.0.0.0:8000"))
        self.assertIs(server.kwargs["use_reloader"], False)
        self.assertIs(server.kwargs["insecure"], True)

    @patch("bus_tracker_app.management.commands.start.call_command")
    def test_configured_port_and_missing_database_directory(self, dispatch):
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "new-data" / "db.sqlite3"
            with override_settings(DATABASES={"default": {
                "ENGINE": "django.db.backends.sqlite3", "NAME": database_path,
            }}):
                self.invoke("8123")
            self.assertTrue(database_path.parent.is_dir())
        self.assertEqual(dispatch.call_args.args[1], "0.0.0.0:8123")

    @patch("bus_tracker_app.management.commands.start.call_command")
    def test_invalid_ports_fail_before_migration(self, dispatch):
        for port in ("abc", "", "0", "-1", "65536"):
            with self.subTest(port=port), self.assertRaisesMessage(CommandError, "PORT must"):
                self.invoke(port)
        dispatch.assert_not_called()

    @patch("bus_tracker_app.management.commands.start.call_command")
    def test_failed_migration_does_not_start_server(self, dispatch):
        dispatch.side_effect = CommandError("Migration failed")
        with self.assertRaisesMessage(CommandError, "Migration failed"):
            self.invoke()
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.args[0], "migrate")
