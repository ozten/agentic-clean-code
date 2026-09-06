# Repeatable tests without live service calls

The default automated test suite must run without paid APIs, external accounts, or production credentials. Use controlled substitutes and replay fixtures for external dependencies. A missing fixture is a failure to resolve, never a reason to silently fall back to the network.

## Choose the right test environment

- Test deterministic computation with explicit inputs and assertions about expected behavior.
- Test orchestration with controlled adapters, including errors, timeouts, and duplicate responses where relevant.
- Test local adapters with disposable local resources when needed: an isolated temporary directory or a temporary database can be appropriate for an adapter test. Keep these out of tests meant to exercise computation alone.
- Test external-service-dependent paths with reviewed recordings or local protocol substitutes. State whether replay replaces the application interface or the actual transport: interface replay does not exercise SDK serialization or HTTP handling below it.

Development application runs default to recorder mode and can supply realistic fixtures as part of normal, authorized use. Live compatibility checks and additional fixture capture remain separate from the automated test loop and follow existing project authorization and budget. Missing fixtures do not authorize new paid calls.

## Wire integration scenarios directly

Integration tests construct the application with explicit stub or playback instances for each relevant interface. They do not inherit production's pass-through default or development's recorder default. This lets a test combine realistic recorded responses with precisely scripted faults. Start with one explicitly selected response per adapter instance; a sequence engine or state machine is optional. The [contractor-payment example](../../examples/contractor-payment/README.md) shows multiple invocations, each wired independently, sharing durable local state.

For example, test “disk full during the second retry of an API call.” Define the second retry as attempt three, after the initial attempt and first retry:

1. Wire an API playback that returns a captured retryable error on attempts one and two, followed by a captured success on attempt three.
2. Wire a filesystem stub whose earlier writes succeed, but whose result-save write during attempt three returns `DiskFull`.
3. Wire a controlled clock/scheduler so retry delays advance without waiting in real time.
4. Run the actual orchestration, including its retry and persistence behavior.
5. Assert that the disk error is reported, the operation is not marked durably saved, and the application does not make an unintended fourth API call. Check that the expected playback interactions were consumed.

This example assumes the result is saved inside the retry attempt. Adapt the trigger and assertions to the application's actual contract. Coordinate the fault by the named operation and attempt, rather than elapsed wall time. If the retry loop lives inside an SDK adapter, place the test seam below that loop or test the adapter separately; replacing the whole adapter would bypass the behavior being tested.

A stub makes the rare failure controllable. Playback supplies realistic surrounding interactions. Neither requires filling a real disk or waiting for a real service to fail.

## Enforce the default

Document the exact offline test command in the project's agent instructions and CI configuration. Run without production credentials and block external network access in the test environment where supported. Removing keys alone does not prevent calls to unauthenticated services.

Reject unexpected replay requests and incomplete recordings. Assert outcomes, not just that the replay completed. Add at least one failure case relevant to the feature. Keep fixture updates reviewable; never regenerate expected results merely to make a failing test pass.

Controlled inputs increase repeatability, but thread scheduling, hidden randomness, and other uncaptured effects may still vary. Name remaining gaps rather than declaring all tests deterministic.

## Why this matters

An agent can generate tests without establishing that they are repeatable or exercise meaningful failures. Make test isolation and correctness expectations explicit, then enforce them in the test environment. The presence of tests alone is not evidence that the architecture supports realistic, difficult scenarios.

## Expand verification deliberately

Write down rules that must always hold, such as “retrying a request must not create a second notification.” Those rules can drive generated-input tests, fuzzing, and fault injection. Start with one useful rule and show that a deliberately introduced violation makes the test fail.

See [interfaces](interfaces.md) for the boundaries that enable control and [traces and replay](traces-and-replay.md) for using captured interactions as fixtures.
