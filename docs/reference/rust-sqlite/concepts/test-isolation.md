---
title: "Test Isolation"
description: "Blocking invariant: tests must never call real external services"
type: invariant
severity: blocking
---

# Test Isolation

Tests — unit, integration, and exploratory — must never make real calls to external services. This is a **blocking** invariant: code that violates it does not ship.

## Rules

### 1. No real service calls in tests

Tests must never hit real APIs, databases-as-a-service, or any external system that costs money or has rate limits. All external dependencies are replaced with one of:

- **In-memory port mocks.** Stub adapters that implement the port trait against an in-process data structure (e.g., `InMemoryDatabase`, `TestClock`).
- **Pact replay recordings.** Captured trace files replayed deterministically (see [traces.md](traces.md) and [pact-record-replay.md](../architecture/pact-record-replay.md)).

### 2. Pact replay for expensive APIs

LLM calls and other expensive or non-deterministic API interactions must be captured as Pact trace recordings and replayed in tests:

- **Record mode** — a human-supervised session captures real API interactions into trace files.
- **Replay mode** — tests load the recordings and replay responses deterministically.

This applies to: LLM completions, embedding APIs, search APIs, payment APIs, any pay-per-call service.

Pact recordings live alongside test fixtures and are committed to the repository.

### 3. Real API calls require human escalation

When a test scenario needs more realistic data than existing recordings provide, the agent must **escalate to a human**. Do not autonomously call paid APIs to "just generate fixtures."

Workflow:

1. The agent halts and surfaces the gap (with the specific request shape it needs).
2. A human runs the real API call in a supervised session with `MYAPP_PORT_<NAME>=record`.
3. The captured recording is committed to the repo.
4. All future test runs use the recording in replay mode.

This prevents agents from autonomously burning API credits or hitting rate limits in CI.

## Why this is a blocking invariant

Repeated automated test runs need a controlled environment. Enforce isolation so each iteration checks behavior without depending on live services.

Other reasons:

- LLM calls are non-deterministic; replaying recordings makes tests reproducible.
- Rate limits and costs should never be a factor in CI or local testing.
- Tests that hit live services are flaky; flaky tests get muted; muted tests stop catching regressions.

## Verification

This invariant is enforced two ways:

1. **CI runs with no API keys set** (or with deliberately invalid dummy values).
   Any test that fails without `ANTHROPIC_API_KEY` (or similar) is violating the invariant.

2. **Pact recordings exist for every external-call test path.**
   If a test exercises an LLM-dependent code path, there must be a recorded trace covering it. Missing recordings are a CI failure, not a "skip this test" condition.

## How this relates to the architecture

This invariant is *the reason* the architecture is shaped the way it is:

- Port traits exist so tests can swap in stub adapters.
- The `myapp-pact` decorator exists so real interactions can be captured once and replayed forever.
- The `MYAPP_PORT_<NAME>=stub|production|record|replay` env-var convention exists so the mode is selectable per port at startup with no code change.

If you ever find yourself wanting to "just call the real thing in this one test," that's the signal to either (a) write a stub adapter for the case, or (b) escalate for a recording session.

## Related

- [../architecture/pact-record-replay.md](../architecture/pact-record-replay.md) — The mechanism that makes this invariant possible
- [../architecture/ports-and-adapters.md](../architecture/ports-and-adapters.md) — The stub/production/record/replay adapter modes
- [traces.md](traces.md) — The trace file format that gets recorded and replayed

## Next

→ [Back to the index](../README.md) — You've reached the end of the reading order
