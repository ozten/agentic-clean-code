# Agent entry point template

Merge the following section into your project's existing agent instruction file. Do not overwrite unrelated instructions. Paths below assume that instruction file is at the repository root; adjust them if needed. Replace every bracketed placeholder before adoption.

---

## Architecture and verification

Read the relevant guide before modifying environmental interfaces, tests, or tracing:

- `docs/guides/interfaces.md`
- `docs/guides/testing.md`
- `docs/guides/traces-and-replay.md`

Accepted project decisions: [paths to applicable ADRs].

Keep deterministic computation independent of concrete environmental adapters. Use existing functions, modules, interfaces, and project conventions where they provide enough control. Introduce a new boundary only when it provides a concrete testability or reproduction benefit; additional layers or packages are not required.

Application configuration selects stub, pass-through, recorder, or playback per interface. Default production to pass-through and development to recorder. Integration tests directly construct stub and playback adapters without inheriting application defaults. Recorder mode makes real calls under existing project authorization.

The default tests use controlled adapters or reviewed recordings and must not call live external services. Missing replay data must fail clearly. Fixture capture and live checks follow [project authorization procedure and budget].

Project rules that must always hold: [specific observable invariants].

Verification commands:

- Offline tests: [exact command]
- Dependency/boundary checks: [exact command, or state that no automated check exists]
- Reproduce a captured failure: [exact command and fixture location, or state that replay is not implemented]

For a change affecting an environmental interaction, state the observable invariant it must preserve and identify the failure that threatens it. Reuse a relevant existing check or add a focused assertion when coverage is missing. Check application behavior and prohibited effects, not only that an exception occurred or playback completed.

For bug fixes, use available evidence, including boundary traces where useful, to establish a reproduction and verify an assertion of expected behavior. A fixture supplies inputs and outcomes; the expected behavior comes from the project rule. Do not change fixtures or weaken assertions merely to make a check pass.

Report verification with:

- The invariant checked and the exact command run.
- The observed result and supporting test output or artifact.
- Any inference drawn from that evidence, stated separately from observations.
- Remaining unknowns, unrun checks, and limits of the controlled environment.

For example, a captured response establishes what the application observed at that boundary; it does not establish the remote system's final state. Do not claim a check passed unless it ran successfully.
