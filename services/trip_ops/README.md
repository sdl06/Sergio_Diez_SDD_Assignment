# SchoolRun Trip Operations

Trip Operations owns routes, stops, buses, monitors, student records, trips and their rosters, parent access links, GPS samples, and ETAs. It also owns the local Django accounts and permissions used for these workflows.

Run it from this directory with Python 3.12 or later and an active virtual environment:

```sh
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8002
```

Open http://127.0.0.1:8002/. Use `/django-admin/` for accounts and permissions and `/manage/` for operational records and parent access links. Give monitors the **Can prepare trips** and **Can post trip locations** permissions and link their accounts to the corresponding monitor profiles. Parents use accounts linked to their children.

The initial migration starts an empty SQLite database at `services/trip_ops/db.sqlite3`. To use another directory, set `TRIP_OPS_DATA_DIR` to a directory reserved for this project. Assignment 1 records have not been imported.

Optional settings are listed in `.env.example`. Supply your own `TOMTOM_API_KEY` to enable traffic estimates. Set a private `DJANGO_SECRET_KEY` locally if sessions should survive a server restart. The local pages exercise trip preparation, lifecycle changes, monitor GPS sharing, and parent tracking. Attendance and absence notices belong to the separate Attendance project.

Run the extracted tests with a disposable file-backed SQLite database:

```sh
python manage.py test --testrunner bus_tracker_app.tests.runner.FileSQLiteRunner
```
