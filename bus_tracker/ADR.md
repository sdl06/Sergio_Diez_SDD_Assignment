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


