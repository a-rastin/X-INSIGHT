---
name: dev-testing
description: Testing phase guidance for adding and validating feature test coverage. Use when the user wants to write tests, update testing docs, run coverage, close coverage gaps, or run dev-lifecycle phase 8.
---

# Dev Testing

Run testing work for configured AI docs features. Before changing docs or code, propose the concrete plan for this phase and wait for user approval unless the user already approved the exact phase plan.

## Write Tests

1. Gather context: feature name, changes summary, environment, existing test suites, flaky tests to avoid.
2. Analyze the testing template, success criteria, edge cases, available mocks, and fixtures.
3. Add unit tests for happy paths, edge cases, and error handling for each module. Highlight missing branches.
4. Add integration tests for critical cross-component flows, setup/teardown, and boundary/failure cases.
5. Run coverage tooling, identify gaps, and suggest additional tests if below the target.
6. If task tracing is available, record evidence for each fresh test/coverage command per `task`.
7. Update the selected testing doc with test file links and results.