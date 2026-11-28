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

## Assignment 2 static interface

For a fresh local volume, generate three separate passwords in a Compose environment
file from the repository root. If you already have a local SQL Server volume,
put its existing SA and service login passwords in this file.

```bash
(
  umask 077
  set -C
  sa_password=$(openssl rand -hex 24) &&
    attendance_password=$(openssl rand -hex 24) &&
    trip_ops_password=$(openssl rand -hex 24) &&
    printf 'MSSQL_SA_PASSWORD=Local1-%s\nATTENDANCE_SQL_PASSWORD=Local1-%s\nTRIP_OPS_SQL_PASSWORD=Local1-%s\n' \
      "$sa_password" "$attendance_password" "$trip_ops_password" > .env.compose
)
docker compose --env-file .env.compose up --build
```

The one-off `sql-init` service waits for SQL Server, then creates any missing local
databases, logins and database users. Each Django service runs its migrations
after initialization. The initializer preserves existing databases and passwords.
Service passwords use letters, digits, underscores or hyphens.

Open [SchoolRun on localhost](http://localhost:8080).
Nginx serves the static files in `ui/`, and `ui/config.js` points the browser at Trip
Operations on port 8002 and Attendance on port 8001. Sign in with an existing
SchoolRun account from the Trip Operations database.

The services accept browser API calls from the configured `UI_ORIGIN`. Compose
sets it to `http://localhost:8080` by default. The browser keeps its session token in
memory and sends it in the Authorization header. Attendance forwards it to Trip
Operations to verify the caller and trip context. Refreshing the page requires
signing in again.

## Assignment 2 CI checks

On pushes and pull requests, CI lints both services with Ruff and runs each Django
suite against its own disposable SQL Server container. Both suites must pass and
reach at least 70% line coverage in their application packages. The tests include
the Attendance-to-Trip Operations request with Trip Operations stubbed. Test
containers use a private Docker network and generate their own SQL credentials.

CI also validates the root system description and both OpenAPI documents before
building the images. To run the contract checks locally, use a Python virtual
environment and run these commands from the repository root.

```bash
python -m pip install PyYAML==6.0.3 jsonschema==4.26.0 openapi-spec-validator==0.9.0
python .github/validate-system.py
```

To reproduce the Attendance checks from the repository root:

```bash
python -m ruff check --isolated --select E4,E7,E9,F services/attendance
docker build -t schoolrun-attendance services/attendance
bash .github/test-with-sql-server.sh attendance
```

For Trip Operations, use `trip-ops` in place of `attendance`. The lint command
uses Ruff 0.17.6. The SQL test command installs coverage.py inside a temporary
image based on the service image.

## Assignment 2 Azure deployment

The GitHub Actions workflow builds both Django services. A push to `main` publishes both images to GHCR with the commit SHA, then deploys that SHA to the existing Azure Container Apps. Each container applies its committed migrations on startup, then starts Gunicorn on port 8000 with one worker and two threads. Gunicorn writes the method, path, status and duration for each request to stdout. Each app reports its own database status and deployed SHA at `/health`.

The workflow reads the public website origin from the Azure Storage account and sets it as `UI_ORIGIN` on both services. After they pass their health checks, it generates a `config.js` with their HTTPS URLs and uploads `ui/` to the Storage account's `$web` container. The site is served at the Storage account's **Static website → Primary endpoint**.

Configure these values under **Settings → Secrets and variables → Actions** in GitHub.

| Type | Name | Value |
| --- | --- | --- |
| Variable | `PREFIX` | `sdiez-ieu2024` |
| Variable | `RESOURCE_GROUP` | `rg-sdiez-ieu2024` |
| Variable | `UI_STORAGE` | `sdiezieu2024ui` |
| Secret | `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Client and tenant IDs for the Azure deployment identity and the Azure subscription ID |
| Secret | `ATTENDANCE_DATABASE_URL`, `TRIP_OPS_DATABASE_URL` | Azure SQL connection URL for each service, using a dedicated database user with permissions to apply migrations and access app data |
| Secret | `ATTENDANCE_DJANGO_SECRET_KEY`, `TRIP_OPS_DJANGO_SECRET_KEY` | Separate random, stable Django secret keys |

Use `mssql://<user>:<password>@sdiez-ieu2024-sql.database.windows.net:1433/<database>` for the database URLs. Percent-encode special characters in the username and password. The database names are `sdiez-ieu2024-attendance-db` and `sdiez-ieu2024-trip-ops-db`.

The `sdiez-ieu2024-github` managed identity trusts this repository's `main` branch via OIDC and has Contributor access in `rg-sdiez-ieu2024`. Retrieve the three Azure IDs with the CLI.

```sh
az identity show --resource-group rg-sdiez-ieu2024 --name sdiez-ieu2024-github \
  --query '{AZURE_CLIENT_ID:clientId,AZURE_TENANT_ID:tenantId}' --output json
az account show --query '{AZURE_SUBSCRIPTION_ID:id}' --output json
```

Both GHCR packages, `schoolrun-attendance` and `schoolrun-trip_ops`, must allow anonymous pulls for the existing Container Apps to fetch their images.

Enable static website hosting on `sdiezieu2024ui` with `index.html` as the index document. Give the GitHub managed identity **Storage Blob Data Contributor** on that storage account so GitHub Actions can upload the files.
