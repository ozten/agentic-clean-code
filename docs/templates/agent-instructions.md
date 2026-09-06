# Agent entry point template

Merge the following section into your project's existing agent instruction file. Do not overwrite unrelated instructions. Paths below assume that instruction file is at the repository root; adjust them if needed. Replace every bracketed placeholder before adoption.

---

## Architecture and verification

Read the relevant guide before modifying environmental interfaces, tests, or tracing:

- `docs/guides/interfaces.md`
- `docs/guides/testing.md`
- `docs/guides/traces-and-replay.md`

Accepted project decisions: [paths to applicable ADRs].

Keep deterministic computation independent of concrete environmental adapters. Use existing interfaces and project conventions; introduce a new boundary when it provides a concrete testability or reproduction benefit.

Application configuration selects stub, pass-through, recorder, or playback per interface. Default production to pass-through and development to recorder. Integration tests directly construct stub and playback adapters without inheriting application defaults. Recorder mode makes real calls under existing project authorization.

The default tests use controlled adapters or reviewed recordings and must not call live external services. Missing replay data must fail clearly. Fixture capture and live checks follow [project authorization procedure and budget].

Project rules that must always hold: [specific observable invariants].

Verification commands:

- Offline tests: [exact command]
- Dependency/boundary checks: [exact command, or state that no automated check exists]
- Reproduce a captured failure: [exact command and fixture location, or state that replay is not implemented]

For bug fixes, use available boundary traces to establish a reproduction and verify an assertion of the expected behavior. Report the commands run and any gaps. Do not claim a check passed unless it ran successfully.
