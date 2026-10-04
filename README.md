# Software Development and Devops – Assignment 1

# **Sergio Díez López**

Github: [https\://github.com/sdl06/Sergio\_Diez\_SDD\_Assignment](https://github.com/sdl06/Sergio_Diez_SDD_Assignment)

1. # Project purpose and scope

**School bus services in Spain often give parents little visibility into arrival times.** This creates uncertainty for families with tight schedules and recurring questions for managers; many parents cannot drive their children to school instead.  
**Two account types use the system:**

- Bus monitor: prepares routes and trips, shares bus location, and records definitive attendance.  
- Parent: views the bus’s live location and stop ETA, and can report a child absent so the bus does not wait.

**The two core workflows are:**

- Live trip location sharing and parent access.  
- Parent absence reporting and monitor attendance verification.

Both depend on trip preparation by an assigned monitor or admin. Atomic creation prevents incomplete or ghost trips.  
**AI-assisted route creation and teacher alerts about bus-related lateness are outside this iteration; their lower time priority made them candidates for future work.**

2. # Installation and first use

With Python 3.12+, clone the submitted repository, enter its root, and run:  
\`\`\`sh  
python \-m venv .venv  
source .venv/bin/activate  
python \-m pip install \-r requirements.txt  
python bus\_tracker/manage.py start  
\`\`\`  
The start command applies committed migrations without prompts and serves frontend and backend on \`0.0.0.0\` at \`PORT\` (default \`8000\`), without a reloader. Open http\://127.0.0.1:8000/. It uses Django’s development/static-file server for local assessment; compiled Tailwind CSS is included, so no frontend build or separate start is needed.  
To change the port or persistent data directory:  
\`\`\`sh  
PORT=8080 DATA\_DIR=/absolute/path/to/data python bus\_tracker/manage.py start  
\`\`\`  
SQLite uses \`\$DATA\_DIR/db.sqlite3\` (default \`bus\_tracker/db.sqlite3\`); the directory is created automatically. A fresh database has schema but no accounts or records. Reusing the directory preserves data. Manual \`makemigrations\` and \`migrate\` are unnecessary.  
Optional account setup in another terminal using the same environment:  
\`\`\`sh  
python bus\_tracker/manage.py createsuperuser  
\`\`\`  
Use \`/django-admin/\` to create routes, stops, students, buses, and monitor/parent links. Pass the same custom \`DATA\_DIR\` to \`createsuperuser\` if used. Accounts are optional for startup.  
For traffic-aware ETA, export the separately supplied key before startup:  
\`\`\`sh  
export TOMTOM\_API\_KEY='\<key supplied separately with the submission\>'  
python bus\_tracker/manage.py start  
\`\`\`  
Alternatively, copy \`bus\_tracker/.env.example\` to \`bus\_tracker/.env\` and edit it locally. The key and \`.env\` file are optional: without the key, live ETA is unavailable, but other workflows work. Never commit the key.  
\`DJANGO\_SECRET\_KEY\`, \`DJANGO\_DEBUG\`, comma-separated \`DJANGO\_ALLOWED\_HOSTS\` and \`DJANGO\_CSRF\_TRUSTED\_ORIGINS\`, and \`SCHOOL\_TIME\_ZONE\` are configurable. Local defaults support assessment; on a remote host, use a private secret, disable debug, and allow its hostname. Exported variables override \`.env\`.  
Create users through /django-admin/. Monitors need the prepare\_trip, post\_trip\_location and record\_trip\_attendance permissions, plus a Monitor profile linking their account to a route. Parents need a ParentChildAccess record linking their account to each child. Neither account requires staff or superuser status.

To test and verify coverage:
python -m coverage run --rcfile=.coveragerc manage.py test bus_tracker_app.tests --testrunner bus_tracker_app.tests.runner.FileSQLiteRunner
python -m coverage report --rcfile=.coveragerc

3. # Models

Django was chosen for its established patterns and the developer’s familiarity. The app separates models, views, and templates; migrations store these models in SQLite:

- **Monitor:** name, assigned route (foreign key), and one-to-one app user. Protected deletion prevents orphaned dependencies.  
- **Student:** name, birth date, route, and stop. No class field is needed without teacher alerts. \`clean()\` rejects a stop whose route differs from the student’s.  
- **Route:** name; related records hold its other details.  
- **Trip:** a route instance linked to a route, bus, monitor, date, students, leg (morning/afternoon), status (prepared/active/completed), and timestamps. Related foreign keys protect deletion. Permissions are \`prepare\_trip\`, \`manage\_operational\_data\`, and \`post\_trip\_location\`. A uniqueness constraint prevents duplicate trips for a leg; \`clean()\` rejects a monitor assigned to the wrong route.  
- **Bus:** basic bus details, including capacity for operational planning.  
- **Stop:** descriptor, coordinates, assigned route, and arrival dates. Its constraint keeps each stop on one route.  
- **TripLocation:** location sample with observed/received timestamps, browser accuracy in metres, and sample ID for deduplication; times must be timezone-aware.  
- **ParentChildAccess:** parent user–student link, with a uniqueness constraint against duplicates.  
- **StudentAttendance:** a student’s present/absent status for a trip.  
- **AbsenceNotice:** a parent’s advance absence report for a trip; validation rejects a student on another route.

The app uses Django’s built-in user model because it already provides the required account features.

4. # Workflows

Five key workflows use Django views:

- **\`prepare\_trip\`:** An assigned monitor submits trip data by POST. Django’s \`is\_valid()\` checks types and \`clean()\` rules; invalid data returns 403\. One atomic transaction creates the trip and adds students, avoiding ghost trips.  
- **\`start\_trip\` and \`complete\_trip\`:** Admins and authorized monitors manage their trips. Atomic \`transition\_trip\` checks \`prepare\_trip\` permission, trip limits, valid next status, and the relevant timestamp. Attendance is recorded after start; completion requires a started trip and the same authorization checks.  
- **Location posting:** The assigned monitor can post only while the trip is active and the request contains JSON. Parsing validates latitude, longitude, accuracy, timezone-aware observation time, and sample UUID. Saving rechecks monitor authority and deduplicates by \`client\_sample\_id\`. Parents may read location only through a child linked by \`ParentChildAccess\` to the route.  
- **Parent ETA:** Only a parent linked through \`ParentChildAccess\` can view an active trip’s ETA. A cache-backed TomTom proxy stores the first estimate and compares subsequent location samples. It requests a new ETA only when elapsed time and distance moved justify one; otherwise it reuses the cached value to limit API calls.  
- **Attendance:** Before a prepared trip, a linked parent may report a child absent or leave them present provisionally, saving stop time. During an active trip, the assigned monitor or admin with \`record\_trip\_attendance\` records definitive present/absent status. The monitor’s observation is the source of truth and lets parents learn if a child missed the bus.

5. # Important decisions and alternatives

Apart from the decisions shown in [ADR.md](http://ADR.md), the developer has done certain key decisions in order to develop the webapp:

1. **Separate absence notices and attendance:** A parent’s “present” indication cannot prove the child boarded. Tracking children would be too intrusive for minors. Separate provisional notices and a definitive monitor ledger improve the record, though monitors still cannot know a child’s whereabouts off the bus.  
2. **Cache TomTom estimates:** Refreshing on every parent request risks rate limits and cost; a proxy alone would still repeat calls for children sharing a stop while the bus barely moves. Reusing a valid cached ETA reduces calls at modest memory cost.  
3. **Configure basic CRUD views:** Repeated CRUD code increases maintenance and error risk. Class-based views improved readability but still repeated setup, so a model configuration dictionary centralizes it. The developer accepted some indirection for less boilerplate and considered extension through configuration consistent with the open-closed principle.  
4. **Usage of the TomTom API**: recognized APIs like Google maps had very limited free plans and forced saving a credit/debit card (5,000 calls per month). Local map downloads were however, extremely heavy and unsuitable for an examiner to grade. The developer accepted not choosing industry standards and realism regarding traffic information, and decided to use a less recognized API, the TomTom API, which offered a more generous free tier of 20,000 calls, which is more suitable for a prototype phase.

# 6\. SMART goals, SDLC and AI usage reflection

SMART planning helped but was only partly successful:

| Element | Positives | Negatives |
| :---- | :---- | :---- |
| Specific | Trip preparation, location sharing, and attendance tasks gave the developer a clear path. | “Finish models” was vague; “finish initial schema” would have been clearer, and models later changed. |
| Measurable | A goal targeted 85% error coverage. | “Allow parents to get location” lacked a measurable acceptance criterion, especially for team work. |
| Achievable | Familiar Django patterns and external APIs made the goals feasible. | ETA, permissions, and browser failure handling expanded the original frontend plan. |
| Relevant | Tracking and attendance served parents and monitors and met the two-domain requirement. | Stakeholder interviews were absent, so real-world relevance was not validated within the assignment. |
| Time-bound | A Gantt chart helped maintain deadlines. | New ideas and concern that the submission was too thin disrupted the schedule, including cached ETA work. |

The SDLC was iterative and incremental: models, CRUD, tracking, and attendance were built and reviewed in stages. Most unit, integration, and end-to-end testing came late, exposing defects that required changes.

The developer led most design while Codex agents implemented much of it. This caused some unwanted Markdown files, tests, and changes to predetermined data, subsequently fixed by the developer, as seen in commits.
