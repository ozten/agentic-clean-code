---
title: "Ports and Adapters"
description: "Trait conventions and a starter set of common ports"
---

# Ports and Adapters

A **port** is a trait. An **adapter** is an implementation. The trait lives in `myapp-ports`; the implementation lives in `myapp-adapters`. The domain (`myapp-core`) only ever sees the trait.

## Trait conventions

- `Send + Sync` so adapters can be shared across tokio tasks behind `Arc<dyn Port>`.
- Methods return `Result<T, PortError>` — never panic across the boundary.
- Inputs are owned domain types or `&str` / `&Path` references; never expose adapter-internal types (`rusqlite::Row`, `reqwest::Response`).
- Async vs sync: pick one per port and stick with it. SQLite ports are usually sync (callers wrap with `tokio::task::spawn_blocking` if needed); HTTP ports are usually async.
- One trait per concern, not one trait per backend. `Database` is a port; `SqliteDatabase` and `PostgresDatabase` are adapters of it.

## Error type

```rust
// myapp-ports/src/lib.rs
#[derive(Debug, thiserror::Error)]
pub enum PortError {
    #[error("not found")]
    NotFound,
    #[error("conflict: {0}")]
    Conflict(String),
    #[error("unavailable: {0}")]
    Unavailable(String),
    #[error("other: {0}")]
    Other(#[from] anyhow::Error),
}

pub type Result<T> = std::result::Result<T, PortError>;
```

Domain code maps `PortError` into its own error variants where it cares about the distinction; otherwise it propagates with `?`.

## Starter ports

These are the recurring ports from Cantrip. Replace method signatures with the operations myapp actually needs — but keep the *shape* of one trait per concern, narrow methods, owned inputs.

### Database

```rust
pub trait Database: Send + Sync {
    fn create_entity(&self, entity: &dyn Entity) -> Result<String>;
    fn get_entity(&self, kind: EntityKind, id: &str) -> Result<Option<Box<dyn Entity>>>;
    fn list_entities(&self, kind: EntityKind, filter: EntityFilter) -> Result<Vec<Box<dyn Entity>>>;
    fn update_entity(&self, kind: EntityKind, id: &str, updates: EntityUpdate) -> Result<()>;

    fn link(&self, from: (EntityKind, &str), to: (EntityKind, &str)) -> Result<()>;
    fn get_links(&self, kind: EntityKind, id: &str, target: EntityKind) -> Result<Vec<String>>;

    fn record_history(&self, event: &HistoryEvent) -> Result<()>;
    fn get_history(&self, filter: HistoryFilter) -> Result<Vec<HistoryEvent>>;
}
```

Keep methods narrow and intention-revealing. Don't expose a generic `query(sql: &str)` — that leaks SQL into the domain and defeats the boundary.

### LLM client

```rust
pub trait LlmClient: Send + Sync {
    fn complete(&self, request: LlmRequest) -> Result<LlmResponse>;
}

pub struct LlmRequest {
    pub model: String,
    pub system: Option<String>,
    pub messages: Vec<LlmMessage>,
    pub max_tokens: u32,
    pub temperature: Option<f32>,
}

pub struct LlmResponse {
    pub content: String,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub model: String,
    pub stop_reason: String,
}
```

The port models *what an LLM can do*, not *what Anthropic's API looks like*. The adapter handles SDK-specific marshalling.

### Filesystem

```rust
pub trait FileSystem: Send + Sync {
    fn read_file(&self, path: &Path) -> Result<String>;
    fn write_file(&self, path: &Path, content: &str) -> Result<()>;
    fn exists(&self, path: &Path) -> Result<bool>;
    fn create_dir_all(&self, path: &Path) -> Result<()>;
    fn list_dir(&self, path: &Path) -> Result<Vec<PathBuf>>;
}
```

Always have an `OsFileSystem` adapter and an `InMemoryFileSystem` adapter. Tests should never touch `/tmp`.

### Clock

```rust
pub trait Clock: Send + Sync {
    fn now(&self) -> DateTime<Utc>;
}
```

The single most important port for testability. With `OsClock` in production and `TestClock` (controllable, fixed) in tests, time-dependent logic becomes deterministic.

### Process spawner

For features that fork background work (e.g., long-running inner loops):

```rust
pub trait ProcessSpawner: Send + Sync {
    /// Spawn a detached background process. Returns the OS process ID.
    fn spawn(&self, kind: SpawnKind, id: &str) -> Result<u32>;
    fn is_running(&self, pid: u32) -> Result<bool>;
    fn kill(&self, pid: u32) -> Result<()>;
}
```

### Metering / billing

```rust
pub trait MeteringClient: Send + Sync {
    fn emit_usage(&self, event: &UsageEvent) -> Result<()>;
    fn emit_usage_batch(&self, events: &[UsageEvent]) -> Result<()>;
    fn get_entitlement(&self, customer_id: &str, feature_key: &str) -> Result<EntitlementBalance>;
}
```

### Rate limiting

```rust
pub trait RateLimitClient: Send + Sync {
    fn check_rate_limit(&self, req: &RateLimitRequest) -> Result<RateLimitResponse>;
}
```

## Adapter modes

Each port should have at least three adapter modes, selected by env var (`MYAPP_PORT_<NAME>=stub|production|record|replay`):

| Mode | Use | Example |
|---|---|---|
| **stub** | Default for `cargo test`; in-memory, no I/O | `InMemoryDatabase`, fixed-time `TestClock` |
| **production** | Real adapter against the real service | `SqliteDatabase`, `AnthropicClient` |
| **record** | Real adapter wrapped in `myapp-pact` decorator | Captures live traces for later replay |
| **replay** | Reads recorded traces and returns them deterministically | CI runs in replay mode |

The selection happens once at startup in `myapp-server::build_state()`. Use cases never know which mode is active.

## What goes in `myapp-adapters` vs `myapp-pact`

- `myapp-adapters` contains the *real* adapter (`SqliteDatabase`, `AnthropicClient`) and any in-memory test adapters.
- `myapp-pact` contains *decorators* (`TracedDatabase<D: Database>`) that wrap any adapter to add recording. They don't call external services themselves.

Keeping them separate means you can use `myapp-pact` to record/replay any new port without touching the production adapter.

## Smell tests

You're holding the architecture wrong if:

- `myapp-core` has `use rusqlite::...` or `use reqwest::...` anywhere.
- A port trait has a method that takes raw SQL or a raw HTTP body.
- Adapter types leak into use case signatures (`fn handle(db: &SqliteDatabase, ...)`).
- A unit test in `myapp-core` needs a real file or a real socket to pass.
- Two adapters of the same port disagree on what "not found" means.

## Related

- [clean-architecture.md](clean-architecture.md) — Crate boundaries and dependency rule
- [pact-record-replay.md](pact-record-replay.md) — How decorators wrap adapters
- [../concepts/test-isolation.md](../concepts/test-isolation.md) — The invariant that motivates stub/replay modes

## Next

→ [Pact: Record & Replay](pact-record-replay.md) — How the tracing decorator wraps adapters to capture and replay every port interaction
