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
