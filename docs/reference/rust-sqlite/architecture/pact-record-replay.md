---
title: "Pact: Record & Replay"
description: "Tracing decorator that wraps adapters to enable deterministic replay testing"
---

# Pact: Record & Replay

Pact is a small Rust crate that wraps any adapter implementation to record every interaction at the port boundary as an atomic trace file. The same recordings are played back during tests so the system runs deterministically without ever calling a real external service.

This crate is the mechanism that makes the [test isolation invariant](../concepts/test-isolation.md) possible.

## How it works

Every request handled by the daemon creates a `Tracer` with a unique operation ID:

```rust
pub struct Tracer {
    operation_id: String,       // UUID v7, e.g. "op-01966a3b-7c80-7d8e-9f12-..."
    trace_dir: PathBuf,         // $MYAPP_TRACES/<operation_id>/
    sequence: AtomicU32,        // monotonic counter within the operation
}
```

Each adapter is wrapped in a tracing decorator:

```rust
pub struct TracedDatabase<D: Database> {
    inner: D,
    tracer: Arc<Tracer>,
}

impl<D: Database> Database for TracedDatabase<D> {
    fn get_entity(&self, kind: EntityKind, id: &str) -> Result<Option<Box<dyn Entity>>> {
        let seq = self.tracer.next_seq();
        let started = Instant::now();
        let result = self.inner.get_entity(kind, id);
        self.tracer.record(TraceEntry {
            seq,
            port: "database",
            operation: "get_entity",
            input: json!({ "kind": kind, "id": id }),
            output: json!(&result),
            duration: started.elapsed(),
        });
        result
    }
    // ... one wrapper per trait method
}
```

The decorator implements the same trait as the wrapped adapter. Use cases see `Arc<dyn Database>` and have no idea recording is happening.

## Trace file layout

Each logical operation gets a directory; each port call inside it becomes a numbered atomic file:

```
$MYAPP_TRACES/
  op-01966a3b-7c80-7d8e-9f12-4a5b6c7d8e9f/
    001-database-get_entity.trace.json
    002-database-list_entities.trace.json
    003-llm-complete.trace.json          # full prompt + response
    004-database-create_entity.trace.json
    manifest.json
  op-01966a3b-9d20-7abc-b234-5e6f7a8b9c0d/
    001-clock-now.trace.json
    002-database-record_history.trace.json
```

### Trace entry

```json
{
  "seq": 3,
  "port": "llm",
  "operation": "complete",
  "started_at": "2026-04-22T15:01:00.123Z",
  "duration_ms": 2840,
  "input": {
    "model": "claude-sonnet-4-6",
    "system": "...",
    "messages": [...],
    "max_tokens": 4096
  },
  "output": {
    "Ok": {
      "content": "...",
      "input_tokens": 1245,
      "output_tokens": 803,
      "model": "claude-sonnet-4-6",
      "stop_reason": "end_turn"
    }
  }
}
```

### Manifest (optional)

```json
{
  "operation_id": "op-01966a3b-7c80-7d8e-9f12-4a5b6c7d8e9f",
  "started_at": "2026-04-22T15:01:00Z",
  "command": "create_report",
  "traces": [
    { "seq": 1, "file": "001-database-get_entity.trace.json", "port": "database" },
    { "seq": 2, "file": "002-llm-complete.trace.json",        "port": "llm" }
  ]
}
```

The manifest is convenience — the directory is always reconstructable from its contents.

## Why directory-per-operation

- **Atomic writes.** One file per call. Crash recovery is trivial; partial reads are impossible.
- **Glob-friendly.** `ls op-.../*.trace.json` is the entire query API for an operation.
- **Causal ordering.** Sequence numbers in the filename preserve the call order.
- **No shared state.** Each trace file is independent; no append-mode log to corrupt.
- **Easy diffing.** Re-running a recorded operation against new code shows exactly which call diverged.

## Record vs replay

The same `myapp-pact` crate provides both directions.

### Record mode

A real adapter wrapped in `TracedDatabase` (or `TracedLlmClient`, etc.). The adapter calls the real service; the decorator captures every input/output as a trace file.

```rust
let real: Arc<dyn LlmClient> = Arc::new(AnthropicClient::new(api_key));
let tracer = Arc::new(Tracer::new("$MYAPP_TRACES"));
let llm: Arc<dyn LlmClient> = Arc::new(TracedLlmClient::new(real, tracer));
```

Record mode runs in **human-supervised sessions only**. Never let an autonomous agent loop in record mode against a paid API — repeated calls incur real costs.

### Replay mode

A *replay adapter* implements the same port trait but reads its responses from existing trace files instead of calling anything.

```rust
let llm: Arc<dyn LlmClient> = Arc::new(ReplayLlmClient::load("$MYAPP_TRACES/op-..."));
```

The replay adapter matches incoming requests against recorded ones (by operation+input shape) and returns the recorded output. If a test makes a call that wasn't recorded, replay fails loudly — that's a signal to escalate and capture a new recording.

## When to record

- A new code path needs realistic external data.
- An adapter or third-party API changes its response shape.
- A bug repro needs to capture the exact sequence that triggered it.

## When to replay

- Always, in CI.
- Always, in `cargo test`.
- Default for local dev unless you're explicitly capturing new fixtures.

## Wiring

The choice of stub / production / record / replay is set per-port at startup via env var. See [ports-and-adapters.md](ports-and-adapters.md) for the convention (`MYAPP_PORT_LLM=replay`, etc.).

```rust
fn build_llm() -> Arc<dyn LlmClient> {
    match env::var("MYAPP_PORT_LLM").as_deref() {
        Ok("production") => Arc::new(AnthropicClient::new(env_var("ANTHROPIC_API_KEY"))),
        Ok("record") => {
            let real = AnthropicClient::new(env_var("ANTHROPIC_API_KEY"));
            Arc::new(TracedLlmClient::new(real, tracer()))
        }
        Ok("replay") => Arc::new(ReplayLlmClient::load(env_var("MYAPP_TRACES"))),
        _ => Arc::new(StubLlmClient::default()),
    }
}
```

## What Pact enables

- **Replay-based testing.** Capture a real session once; re-run it forever without external dependencies.
- **Full observability.** Production traces are the same format as test fixtures. Debugging a bug in prod is reading the trace directory.
- **Causal reconstruction.** File ordering inside an operation directory shows exactly what happened in what order.
- **Learning from failures.** When something fails, the trace is the post-mortem.

## Crate layout

```
myapp-pact/
  src/
    lib.rs
    tracer.rs                   # Tracer (operation ID + sequence counter)
    trace_file.rs               # atomic trace file format and writing
    traced_db.rs                # TracedDatabase<D>
    traced_llm.rs               # TracedLlmClient<L>
    traced_fs.rs                # TracedFileSystem<F>
    traced_clock.rs             # TracedClock<C>
    traced_process.rs           # TracedProcessSpawner<P>
    replay_db.rs                # ReplayDatabase loader
    replay_llm.rs               # ReplayLlmClient loader
    ...
```

Add a new traced wrapper any time you add a new port. The pattern is mechanical: one decorator struct, one `impl Port for Decorator`, one `tracer.record(...)` call per method.

## Related

- [clean-architecture.md](clean-architecture.md) — Where the decorator fits in the layer diagram
- [ports-and-adapters.md](ports-and-adapters.md) — Trait conventions decorators must satisfy
- [../concepts/traces.md](../concepts/traces.md) — Trace file format details
- [../concepts/test-isolation.md](../concepts/test-isolation.md) — The invariant Pact enforces

## Next

→ [Traces](../concepts/traces.md) — The trace file format that gets recorded and replayed
