# SchoolRun attendance

This Django project owns two domain tables. `AbsenceNotice` stores a parent's notice and `StudentAttendance` stores the monitor's definitive observation. Both store `trip_id` and `student_id` as integer references and enforce one row per trip and student in each table. Actor IDs are integer references too.

The attendance rules need a verified caller, trip state, and roster. Tests provide those facts as a `TripContext`. The running project returns HTTP 503 for requests requiring that context until a source for it is wired in. It does not accept identity, roster, or authorization facts supplied by the browser.

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
