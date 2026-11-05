---

name: testing-and-debugging
description: Debug defects systematically, reproduce failures, identify root causes, add focused regression tests, and verify fixes safely across Python, FastAPI, SQLAlchemy, Next.js and TypeScript projects.
license: MIT
compatibility: opencode
metadata:
  category: debugging
  stack: cross-stack
  version: "1.0.0"
orchestration:
  lead_for:
    - bug-fix
  support_for:
    - python-cleanup
    - database-issue
    - refactor
    - fastapi-feature
    - nextjs-feature
    - model-serving
  conflicts_with:
    - python-quality
---

# Testing and Debugging

Use this skill when investigating bugs, failing tests, incorrect behavior, flaky behavior, integration failures, runtime errors, regressions or unexpected production behavior.

The objective is to identify the real cause, apply the smallest safe fix and prove the fix with focused verification.

## Core Workflow

When fixing a bug:

1. Read the error, failing test, logs and relevant code.
2. Reproduce the failure whenever possible.
3. Identify the smallest failing path.
4. Separate the visible symptom from the underlying cause.
5. Form a specific hypothesis.
6. Gather evidence that supports or rejects the hypothesis.
7. Add or update a regression test.
8. Apply the smallest safe change.
9. Run focused verification.
10. Run broader checks if focused verification passes.
11. Report what was changed, what was tested and what remains unverified.

Do not begin by rewriting large sections of code.

## Repository Inspection

Before changing code, inspect the project’s existing setup.

Check:

* `AGENTS.md`
* `README`
* `pyproject.toml`
* `requirements.txt`
* `package.json`
* lockfiles
* test configuration
* CI configuration
* environment configuration
* relevant fixtures
* existing debugging or logging utilities

Use the repository’s existing commands and conventions.

Do not invent test commands, dependencies, modules or configuration.

## Reproduction

A reproduction should be:

* minimal
* deterministic where possible
* directly connected to the reported failure
* easy to rerun
* isolated from unrelated systems when practical

Capture:

* exact error
* input
* expected behavior
* actual behavior
* environment
* relevant version
* triggering conditions

Do not claim a bug is fixed without reproducing it first unless reproduction is impossible.

When reproduction is impossible, explain why and use the strongest available evidence.

## Root-Cause Analysis

Distinguish between:

* symptom
* trigger
* root cause
* contributing conditions

Example:

```text
Symptom:
Request returns HTTP 500.

Trigger:
Database connection closes during commit.

Root cause:
The failed SQLAlchemy session is reused without rollback or replacement.

Contributing condition:
The background task keeps a request-scoped session.
```

Do not fix only the visible symptom if the underlying defect remains.

## Hypothesis-Driven Debugging

For each likely cause:

1. State the hypothesis.
2. Identify evidence that would confirm it.
3. Check logs, state, code or tests.
4. Reject unsupported hypotheses.
5. Continue until one explanation matches the observed behavior.

Avoid making several speculative changes at once.

Change one important variable at a time where practical.

## Regression Tests

A bug fix should normally include a test that:

* fails before the fix
* passes after the fix
* covers the real trigger
* validates externally observable behavior
* avoids relying on implementation details
* remains deterministic

Regression tests should be as focused as possible.

Examples:

* API request returns correct status
* failed transaction is rolled back
* duplicate submission is rejected
* background job creates its own session
* stale request does not overwrite newer state
* timeout produces a controlled error
* malformed input is rejected
* race condition is prevented by a constraint or atomic update

Do not write a test that only confirms the new implementation exists.

## Test Scope

Run tests in this order:

1. Single failing test
2. Relevant test file
3. Related module or feature tests
4. Full test suite when appropriate
5. Lint, type checking and build checks

Examples:

```bash
pytest tests/test_service.py::test_failed_transaction_rolls_back -q
```

```bash
pytest tests/test_service.py -q
```

```bash
npm test -- assignment-form
```

```bash
npx playwright test tests/assignment-flow.spec.ts
```

Do not start with the full suite when a focused test can provide faster evidence.

## Python Debugging

Check for:

* incorrect exception handling
* mutable default arguments
* incorrect truthiness checks
* stale mutable state
* resource leaks
* wrong return types
* timezone issues
* generator exhaustion
* sync code inside async functions
* un-awaited coroutines
* swallowed exceptions
* incorrect context manager behavior
* retry loops without limits

Prefer traceback evidence over guesswork.

## FastAPI Debugging

Check:

* dependency execution
* request validation
* response model mismatch
* sync versus async route behavior
* request-scoped session lifetime
* background task lifecycle
* exception handler behavior
* middleware ordering
* streaming resource lifetime
* authentication and authorization
* status-code mismatch

When debugging API failures, verify both:

* service-layer behavior
* HTTP-level behavior

## SQLAlchemy and PostgreSQL Debugging

Check:

* failed session reused without rollback
* incorrect transaction boundary
* commit ownership
* broken connection handling
* connection pool exhaustion
* missing constraints
* lazy loading after session close
* N+1 queries
* ambiguous commit outcomes
* concurrency races
* tenant filters
* model and migration mismatch

After `OperationalError`, `IntegrityError`, failed flush or failed commit:

* inspect transaction state
* rollback where possible
* close or discard unusable sessions
* create a fresh session before retry
* retry only safe operations

Do not solve transaction bugs only by increasing pool size or adding retries.

## Async Debugging

Check:

* blocking operations inside async functions
* tasks created but not awaited
* cancellation handling
* unbounded concurrency
* race conditions
* stale results
* task exceptions never observed
* incorrect event-loop ownership
* synchronous clients used inside async paths

Do not add arbitrary sleeps to hide race conditions.

Use explicit synchronization, awaiting, events, locks or deterministic test controls.

## Next.js and React Debugging

Check:

* server and client component boundaries
* hydration mismatch
* stale closure
* incorrect effect dependencies
* missing effect cleanup
* duplicate requests
* race conditions between requests
* server-only code imported into client components
* caching behavior
* state derived incorrectly from props
* API contract mismatch
* browser-only APIs used during server rendering

Test loading, error, empty and success states.

## Network and External Services

Check:

* timeout configuration
* retry behavior
* response status handling
* malformed response data
* connection reuse
* authentication headers
* rate limits
* partial failures
* duplicate requests
* idempotency

Do not retry permanent failures.

Do not retry non-idempotent operations without protection.

## Flaky Tests

Treat flaky tests as defects.

Check for:

* timing assumptions
* shared state
* test order dependency
* uncontrolled randomness
* real network calls
* timezone dependency
* fixed ports
* leaked database state
* missing cleanup
* background work still running
* arbitrary sleeps

Prefer:

* deterministic clocks
* fixed random seeds
* isolated fixtures
* explicit events
* polling with bounded timeout
* proper cleanup
* controlled dependency injection

Do not simply increase sleep duration.

## Logging and Evidence

Use logs to confirm hypotheses.

Useful context includes:

* request ID
* user ID
* entity ID
* job ID
* operation name
* retry count
* status transition
* exception type
* duration

Do not log secrets or sensitive payloads.

Add temporary debug logging only when necessary and remove or reduce it after the issue is understood.

## Minimal Change Rule

The fix should:

* address the identified root cause
* avoid unrelated refactoring
* preserve existing public behavior
* avoid introducing new dependencies without need
* avoid weakening validation or typing
* include a regression test
* remain easy to review

Do not combine bug fixes with broad architectural cleanup unless the cleanup is required for correctness.

## Do Not

* Rewrite unrelated code.
* Disable tests to make the suite pass.
* Skip or delete failing tests without justification.
* Add arbitrary sleeps.
* Catch and ignore errors.
* Use broad exception handling to hide failures.
* Weaken types without justification.
* Increase timeouts without finding the cause.
* Add retries without checking idempotency.
* Change several unrelated variables at once.
* Claim success without running available checks.
* Claim a production issue is resolved solely because local tests pass.

## Verification

Use the repository’s configured tools.

Typical Python checks:

```bash
ruff check .
ruff format --check .
mypy .
pyright
pytest
```

Typical Next.js and TypeScript checks:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Run only commands that exist in the project.

When a command fails because of a pre-existing issue, separate that from failures introduced by the current change.

## Required Output

After debugging, report:

```text
Root cause:
The verified cause of the failure.

Fix:
The smallest change applied.

Regression test:
The test added or updated.

Verification:
Commands run and results.

Remaining uncertainty:
Anything that could not be reproduced or verified.
```

If no root cause was confirmed, say so explicitly.

Do not present a hypothesis as a confirmed cause.

## Completion Criteria

A debugging task is complete only when:

* the failure was reproduced or the reproduction limitation was explained
* the root cause was identified with evidence
* the fix targets the root cause
* a regression test exists where practical
* focused verification passes
* broader checks were run when appropriate
* no unrelated behavior was changed
* remaining uncertainty is disclosed
