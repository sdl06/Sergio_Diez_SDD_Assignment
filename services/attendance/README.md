# SchoolRun attendance

This Django project owns two domain tables. `AbsenceNotice` stores a parent's notice and `StudentAttendance` stores the monitor's definitive observation. Both store `trip_id` and `student_id` as integer references and enforce one row per trip and student in each table. Actor IDs are integer references too.

Attendance fetches the caller, trip state, and scoped roster from Trip Operations. Set `TRIP_OPS_BASE_URL` to its URL (default `http://127.0.0.1:8002`, set by Compose on the container network). `TRIP_OPS_TIMEOUT_SECONDS` defaults to 3. If Trip Operations is unavailable, Attendance responds with HTTP 503 and leaves writes unsaved.

For local testing, use the same hostname for both services, such as `127.0.0.1` on ports 8001 and 8002. Log in to Trip Operations first and send its session cookie with Attendance requests. For POST, send the CSRF cookie and the refreshed `X-CSRFToken` returned by login. Attendance passes those credentials to Trip Operations for verification. A browser on another origin must be configured explicitly in Trip Operations' `DJANGO_CSRF_TRUSTED_ORIGINS`.

From this directory, with a Python 3.12+ virtual environment active:

```sh
python -m pip install -r requirements.txt
python manage.py test
python manage.py migrate
python manage.py runserver 127.0.0.1:8001
```

The initial migration is for a fresh local SQLite database. If you ran the earlier attendance draft, move its local `db.sqlite3` aside before running this migration. The Assignment 1 database is separate.

| Method | Path |
| --- | --- |
| GET, POST | `/api/children/<child_id>/trips/<trip_id>/absence/` |
| GET | `/api/trips/<trip_id>/attendance/` |
| POST | `/api/trips/<trip_id>/attendance/<student_id>/` |
