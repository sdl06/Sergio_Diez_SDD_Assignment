## [1]. <Backend framework choice>
Date: 2026-09-17
Status: Decided
Context: In order to build the app, to ease up the process by not having to manually write functions for modelling, urls..., a framework is usually chosen. It was my case.
Decision: 1-2 sentences, what you chose: I chose Django, which, despite being rather complex, it is the framework I am most familiar with. I have been using it for around 2 years, whereas if I wanted ot use any other framework, I would have had to learn it from scratch.
Alternatives considered: one real alternative was fastapi. I am mildly familiar with it, and is easier for some cases. However, I do not feel confident enough to use FastAPI for a school project
Consequences: this enables confident, quick building rather than unconfident building where I would have had to learn an unknown framework or gain additional confidence with an existing one.


## [2]. <Feature domain scoping for independent modularization>
Date: 2026-09-17
Status: Decided
Context: Two feature domains need to be added. In order to improve organization, given the scope of the project, there can be multiple choices. I have added, as candidates, given the clauses of the assignment, 2 separate django apps and 2 modules under a core app
Decision: I chose 2 modules under a core app, since the main pro, convenience, outweights the cons, given the scope of the assignment
Alternatives considered: I considered 2 django apps (one for the map, and one for attendance), but it was overkill given the size of the app
Consequences: The main consequences are the loss of stronger framework-level modular packages, explicit ownershipp and ceremony, but given the size of the app, those three barely affect the project, making the pro of convenience outweigh the cons


## [3]. <A data-model/schema decision in SQLite>
Date: 2026-09-27
Status: Decided
Context: When deciding location updates, I was checking out the models, and figured out that in order to implement the location updates, the model was not suitable enough given loss of information, and possible inefficiencies.
Decision: I decided to create a whole new model for the location updates, that having Trip as a foreign key.
Alternatives considered: I considered things like adding an array as a data structure for the model. However, that led to the breach of the first normal form, given the lack of atomicity there is in array. Another choice was to pretty much do nothing about it, but that led to overwriting information, which would have led to the loss of meaningful data in emergency cases.
Consequences: This change gives many upsides, such as higher database efficiency and a new, meaningful feature, which is to look for past location updates. It only adds additional schema complexity, but in this case, the pros are well-off compared with the cons.

## [4]. <Testing approach decision>
Date: 2026-10-03
Status: Decided
Context: When deciding testing, I considered three things:
- Edge cases. To implement them, I focused on edge cases, and cases that didn't follow permissions. Those include, for instance, parents of other children, misplaced monitors or impossible calendar dates.
- Integration testing with the Tomtom API, ensuring commands and CRUD work in a timely manner, given location updates and ETA proxies
- E2E testing to ensure proper frontend-backend connection
Decision: the implementation of 65 unit tests, 8 integration tests, and 8 E2E tests in order to ensure a correct implementation given different edge cases
Alternatives I considered: Testing is a pretty straight forward process, so none really. The other alternatives I have thought about are being more lenient with test cases, but that would have been counterproductive in the long term. For this webapp app, also, I decided to not simulate cases where thousands of people joined simultaneously, due to a limited API calls plan
Consequences: This approach towards testing gives upsides, ensuring a more robust functionality on paper, rather than a constant iteration where things could be missed out more easily. It also allows savings, since it won't be tested in a production-looking system, for now

## [5]. <Intentional omission>
Date: 2026-10-04
Status: Decided
Context: One key part of the original idea was for teachers to know which students were to be absent due to school bus delays. However, given the 2 domain limit, it was one of the trim-down candidates.
Decision: I ended up getting rid of it, since despite it would have been pivottal from teachers, it diverged excessively from the core implementation of the project. There were other dropped features like AI-powered route generation given student residence clusters.
Alternatives I considered: I was thinking about getting rid of parent tracking altogether, but decided not to since parents are the main stakeholder regarding the product and doing so would have led to an inconsistent value proposition
Consequences: Teachers are currently unable to know whether a student will be late. However, if future versions get released, it would be a priority feature.

## [6]. <The split>
Date: 2026-11-11
Status: Decided
Context: I have to split the domains and core data and functions into 2 different services. The catch is that there will be a service that has to deal with core data. In order to ensure data ownership, 3 different services would have been ideal, but given the project specification, it's banned.
Decision: I decided to split the data in 2 microservices:
- **Trip Operations**, which would include routes, stops, buses, monitors, students, trips and trip assignments; location samples, ETAs and parent access.
- **Attendance**: would include absence notices and definitve attendance records, storing trip and student IDs as reference srather than cross-database foreign keys.
Alternatives I considered: An alternative would have been to add the core information (students, routes, stops...) in attendance. However, that would have gotten rid of data locality, due to constant http data movement due to tracking updating bus location. The proximity to the domain is also key, since most of the core models are trip operations models.
Consequences: when filling up attendance, due to the loose coupling of the attendance service to the trip operations service, the process may have more latency, due to HTTP communications being required to fill out the attendance form.
## [7]. <Data and migrations>
Date: 2026-11-17
Status: Decided
Context: I have to decide what data goes into what SQL database. In the app, there is a clear intersection regarding overlapping databases, StudentAttendance. Also, most views within attendance, implicitly need data from the trip operations service. Thus, we need to decide how data should be divided and how the migration to each of the databases will be done
Decision: Firstly, I decided to get rid of all foreign keys of fields that reference ones outside the database. AI did that during the split, and the decision made is sound. The division of the databases is consistent with the division of concerns: trip operations would manage students and buses, as well as assigning students to rosters; attendance owns the facts it creates, whether a parent reported an absence and whether a monitor marked a student present or absent.
The Attendance database can no longer enforce foreign keys to students and trips in Trip Operations. Attendance stores their IDs and checks roster membership and the caller’s permission with Trip Operations before writing. The check reflects the state at the time of the request. Automatic cascades across the two databases are lost.
Alternatives I considered: I considered using WebSockets for Attendance to check trip details with Trip Operations. Each attendance action needs one answer about the trip’s current state, roster, and permissions. An HTTP request gives that answer with a timeout and a status code. WebSockets would add a persistent connection and reconnect logic for a workflow that has no need for live updates. I chose HTTP on the local Compose network and HTTPS in Azure to encrypt the caller’s credentials and roster data in transit.
Consequences: there are no unneeded persistent connection, given the developer me not using websockets. However, errors can be routed due to HTTP returning a status code. Given the lack of foreign keys and the use of HTTP communications, calls will be slower due to networking requests, something admissible since there isn't really an alternative apart from undesired (and in this assignemnt, illegal given the means) tighter coupling.
## [8]. <Serverless Azure hosting>
Date: 2026-11-19
Status: Decided
Context: I have to choose how to host SchoolRun on Azure while keeping costs within my Azure for Students allowance. The assignment and the professor's updated deployment guide constrain the services I can use and require the backend to scale to zero when idle.
Decision: I chose France Central because it is an allowed European region near Madrid, where I am based. In my resource group, I created one logical SQL server with separate serverless databases for Attendance and Trip Operations, using the free database offer to limit costs. Each service will use credentials that only grant access to its own database.
I chose Azure Container Apps on the Consumption plan, with one Container App per service in a shared environment and minimum 0 and maximum 1 replica per app. I will host the frontend as an Azure Storage static website, following the updated deployment guide, and publish the backend images to GHCR. I will document the initial setup commands in the README and use GitHub Actions to deploy subsequent changes and supply configuration and secrets.
At 100 times the traffic, I would measure response times, SQL load and TomTom usage before increasing capacity. I would reconsider the replica limit and database capacity and auto-pause settings, review session handling across replicas, and ensure migration execution is coordinated during deployments. These changes would trade higher cost and operational complexity for increased throughput and availability.
Alternatives considered: West Europe was another possible region, but I chose to keep the resources together in France Central. Azure Container Registry would provide an Azure-hosted registry, but GHCR fits the existing GitHub workflow without adding a fixed registry cost. Bicep or Terraform would make infrastructure easier to recreate and compare, but I chose documented Azure CLI commands because I can understand and maintain them within the assignment's scope. Keeping containers running would reduce startup delays, but the assignment requires scale-to-zero and the app does not need continuous compute while unused.
Consequences: Container Apps can stop their replicas while idle, and the SQL databases can auto-pause. The first request may therefore be slow or temporarily fail while the container starts and SQL resumes. I will add bounded database connection retries with backoff, allow enough time in startup and deployment health checks, and make the UI explain startup delays. Each service's health endpoint will check its own database independently of the other service.
Database records will persist outside the containers, so replacing an image will preserve them. Each service will apply pending migrations before starting its server and stop startup if a migration fails. The one-replica limit bounds normal scaling, but old and new revisions can overlap during deployment, so it does not guarantee that migrations can never run concurrently. The SQL free offer also imposes a monthly allowance: with AutoPause selected, exhausting it makes the database unavailable until the allowance resets. Storage and active container usage can still consume subscription credit.

## [9]. <Pipeline and Testing>
Date: 2026-11-27
Status: Decided
Context: For this deployment, we are using an automated CI/CD pipeline. This should entail that said pipeline ensures both functional and safe deployments. This entails adding blockers when there's issues regarding performance, linting, or service initialization. Testing should also be done in order to ensure all tests work out as intended.
Decision: the CI gates I decided to implement are Ruff, critical security issues through SAST and SCA, and a 70% minimum coverage per service. All those should pass before deployment. Tests use a disposable SQL server so they  exercise the same DB engine as azure without touching deployed data. Regarding cross-service testing, attendance makes its normal request through a stubbed trip operations transport. The test checks what attendance sends and how it handles the reploy. WHhen it comes to scope, live tomtom api calls stay opt-in. The stubbed test covers attendance's side of the integration. The previously added browser smoke test exercises the two running services together.
Alternatives considered: Firstly, I considered running the tests on sqlite for faster deployment and removing the need to start a db container. I chose a disposable sql server since azure uses the same db engine, and the concurrency tests already exposed a difference in how sql server locks rows. Secondly, a compose integration test would catch real networking and config problems, including a wrong service url. I chose to stub trip operations in the attendance suite so I could reliably test successful replies, denied requests and timeouts. I tested the full browser flow separately with both services running. Lastly, I could have made every semgrep finding blocking, enforcing a stricter policy. However, it would also block deployments on lower-priority findings. I chose a small blocking set for request data reaching shell execution, SQL or unsafe deserialization. The broader scan stays advisory so those findings are still visible.
Consequences: My choices have tradeoffs, including the leak of non-critical security issues, and the usage of an SQL server will mean a slower deployment. This means that the swiftness gained with the more lenient security checks is lost with the real SQL server. Also, using a stubbed trip operations can lead to the non-catching of several networking problems.
