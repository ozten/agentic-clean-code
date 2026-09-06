# ADR 001: Adopt controlled interfaces for contractor-payment recovery

Status: Accepted for the repository's contractor-payment example; example for adaptation elsewhere

Date: 2026-09-06

## Context

An approved $500 contractor payment crosses a remote payment API and local persistence. A timeout can leave the remote outcome unknown, and confirmation can fail to save locally even after a successful response. Repeating the workflow must preserve payment identity and must not release reserved funds or create duplicate local postings.

Coding-agent defaults do not constitute an architectural decision about these conditions. We need explicit contracts and repeatable checks of failure behavior.

## Decision

Adopt interfaces separating deterministic payment decisions from environmental effects, following [interfaces](../guides/interfaces.md), [testing](../guides/testing.md), and [traces and replay](../guides/traces-and-replay.md).

The example's `Ledger` interface provides durable preparation and confirmation. `Transfers` submits a payment using a stable key. A Stripe mapping adapter uses an injected `HttpTransport`. The core imports no concrete adapter, reads no clock, and takes time as an argument. Its orchestration invokes effects through interfaces; the retry identity and age policy operate on explicit values.

Integration tests directly construct a SQLite ledger, a single-response transport playback, and a disk-full fault adapter when required. Each invocation selects one expected outcome. Request matching is exact, an extra call fails, and there is no live fallback. More advanced playback is outside this decision.

## Persistence and uncertainty

Before external submission, commit the immutable payment identity and reserve the amount. On confirmed success, atomically commit the receipt, one posting, and local balance changes. On uncertain outcomes or failed confirmation, keep the reservation. Use the saved identity on subsequent attempts and stop automatic submission after the example's 23-hour window; reconciliation is a separate future workflow.

## Runtime wiring and recording

The reusable architectural convention selects stub, pass-through, recorder, or playback per interface, defaulting production to pass-through and development to recorder. **The example implements direct test/demo wiring, not that runtime configuration loader or a live provider transport.**

The HTTP and ledger recorders write JSON into `trace-<GUID>/trace.json` beneath a configurable root (`traces/` by default). Each record includes inputs, outputs/error metadata, an individual trace ID, and a shared global GUID. Tests can explicitly select one completed HTTP trace for playback. Ledger playback is not implemented. The sink uses direct I/O to avoid recursive recording.

An initial sink failure prevents delegation. A final sink failure stops the application, leaving any persisted initial trace incomplete. A failure before preparation prevents reservation; after preparation the reservation is retained. A trace failure after confirmation can occur even though the ledger has already committed; a later invocation reads the saved receipt rather than submitting again. This is a deliberate availability tradeoff for the teaching example. Ledger preparation and confirmation are recorded, including their errors. The comparison uses the same injected SQLite confirmation failure in both applications.

## Alternatives

- **Direct SDK calls mixed with persistence:** less initial structure, but hard-to-reach failure conditions lack an explicit test seam.
- **A new payment ID on every retry:** rejected because it changes the identity of an uncertain external action.
- **Always roll back the local reservation on an exception:** rejected because an exception does not prove that the remote transfer failed.
- **A full stateful provider simulator:** deferred; one selected response per invocation is enough for the demonstrated assertions.
- **A general replay engine or distributed transaction framework:** outside the scope of this small example.

## Consequences

The test can force a timeout followed by a confirmation-write failure and then verify recovery with durable local state. Interfaces and fixtures make the assumptions explicit, at the cost of maintaining adapters and test data. Synthetic playback does not verify live provider behavior, settlement, or concurrent workers. Introducing the architecture has an initial cost; no token or time savings are claimed without measurements.

## Verification

From the repository root:

```sh
python3 -B -m unittest discover -s examples/contractor-payment -v
python3 -B examples/contractor-payment/demo.py
```

Checks cover unchanged retry requests, reservation preservation, one local posting, duplicate submission, stale unknown payments, changed parameters, request/response matching, local transaction rollback, and trace storage failures. The default test process blocks socket connection attempts. The fixture files are synthetic and require no credentials.

The example's [README](../../examples/contractor-payment/README.md) documents implemented behavior and limits. Adapt this record to a new project's actual interfaces and verification commands rather than marking these implementation details accepted wholesale.
