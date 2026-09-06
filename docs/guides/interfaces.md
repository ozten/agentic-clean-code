# Interfaces separate code from its environment

An interface describes an operation and its contract. An adapter implements it against a particular environment. A port is the interface at that boundary; Rust traits are one way to express it.

The aim is repeatability and testability: deterministic computation receives controlled inputs, while nondeterministic interactions happen through explicit interfaces. Examples include reading the clock, calling an LLM, accessing storage, drawing random values, and starting processes.

## Working rules

- Keep deterministic computation independent of SDKs, operating-system APIs, and concrete adapters. Given the same explicit inputs, it should produce the same result.
- Code coordinating external interactions depends on interfaces. It may perform effects through them; it is not therefore a pure function.
- Define interfaces in terms meaningful to the caller. Keep backend-specific response objects and errors inside adapters; expose the values and error categories the caller needs.
- Supply a production adapter and a controlled substitute for each boundary exercised by isolated tests. Select adapters from per-interface configuration at application startup; integration tests construct their adapters directly.
- Make time and randomness explicit where behavior depends on them. Decide whether ordering matters, and normalize irrelevant ordering where appropriate.
- Keep interfaces small enough to implement faithfully. Document semantics such as missing data, timeouts, retries, and duplicate requests.

For example, a reminder application can receive the current time and a list of reminders as inputs to a deterministic function that chooses which are due. Separate interfaces load reminders and send notifications. Tests fix the time and capture attempted notifications without actually sending any.

## Configure each interface

Application configuration selects one of four modes independently for each interface:

| Mode | Behavior |
|---|---|
| `stub` | Supply controlled values, scripted errors, or an in-memory implementation. |
| `pass-through` | Call the real implementation without boundary recording. |
| `recorder` | Call the real implementation and capture requests, responses, and errors. |
| `playback` | Match requests against a recording and return captured results without live calls. |

Production defaults to `pass-through`. Development defaults to `recorder`, so exercising the application produces evidence for reproduction and future test fixtures. Recorder mode makes real calls and incurs their normal costs and effects. Existing authorization for running the application applies; this default does not authorize an unattended test loop to use real services.

For example, an application could define this configuration shape (illustrative YAML, not a supplied config loader):

```yaml
profiles:
  production:
    default_mode: pass-through
    interfaces: {}
  development:
    default_mode: recorder
    interfaces:
      clock:
        mode: stub
        fixed_time: "2026-09-01T12:00:00Z"
      notifications:
        mode: playback
        fixture: fixtures/notifications.json
```

Resolve an explicit interface override first, otherwise use the selected profile's default. The startup wiring constructs each adapter and injects it into the application. Reject unknown modes and missing required configuration; never silently switch playback to a live adapter. The code using an interface does not choose its mode.

Integration tests bypass these runtime defaults. Each test directly wires stubs and playback adapters to assemble its scenario, including combinations that would be difficult to create in a real environment. See [testing](testing.md) for a retry-and-disk-full example.

## Adopt incrementally

Start at an interaction that causes cost, nondeterminism, or painful reproduction. Existing modules and functions may provide enough separation; separate packages, a daemon, and a particular database are not prerequisites.

There is a cost: more interfaces and adapters to maintain. Avoid wrapping every internal function or designing hypothetical replacement backends. Add a boundary where control over the environment provides a concrete benefit.

## Verify

Demonstrate one meaningful scenario with controlled adapters. Check that the deterministic code does not import concrete clients or read hidden environmental inputs. Use the language's dependency restrictions or a project-specific automated check where available.

Then verify adapter behavior separately against its contract. A passing test against a substitute does not prove that the production adapter or external service behaves identically. See [testing](testing.md) and [traces and replay](traces-and-replay.md).
