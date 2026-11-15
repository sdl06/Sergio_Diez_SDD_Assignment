# SchoolRun Trip Operations

Trip Operations owns routes, stops, buses, monitors, student records, trips and their rosters, parent access links, GPS samples, and ETAs. It also owns the local Django accounts and permissions used for these workflows.

Run it from this directory with Python 3.12 or later and an active virtual environment:

```sh
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8002
```

Trip Operations serves backend routes at `http://127.0.0.1:8002`. The separate frontend can use these operations when its authentication is wired in.

- `GET /accounts/login/` returns a CSRF token. Keep the cookies and send the token as `X-CSRFToken` with a form-encoded `POST /accounts/login/` containing `username` and `password`. Keep the session cookie and use the refreshed token returned by login for subsequent POST requests. `POST /accounts/logout/` ends the session.
- `GET /manage/` lists operational resources. Use the routes under `/manage/<resource>/` to read, create, update, or delete records. Create and update accept form-encoded fields. Create monitor and parent accounts and assign permissions through Django's management shell. Link accounts through the monitor and parent access records.
- `GET /routes/<route_id>/prepare/` returns trip preparation options. Submit the chosen values as form data to `POST /routes/<route_id>/prepare/submit/`. Use `/trips/` and `/trips/<trip_id>/` to read trips, and POST to the trip's `start/` or `complete/` route to change its state.
- `GET /parents/live/` returns the caller's children and trips. Monitor GPS submissions and parent location and ETA reads are under `/api/`.

The initial migration starts an empty SQLite database at `services/trip_ops/db.sqlite3`. To use another directory, set `TRIP_OPS_DATA_DIR` to a directory reserved for this project. Assignment 1 records have not been imported.

Optional settings are listed in `.env.example`. Supply your own `TOMTOM_API_KEY` to enable traffic estimates. Set a private `DJANGO_SECRET_KEY` locally if sessions should survive a server restart. Attendance and absence notices belong to the separate Attendance project.

Run the extracted tests with a disposable file-backed SQLite database:

```sh
python manage.py test --testrunner bus_tracker_app.tests.runner.FileSQLiteRunner
```
