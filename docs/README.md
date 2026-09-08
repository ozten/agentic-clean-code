# Reusable architecture guidance

Use these documents to help your coding agent build software whose behavior you can test repeatedly and whose failures you can reproduce. Start with one rule that changes must preserve and control the environmental interaction that threatens it: an API, storage, a clock, randomness, or a process. Existing functions and modules may provide enough control; introduce an interface when it enables a concrete test or reproduction.

## Supply deliberate engineering guidance

Without explicit architectural guidance, a project inherits the coding harness's defaults and the patterns its agent chooses. Generated tests alone do not establish repeatability, useful failure coverage, or reproducible bug reports.

Agentic Clean Code makes those quality expectations concrete: interfaces separate code from its environment, integration tests control that environment, and boundary traces provide reproduction evidence. The guides give agents a consistent structure to implement and verify. Project-specific decisions and executable checks turn that guidance into practice.

## Try the working example

Run the [contractor-payment example](../examples/contractor-payment/README.md): a lost API response, a failed local confirmation write, and recovery using one response per invocation. It uses documented Stripe request shapes and synthetic fixtures, requires no accounts, and moves no money. The [example adoption ADR](decisions/001-agentic-clean-architecture.md) explains its decisions and limits.

For a matching baseline, try the [simple Python app](../examples/contractor-payment-simple/README.md) and [troubleshooting comparison](../benchmarks/troubleshooting/README.md). The comparison checks happy-path and failure-state parity, then exposes the difference in available evidence. The [30-trial pilot-v2](../benchmarks/troubleshooting/results/pilot-v2/analysis/report.md) found no token savings from traces: each arm without traces submitted 10/10 diagnoses, while the traces arm submitted 5/10 and hit the token cap in five trials. All submitted answers were judged correct in session review. The task did not require agents to implement fixes or regression tests.

## Start with one boundary

1. Copy `docs/guides/` and `docs/templates/` into your project, preserving their relative paths. The reference material is optional.
2. Ask your agent to read the three guides and inspect the existing project. Identify one expensive or difficult-to-reproduce external interaction. Avoid a wholesale rewrite.
3. Adapt the [example adoption decision](decisions/001-agentic-clean-architecture.md) to your actual interfaces, affected code, tradeoffs, and verification commands. Store the completed record in your project's `docs/decisions/` directory. A [blank template](templates/architecture-decision.md) is also available.
4. Merge the [agent instructions](templates/agent-instructions.md) into the instruction file your agent actually reads. Fill in the commands and project-specific rules. Merely copying Markdown does not enforce it.
5. Implement that interface with a production adapter and a controlled test adapter. Demonstrate the same test passing repeatedly with fixed inputs and no live service calls.
6. Configure each adopted interface for stub, pass-through, recorder, or playback. Default production to pass-through and development to recorder. Integration tests directly wire stubs and playback adapters. Capture one failure, replay it, and retain an assertion of expected behavior as a regression test.

Example adoption request:

> Read docs/guides/interfaces.md, docs/guides/testing.md, and docs/guides/traces-and-replay.md. Inspect this project and identify one external dependency that makes testing expensive or hard to reproduce. Explain the smallest useful interface and its tradeoffs, write a proposed decision using docs/templates/architecture-decision.md (or adapt the contractor-payment ADR if copied), and implement a controlled test adapter using the project's existing conventions. State one observable rule the change must preserve and verify it under a controlled failure without live service calls. Reuse existing boundaries where sufficient. Report the exact command, observed result, supporting artifact, and remaining uncertainty; distinguish observations from inferences. Follow existing project authorization for external calls.

## What to read

| Document | Purpose |
|---|---|
| [Interfaces](guides/interfaces.md) | Separate deterministic computation from its environment. |
| [Testing](guides/testing.md) | Make automated verification repeatable and independent of paid services. |
| [Traces and replay](guides/traces-and-replay.md) | Capture the evidence needed to reproduce failures. |
| [Example adoption ADR](decisions/001-agentic-clean-architecture.md) | A concrete decision to understand and adapt. |
| [Decision template](templates/architecture-decision.md) | Optional blank form for a project-specific decision. |
| [Agent instruction template](templates/agent-instructions.md) | Connect the guidance to day-to-day implementation and verification. |
| [Original Rust/SQLite notes](reference/rust-sqlite/README.md) | Detailed source material, including illustrative traits, decorators, and crate layout. |

## Why guidance, ADRs, and an agent entry point?

The guides describe reusable practices. Keep them short and link to the relevant one when assigning a task, rather than pasting every reference into every prompt. Reduced token use is an outcome to measure, not a guarantee of this layout.

An architecture decision record (ADR) captures a particular project's context, chosen scope, alternatives, and consequences. A generic document cannot truthfully declare that every project has accepted the same architecture. Adapt the worked example or use the blank template to record the actual decision; when the decision changes, supersede it with a new record.

An agent entry point identifies the active guidance and real verification commands. It should link to the guides instead of repeating them. Teams should maintain one source of truth for each rule.

A skill is useful for a repeatable procedure such as inspecting a repository, proposing boundaries, or reviewing test isolation. These documents are the underlying guidance that such a skill could reference. No tool-specific skill is required for adoption; a packaged skill can be added when its workflow is established.

## Scope and provenance

The three guides adapt Austin King's original dotfiles docs for reuse across languages and project sizes. The original `docs/` tree is retained under `reference/rust-sqlite/`, including its historical migration plan. The API-spend anecdote and references to it have been removed for this edition; the source files in dotfiles are unchanged. That plan describes earlier work in dotfiles and is not an implementation plan for this repository.

The reference includes Rust/SQLite-specific conventions and illustrative code, not a shipped implementation. Its `myapp` names are placeholders. Its term `Pact` names the recording design described there; no library installation is supplied here.

The guides qualify several claims from the reference: calling an effectful interface does not make a function pure; recording does not control every source of nondeterminism; numbering concurrent calls does not fully capture causality; and a file per call alone does not guarantee atomic or complete recording. The guides also use the current wiring convention: production defaults to pass-through, development to recorder, and integration tests wire adapters directly. Each boundary trace now has its own GUID-named directory under a configurable root, with a shared global trace ID to correlate related records. These conventions supersede the historical reference's development defaults and directory-per-operation layout. Use the guides for new adoption and the originals for historical detail.

## Further experiments

Once a boundary is controllable, explore property-based testing (generate inputs and check rules), fuzz testing (search with unusual inputs), fault injection (simulate failures), time-travel testing (control clocks), and model checking (explore a model's possible states). Formal proofs and diverse independent implementations are further research directions. Each needs its own meaningful correctness criteria; replay alone does not establish that a recorded answer was right.

To evaluate the benefit, compare the same change or bug fix with and without the adopted practice. Record elapsed time, agent tokens, live API calls, and whether the regression test detects the bug. Include the cost of introducing and maintaining the boundary.
