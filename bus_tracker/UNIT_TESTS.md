# Testing approach for SchoolRun

Read this note when we begin the next testing phase. It records the agreed approach; it is not a claim that all of these tests already exist. Although this file is called `UNIT_TESTS.md`, the plan deliberately combines focused unit tests with Django request/database integration tests.

## Guiding principle

Test important rules and risks first, then test the complete request flow that should enforce them. Use coverage to find gaps, not as the sole measure of quality. A test should describe one **given → when → then** behavior and assert the result that matters, including database state after a write or a denied request.

## Layers to cover

1. **Model and form rules.** For each rule, test an accepted and a rejected case: a student's stop belongs to their route; a trip's monitor belongs to its route; an attendance record refers to a student assigned to its trip. Test form-specific choice restrictions separately from model validation. Remember that a direct model `save()` does not automatically call `full_clean()`.
2. **Permissions.** Build a small role matrix for sensitive views: anonymous user, signed-in user without permission, monitor assigned to the route, monitor assigned to another route, and admin. Check the response *and* that a denied POST did not create or alter records. Give trip preparation and management CRUD priority. Include a CSRF-enforcing client for security-sensitive POSTs because Django's normal test client does not enforce CSRF by default.
3. **Complete workflows.** Submit real forms through Django's test client and query the test database afterward. For trip preparation, verify the route, bus, monitor, date, and assigned students—not only the redirect. Submit the same route/date twice and verify that only one trip remains and the existing trip is not silently changed.
4. **Failures and boundaries.** Exercise unknown or malformed IDs, invalid fields, empty routes, protected deletion, and duplicate route/date submissions. Verify that errors are visible and that invalid requests leave the database unchanged.
5. **Presentation and browser behavior.** Keep a few tests for essential page content and navigation, but do not make wording or Tailwind classes the foundation of the suite. Test the draft trip-builder JavaScript separately when its behavior matters; browser validation must never replace server-side validation.

## Suggested organization

Separate tests by responsibility—for example, `ModelRuleTests`, `TripFormTests`, `TripPermissionTests`, and `TripPreparationWorkflowTests`. Create only the database records each scenario needs. Test-created records are isolated fixtures, not hard-coded production data. Prefer named helpers for repeated setup, while keeping each test's relevant inputs easy to see.

## Priority and review

Prioritize **permissions and database invariants**, then workflows, then presentation. Afterward, measure line and branch coverage for the application code, inspect the missed lines, and add tests only where they represent meaningful behavior. A defensible 70% with strong authorization and data-integrity checks is more valuable than a higher percentage driven mostly by page-load assertions.

The parent live-updates page and the visual trip-builder are currently placeholders/drafts. Do not write tests that pretend live location posting or parent-specific access control already exists. Revisit this note and extend the matrix when those features are implemented.
