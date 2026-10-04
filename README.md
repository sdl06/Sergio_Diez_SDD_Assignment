# 1. Project purpose and Scope
**Problem**: School bus systems, in Spain, are technologically underdeveloped and lack processes in order to be transparent and well-suited for parents with tight schedules. For most parents, knowing when the school bus will arrive is a big unknown that leads to uncomfortable conversations with managers on a regular basis. The alternative would be for the parents to drive their children to school, but in most cases, lack the time to do so.
**Who uses it**: There are two types of accounts:
- Bus monitor → is in charge of bus location sharing, route preparation as well as the final attendance source of knowledge
- Parent → is able to see the live location (and ETA for the bus to reach the stop), and can mark their child absent so that the bus does not wait for them
**Which are the main workflows?**: The main workflows are the key implementations of the two domains of the project:
- Live location emission and reception in trips
- Attendance marking from parents and subsequent verification from bus monitors
They both step from the preparation of trips from the route monitor or admin, applied atomicly to avoid ghost routes
**What is deliberately outside the project’s scope?** The developer considered adding things like AI-assisted route creation, or the implementation of notifications to teachers when a student arrives late due to buses. However, given a low importance for time, decided to apply them in future iterations rather than in this current one. 

# 2. Installation and first use
With Python 3.12 or newer installed, clone the submitted repository and enter its folder. From the repository root, install dependencies and start:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python bus_tracker/manage.py start
```

The single startup command applies committed migrations without prompts, then serves frontend and backend on `0.0.0.0`, using `PORT` (default `8000`) with no reloader subprocess. Open http://127.0.0.1:8000/. This uses Django's development/static-file server for local assessment, not production hosting. No separate frontend build or startup is needed; compiled Tailwind CSS is included.

For a different port or persistent database directory, use environment variables:

```sh
PORT=8080 DATA_DIR=/absolute/path/to/data python bus_tracker/manage.py start
```

SQLite is stored at `$DATA_DIR/db.sqlite3`; the default is `bus_tracker/db.sqlite3`. The directory is created automatically. A fresh database has the migrated schema but no application records or accounts. Restarting with the same directory preserves data. No manual `makemigrations` or `migrate` step is required.

Optional first-use account setup, in another terminal with the same environment:

```sh
python bus_tracker/manage.py createsuperuser
```

Log into `/django-admin/` to create routes, stops, students, buses and monitor/parent account links. If you used a custom `DATA_DIR`, supply it to this command too. Account creation is optional setup, not a startup prerequisite.

To enable traffic-aware ETA, export the privately supplied key before startup:

```sh
export TOMTOM_API_KEY='<key supplied separately with the submission>'
python bus_tracker/manage.py start
```

Alternatively, copy `bus_tracker/.env.example` to `bus_tracker/.env` and edit it locally. Neither an `.env` file nor a TomTom key is required to start; without the key, live ETA is unavailable but other workflows remain usable. Never commit the real key.

`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` (comma-separated), `DJANGO_CSRF_TRUSTED_ORIGINS` (comma-separated) and `SCHOOL_TIME_ZONE` are also configurable through environment variables. Defaults support local assessment; set a private secret, disable debug and allow the actual hostname when assessing on a remote host. Exported variables override the optional `.env` file.

# 3. Models
The architecture of the app can be split into models, views and templates. The framework chosen was Django, since it is an industry standard, and I am comfortable with it.

The self-defined models, which are, through migrations, converted to SQLite rows, include the following:
- **Monitor**: defines a monitor. It includes their name, the route they have been assigned to through a foreign key, as well as their user in the app, as a one-to-one field, forcing that there’s only one user for each monitor. Deleting the monitor, in the case its dependencies haven’t been deleted, would lead to a protection block, forcing you to delete its dependencies to not lead to orphan relationships.
- **Student**: defines a student. It includes name, date of birth, route and assigned stop. For now, the class has not been defined due to deciding not to add teacher notifications. The Clean function introduces a validation error when the route ID of the student’s assigned stop is different to the student’s route ID
Route: defines a route. Given how the route is filled with foreign keys with it, it only includes the name of the route. 
- **Trip**: it defines an instance of a route. It has a foreign key with the route, the bus and the assigned monitor for said trip. They have a protected deletion clause. Essential information like the date, leg (constrained between morning and afternoon), status (prepared, active, completed) time stamps and students are added. The model has three permissions: prepare_trip, manage_operational_data and post_trip_location and a unique constraint to make sure that there is one unique trip per leg. The trip’s respective clean function also raises a validation error when the monitor is on the wrong trip.
- **Bus**: It includes basic information about buses different trips use. This model is useful since it allows the person in charge to see the capacity of each different bus
- **Stop**: it includes data for each of the bus stops, such as their location (longitude + latitude), descriptor, assigned route and arrival dates. It has a unique constraint that limits the amount of routes where the stop is used to one.
- **TripLocation**: It shows an iteration of the live location of the trip. It has observed and received times, location and its browser-reported accuracy, in meters. It lastly includes a sample id to avoid duplicates, as well as the enforcement of a time zone.
- **ParentChildAccess**: Is it a many to many field that marks links between users (parents) and the students themselves. There is a unique constraint that bars duplicated parent-student links.
- **StudentAttendance**: it is a class that marks whether the student is present or absent in a given trip.
- **AbsenceNotice**: it is a class that marks when the parents prematurely announce the absence of their child in a given trip. A validation error is called when a student is reported absent in a route that is not theirs.
As the reader may notice, there is no self-defined user model. This is so because the developer used Django’s included user model. This is so since it already had the necessary implementations for the author to use it as is.
# 4. Workflows
Five key workflows, supported by django views, are the following:
- **prepare_trip**: A monitor assigned to the respective route can call this view. A post request ingests HTML form trip data, and then, is_valid runs Django’s validation pipeline, checking the conditions defined in the clean method, as well as correct types. After ensuring correct form (else it returns a 403), an atomic transaction is used to create the respective trip and add students, in order to avoid the creation of ghost trips.
- **Start_trip and complete_trip**: anyone allowed to prepare trips can manage operational data. Those are, admins and monitors in their respective trips. If the current status allows trip beginning, it first runs, atomically, transition_trip, which checks if the user has prepare_trip permission, limits trips, changes only to the valid next transition, and sets the corresponding timestamp. Then, the monitor is allowed to mark attendance. After completing it, the process is the same, running transition_trip to see if the monitor has the permission to change the status, and then change it if the trip has actually begun.
- **Location posting**: Monitors of respective trips are the ones who operate setters, whereas parents with ParentChildAccess connected to a child in a bus route can use getters. In order for the location of the bus to get posted, it first checks whether the person doing the request is actually the monitor, the trip is active and the content is json, for increased security and coherence. It then takes the raw request body and produces validated python values. It turns latitude, longitude, accuracy, observation time and sample UUID, checks requirements (date/time with timezone, accuracy, valid UUID) and returns a dictionary. Save sample one checks that the monitor of the trip is actually requesting it, checks overlapping posts with client_sample_id and it then gets returned
- **Parent ETA view – authorized live info**: Parents with the ParentChildAccess class are the only ones able to get the ETA of a bus. In order to allow parents to know the ETA, the Tomtom API, as well as a cache-powered proxy is used. The ETA calls for each route are stored in a cache, with the first one being stored regardless. It first gets the child and the trip, ensuring that the trip is active, and there is a prior sample to compare the data with (if there isn’t, one is created straight away). It then calculates the distance moved between the prior sample and the current one, and based on the time and the distance moved, a new ETA may be requested and added to the cache. If not, in order to avoid expensive calls, no action is taken. 
- **Parent access and monitor attendance views**: parents with a ParentChildAccess record can mark the student provisionally present or absent, whereas monitors with record_trip_attendance are the only ones able to modify the definitive ledger for each trip. In this app, the final source of truth regarding a student's presence in a bus trip, rather than the parents’ inference and trust, is the monitor’s observation. That way, if the child misses (or decides not to take) the bus, the parents will know it straight away. Firstly, before the trip (prepared status), the parent either keeps their child as present, or they can mark him absent, saving the bus idle time. Whenever the trip is active, the monitor marks children either present or absent. The monitor of the assigned route and app admins are the only people with the permissions to modify such ledger.

# 5. Important decisions and alternatives
Apart from the decisions shown in ADR.md, the developer has done certain key decisions in order to develop the webapp:
- **Separate parent absence notices from monitor attendance**: during the development of the attendance, the developer came through the realization of the app not being bus-skipping proof. That means that, if the parent marked their child present, there was the chance of the child actually skipping the bus and no one knowing anything. Live location from children would have made sense, but it was way too intrusive, given how the developer is dealing with sensitive information of minors. The alternative implemented is a double attendance ledger, which despite the limitation of monitors not knowing where children are, allows a better-recorded attendance list.
- **Caching TomTom estimates instead of requesting one on every parent refresh**: during the development of the ETA implementation, the developer encountered an issue: parents refreshing location all the time would lead to problems regarding calling and rate limits, leading to unnecessary spending. One alternative was just to implement a proxy; however, each parent could trigger another tomtom request if then, even when several children share the same stop and the bus barely moved. Implementing a cache could allow the recycling of the prior ETA value as long as it is useful, despite the added memory overhead.
- **The use of a configuration dictionary for basic CRUD views**: During the start of the views development, the developer found out that CRUD would occupy an excessive amount of boilerplate code, leading to a higher chance of error and a messier codebase. The only alternative was the use of class-based views, which allowed easier readability. However, that led to a high amount of repetition, leading to the creation of a configuration dictionary, adding each of the models in it (it may seem like it breaks the open-closed principle, but it doesn’t since extension is done through configuration). That way, the developer was willing to accept some indirection while removing repetition, a trade-off they deemed as valid.
# 6. SMART goals, SDLC, and AI usage reflection
The development of SMART goals was rather partial. Below, a table with each of the elements can be found:

| Element | Positives | Negatives |
| Specific | Tasks identify certain things like trip preparation, location sharing and attendance marking, creating a track for the developer to follow. | Some tasks in the developer’s personal checklist were rather generic “finish models” (which should have been “finish initial schema implementation”) was added, and models were subsequently modified. |
| Measurable | The developer measured things like error coverage in the SMART goals, targeting for 85%. | Some goals were too qualitative for them to be measurable. For instance, “allow parents to get location” could have many different interpretations. It’s not that bad for a solo developer, but working in a team, it’s a habit that shouldn’t be repeated. |
| Achievable | The developer came up with goals that were rather easy to implement, and if something looked hard, he implemented the easiest yet correct path (eg. choosing a framework the developer is comfortable with, external APIs…). | Some aspects were added beyond the initial plan, like ETA, permissions, and browser failure handling, expanding the initial frontend plan. |
| Relevant | Tracking and attendance directly support parents and monitors and satisfy the two-domain requirement. | Criticism behind relevance may include not interviewing stakeholders to see if the implementation solved actually relevant problems, but that is beyond the scope of this assignment.
| Time-bound | The developer implemented a gantt chart to stay on task, leading to discipline regarding deadlines. | The gantt chart discipline was at times broken, due to ideas coming in, and a subsequent realization of the submission being too thin, leading to the implementation of cached ETA. |



Regarding the SDLC, the process was iterative and incremental: models, CRUD, tracking and attendance were implemented and reviewed in stages. Most automated unit, integration and E2E testing was concentrated towards the end, revealing defects that required further implementation changes.

When it comes to AI usage, the developer focused on most of the design, and AI agents (deployed through Codex, respectively), focused on the implementation of most of the design. This approach gave issues in some cases, like the creation of md files for no reason, testing files when undesired and certain modifications involving predetermined data.
