---
title: "Clean Architecture (Ports & Adapters / Hexagonal)"
description: "Layered architecture with crate boundaries enforcing the dependency rule"
---

# Clean Architecture

Also called Ports & Adapters or Hexagonal Architecture.

We use it to keep deterministic, easily-tested code separated from the non-deterministic environments it runs against — databases, HTTP, the clock, LLM APIs. The domain talks to the world only through **port traits**; **adapters** implement those traits. Dependencies point inward: the domain has no idea what's on the other side of a port.

Production runs the real adapters. Tests programmatically stub out any port, or play back pre-recorded interactions. Recordings are on-disk **traces** — append-only, structured, causally ordered — that make troubleshooting effortless and higher-signal than logs. Captured once in a human-supervised session, they replay forever in CI: no API keys, no costs, no flakiness.

The shape is the load-bearing part: a small pure core, replaceable adapters around it, and a single decorator crate that wraps any adapter to record what it does. Adapted from the Cantrip second brain — replace the domain-specific port methods with whatever myapp's domain needs.

## The layers

```
  ┌──────────────────────┐       ┌─────────────────────────┐
  │      myapp-cli       │       │      myapp-server       │
  │   thin HTTP client    │──────►│  axum daemon, wiring,    │
  │  clap → JSON → POST   │       │  dispatch, owns adapters │
  └──────────────────────┘       └────────────┬─────────────┘
                                              │ depends on
                                 ┌────────────▼─────────────┐
                                 │      myapp-core          │  domain logic, use cases
                                 │  no I/O, no side effects  │
                                 │  operates on port traits  │
                                 └────────────┬─────────────┘
                                              │ depends on
                                 ┌────────────▼─────────────┐
                                 │     myapp-ports          │  trait definitions
                                 │  Database, LlmClient,     │
                                 │  Clock, FileSystem, ...   │
                                 └────────────┬─────────────┘
                                              │ implemented by
                                 ┌────────────▼─────────────┐
                                 │    myapp-adapters        │  real implementations
                                 │  SqliteDb, AnthropicLlm,  │
                                 │  OsFileSystem, OsClock    │
                                 └────────────┬─────────────┘
                                              │ uses
                                 ┌────────────▼─────────────┐
                                 │     myapp-pact           │  trace recording
                                 │  wraps adapters to record │
                                 │  every port interaction   │
                                 └──────────────────────────┘
```

## The dependency rule

**Dependencies point inward.** This is the only rule that matters. If you violate it, the architecture stops working.

- `myapp-core` depends on `myapp-ports` (traits only)
- `myapp-adapters` depends on `myapp-ports` (to implement them)
- `myapp-server` depends on everything (it's the wiring layer)
- `myapp-core` **never** imports `myapp-adapters`

Effects of obeying the rule:
- Core is unit-testable with in-memory port mocks. No SQLite, no HTTP, no clock skew.
- Adapters are swappable. Stub → SQLite → Postgres without touching core.
- The recording decorator (`myapp-pact`) wraps any adapter without core knowing.

## Crate split

```
myapp/
  Cargo.toml                    # workspace root
  crates/
    myapp-cli/                 # binary — thin HTTP client (clap → JSON → POST)
    myapp-server/              # HTTP daemon — axum, owns adapters + dispatch
    myapp-core/                # domain logic (pure, no I/O)
    myapp-ports/               # port trait definitions
    myapp-adapters/            # adapter implementations (SQLite, HTTP, FS, clock)
    myapp-pact/                # tracing decorators for record/replay
```

### `myapp-cli` (binary)

Thin HTTP client. Parses clap args, serializes a `{command, args, flags}` envelope, POSTs to the daemon, prints the JSON response. Zero business logic.

```
myapp-cli/
  src/
    main.rs                     # entry, serve vs client dispatch
    cli/mod.rs                  # clap app definition
    output.rs                   # JSON / human / markdown formatting
```

### `myapp-server` (HTTP daemon)

Axum-based daemon. Owns all adapters, dispatch logic, and shared state. Single `POST /api/myapp` endpoint that routes by `command`.

```
myapp-server/
  src/
    lib.rs                      # AppState, axum router, serve()
    dispatch.rs                 # command routing → core use cases
    bin/myapp-server.rs        # binary entry point
```

Responsibilities:
- Read `.env` and ENV vars on startup (`dotenvy::dotenv()`)
- Construct adapters (SQLite, HTTP clients, filesystem, clock)
- Optionally wrap each adapter in its `myapp-pact` tracing decorator
- Dispatch `{command, args, flags}` requests into core use cases
- Return JSON responses

### `myapp-core` (domain logic)

Pure domain logic. No I/O. Operates entirely through port traits.

```
myapp-core/
  src/
    lib.rs
    use_cases/
      mod.rs
      <use_case>.rs             # one file per use case, each takes &dyn Port params
    domain/
      mod.rs
      <entity>.rs               # plain structs and enums
    errors.rs                   # domain error types
```

Rule: everything in `domain/` is plain data. Everything in `use_cases/` is a function that takes port traits as parameters and returns `Result<Domain, DomainError>`. No `tokio::spawn`, no `reqwest::get`, no `rusqlite::Connection`.

### `myapp-ports` (trait definitions)

Port interfaces. The boundary where the domain talks to the outside world. See [ports-and-adapters.md](ports-and-adapters.md) for the trait conventions and a starter set.

### `myapp-adapters` (implementations)

Real implementations of the ports. Each port lives in its own submodule. Real adapters always live alongside stub/in-memory ones.

```
myapp-adapters/
  src/
    lib.rs
    sqlite/                     # SqliteDatabase
    http/                       # HTTP client adapters
    filesystem/                 # OsFileSystem + InMemoryFileSystem
    clock/                      # OsClock + TestClock
    process/                    # OsProcessSpawner + TestProcessSpawner
```

### `myapp-pact` (trace recording)

Decorator crate that wraps any port implementation to record every interaction as a trace file. See [pact-record-replay.md](pact-record-replay.md).

## Wiring on startup

```rust
// myapp-server/src/lib.rs
pub async fn serve(port: u16) {
    let _ = dotenvy::dotenv();
    let state = build_state();          // opens SQLite, reads API keys
    let app = Router::new()
        .route("/api/myapp", post(handle_request))
        .with_state(state);
    let listener = TcpListener::bind(("127.0.0.1", port)).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

fn build_state() -> AppState {
    let db: Arc<dyn Database> = Arc::new(SqliteDatabase::open(env_var("MYAPP_DB")));
    let clock: Arc<dyn Clock> = Arc::new(OsClock);
    let llm: Arc<dyn LlmClient> = Arc::new(AnthropicClient::new(env_var("ANTHROPIC_API_KEY")));

    // Optional: wrap adapters in tracing decorators
    let tracer = Arc::new(Tracer::new(env_var("MYAPP_TRACES")));
    let db = Arc::new(TracedDatabase::new(db, tracer.clone()));
    let llm = Arc::new(TracedLlmClient::new(llm, tracer.clone()));

    AppState { db, clock, llm }
}
```

## Testing strategy

The crate split makes the test pyramid trivial:

- **Unit tests in `myapp-core`**: inject in-memory port mocks. Test domain logic in isolation. No SQLite, no network, no clock.
- **Integration tests in `myapp-adapters`**: test real SQLite against migrations; test HTTP clients against recorded Pact traces in replay mode.
- **Integration tests in `myapp-server`**: spin up an in-process axum app with test SQLite and replay-mode HTTP. POST to it; assert JSON.
- **End-to-end tests**: start the daemon, run CLI commands against it, assert JSON output.

See [../concepts/test-isolation.md](../concepts/test-isolation.md) for the invariant that no test ever hits a real external service, and [pact-record-replay.md](pact-record-replay.md) for how recordings make that possible.

## Why this shape

- **Replaceable storage.** SQLite today, Postgres or DynamoDB tomorrow — the change is one adapter file.
- **Testable core.** No mocking framework needed. The port traits *are* the seam; in-memory implementations are a few lines.
- **Recordable everything.** A single decorator crate captures every external interaction without core or use cases knowing it exists.
- **Multiple front-ends.** CLI, MCP server, dashboard, cron — all speak the same `{command, args, flags}` envelope to the same daemon. No business logic duplication.

## Related

- [ports-and-adapters.md](ports-and-adapters.md) — Trait conventions and a starter set of ports
- [pact-record-replay.md](pact-record-replay.md) — How the tracing decorator works
- [../concepts/traces.md](../concepts/traces.md) — Trace file structure
- [../concepts/test-isolation.md](../concepts/test-isolation.md) — Why we never hit real services in tests

## Next

→ [Ports and Adapters](ports-and-adapters.md) — Trait conventions and a starter set of common ports
