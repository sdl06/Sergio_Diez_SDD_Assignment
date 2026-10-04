"""Use a disposable, file-backed SQLite database for realistic locking tests."""
from tempfile import TemporaryDirectory
from pathlib import Path

from django.db import connections
from django.test.runner import DiscoverRunner


class FileSQLiteRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        self.sqlite_directory = TemporaryDirectory(prefix="schoolrun-test-")
        database = connections["default"]
        if database.vendor != "sqlite":
            self.sqlite_directory.cleanup()
            raise RuntimeError("FileSQLiteRunner is intended for this project's SQLite tests.")
        self.original_test_name = database.settings_dict["TEST"].get("NAME")
        database.settings_dict["TEST"]["NAME"] = str(Path(self.sqlite_directory.name) / "test.sqlite3")
        try:
            return super().setup_databases(**kwargs)
        except Exception:
            database.settings_dict["TEST"]["NAME"] = self.original_test_name
            self.sqlite_directory.cleanup()
            raise

    def teardown_databases(self, old_config, **kwargs):
        try:
            super().teardown_databases(old_config, **kwargs)
        finally:
            connections["default"].settings_dict["TEST"]["NAME"] = self.original_test_name
            self.sqlite_directory.cleanup()
