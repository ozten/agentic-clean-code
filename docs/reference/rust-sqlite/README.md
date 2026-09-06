---
title: "Myapp Architecture Notes"
description: "Seed knowledge for a Rust/SQLite codebase using Clean Architecture, Ports & Adapters, and Pact record/replay"
---

# Myapp Architecture Notes

Reference notes carried over from the Cantrip second brain to seed `myapp`. The shape — Clean Architecture with port traits, adapter implementations, and a recording decorator — is what matters; the specific port methods are illustrative and should be replaced with whatever the myapp domain needs.

## Using this template

These docs are a reusable starting point for a Rust/SQLite project that wants Clean Architecture with Pact-style record/replay. Drop the `docs/` tree into a new repo, then substitute the placeholder name in all three forms it appears in: `myapp` in crate names and prose, `Myapp` in titles and headings, and `MYAPP_*` in env-var prefixes. The architectural shape — pure core, port traits, adapter implementations, recording decorator — is the load-bearing part; the example port methods and crate names are illustrative.

## Architecture

- [architecture/clean-architecture.md](architecture/clean-architecture.md) — Layers, dependency rule, crate split
- [architecture/ports-and-adapters.md](architecture/ports-and-adapters.md) — Port trait conventions, common ports (DB, LLM, FS, Clock, Process, Metering, RateLimit)
- [architecture/pact-record-replay.md](architecture/pact-record-replay.md) — Tracing decorator that wraps adapters; record vs replay testing

## Concepts

- [concepts/traces.md](concepts/traces.md) — Append-only port-interaction log; directory-per-operation file layout
- [concepts/test-isolation.md](concepts/test-isolation.md) — Blocking invariant: tests never call real external services

## Reading order

Start with [clean-architecture.md](architecture/clean-architecture.md) for the shape, then [ports-and-adapters.md](architecture/ports-and-adapters.md) for trait conventions, then [pact-record-replay.md](architecture/pact-record-replay.md) for how to wire recording in. [traces.md](concepts/traces.md) and [test-isolation.md](concepts/test-isolation.md) explain *why* the recording layer exists.

## Principles carried over

1. **Dependencies point inward.** Core depends on ports (traits). Adapters implement ports. The server wires adapters together. Core never imports adapters.
2. **Pure core.** Domain logic does no I/O. It operates entirely through port traits, which makes it trivially testable with in-memory mocks.
3. **One trace per port call.** Every adapter interaction (DB query, HTTP request, clock read, file write) is wrapped in a tracing decorator that records input, output, and timing as an atomic file.
4. **Record once, replay forever.** Real external calls happen in human-supervised sessions. The recorded trace is committed to the repo and replayed in CI — no API keys, no costs, no flakiness.
5. **Fail loud at boundaries.** Missing config, broken DB, failed migrations panic on boot. Internal code trusts internal code; only system boundaries (user input, external APIs) validate.
