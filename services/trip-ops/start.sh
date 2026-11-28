#!/bin/sh
set -e

SQL_STARTUP=1 python manage.py migrate --noinput
exec gunicorn trip_ops_project.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" --workers 1 --worker-class gthread --threads 2 \
  --access-logfile - \
  --access-logformat 'method=%(m)s path=%(U)s status=%(s)s duration_ms=%(M)s'
