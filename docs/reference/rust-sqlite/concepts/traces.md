---
title: "Traces"
description: "Append-only port-interaction log; the substrate for record/replay, audit, and debugging"
---

# Traces

A trace is the atomic, append-only record of a single port interaction (one DB call, one HTTP request, one clock read, one file write). Traces are produced by the `myapp-pact` decorators that wrap each adapter.

## Purpose

Traces serve three jobs at once:

1. **Audit** — full accountability for every external action the system took.
2. **Replay** — captured traces become deterministic test fixtures (see [test-isolation.md](test-isolation.md)).
3. **Debugging** — when something fails in prod, the trace directory is the post-mortem.

## Traces vs application state

| Traces | State |
|---|---|
| What happened | What exists |
| Append-only files | Mutable rows in SQLite |
| Historical | Current |
| For analysis & replay | For operation |

Traces are *not* the source of truth for current state. SQLite is. Traces are the source of truth for *history*.

## Directory-per-operation

Each logical operation (one daemon request, one cron tick, one inner-loop run) gets its own directory. Atomic trace files live inside, sequentially numbered:

```
$MYAPP_TRACES/
  op-01966a3b-7c80-7d8e-9f12-4a5b6c7d8e9f/
    001-clock-now.trace.json
    002-database-get_entity.trace.json
    003-llm-complete.trace.json
    004-database-create_entity.trace.json
    manifest.json                 # optional index
  op-01966a3b-9d20-7abc-b234-...  /
    001-database-record_history.trace.json
```

Properties:

- **One file per port call.** Atomic write; impossible to corrupt by partial read.
- **File order = call order.** The `001-`, `002-` prefix encodes sequence.
- **Glob-friendly.** `ls op-.../*.trace.json` is the entire query API.
- **Independent.** No shared append-mode log; no locking.

## Trace entry format

```json
{
  "seq": 3,
  "port": "llm",
  "operation": "complete",
  "started_at": "2026-04-22T15:01:00.123Z",
  "duration_ms": 2840,
  "input":  { "...": "operation-specific input payload" },
  "output": { "Ok": { "...": "operation-specific output payload" } }
}
```

`output` mirrors Rust's `Result` shape (`{"Ok": ...}` or `{"Err": ...}`) so failures are recorded as faithfully as successes.

## Manifest

The manifest is an optional index of all traces in an operation:

```json
{
  "operation_id": "op-01966a3b-7c80-7d8e-9f12-4a5b6c7d8e9f",
  "command": "create_report",
  "started_at": "2026-04-22T15:01:00Z",
  "ended_at":   "2026-04-22T15:01:03Z",
  "traces": [
    { "seq": 1, "file": "001-clock-now.trace.json",        "port": "clock"    },
    { "seq": 2, "file": "002-database-get_entity.trace.json", "port": "database" },
    { "seq": 3, "file": "003-llm-complete.trace.json",     "port": "llm"      }
  ]
}
```

Not required — the directory contents are always reconstructable. Useful for fast indexing and cross-operation correlation.

## Cross-operation correlation

When one operation triggers another (e.g., a daemon request spawns a background task), each gets its own operation directory. Link them via a shared `correlation_id` field in the manifests so you can trace causal chains across the hierarchy.

## Granularity

Trace at **port boundaries**, not at every function call. Examples of what to trace:

- Database read/write
- HTTP request/response
- File read/write
- Clock read
- Process spawn / kill
- Metering event emit
- Rate-limit check

What *not* to trace:

- Internal function calls (use spans/logs for that)
- Pure computations
- Iteration over in-memory collections

The rule of thumb: if it crosses a port, trace it. If it stays in `myapp-core`, it's not interesting.

## Storage and retention

- **Dev / record sessions:** keep everything; small trace dirs are how you build up the replay corpus.
- **Production:** rotate by age + size; ship to object storage if you want long-term audit. Recent traces stay on local disk for fast post-mortem.
- **Replay corpus:** check selected trace directories into the repo as test fixtures. Treat them like any other test data — review on update, regenerate when code shape changes.

## Related

- [../architecture/pact-record-replay.md](../architecture/pact-record-replay.md) — How traces are produced (the decorator pattern)
- [test-isolation.md](test-isolation.md) — The invariant traces enable
- [../architecture/clean-architecture.md](../architecture/clean-architecture.md) — Where the recording layer sits in the stack

## Next

→ [Test Isolation](test-isolation.md) — The blocking invariant that traces and replay enable
