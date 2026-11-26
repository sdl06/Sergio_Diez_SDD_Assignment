import os
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or token_urlsafe(48)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in {"true", "1", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]
TRIP_OPS_BASE_URL = os.environ.get("TRIP_OPS_BASE_URL", "http://127.0.0.1:8002")
TRIP_OPS_TIMEOUT_SECONDS = float(os.environ.get("TRIP_OPS_TIMEOUT_SECONDS", "3"))
UI_ORIGIN = "https://sdiezieu2024ui.z28.web.core.windows.net"
CORS_ALLOWED_ORIGINS = [UI_ORIGIN] if UI_ORIGIN else []
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]
CORS_ALLOW_HEADERS = ["authorization", "content-type"]

INSTALLED_APPS = ["corsheaders", "bus_tracker_app"]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
]

ROOT_URLCONF = "attendance_project.urls"
WSGI_APPLICATION = "attendance_project.wsgi.application"

database_url = urlparse(os.environ["DATABASE_URL"])

DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "HOST": database_url.hostname,
        "PORT": database_url.port or 1433,
        "NAME": database_url.path.lstrip("/"),
        "USER": unquote(database_url.username or ""),
        "PASSWORD": unquote(database_url.password or ""),
        "OPTIONS": {
            "driver": "ODBC Driver 18 for SQL Server",
            "extra_params": os.environ.get(
                "SQL_EXTRA_PARAMS",
                "Encrypt=yes;TrustServerCertificate=no",
            ),
        },
    },
}

TIME_ZONE = "UTC"
USE_TZ = True
