# Agentic Clean Code

Adopt the Hexagonal architecture (Ports & Adapters) with your coding agent, so its changes stay testable offline and its failures stay reproducible.

**TL;DR:** point your coding agent of choice at [docs/templates/agent-instructions.md](docs/templates/agent-instructions.md). Merge that section into the instruction file your agent already reads (`CLAUDE.md`, `AGENTS.md`, or similar), fill in the bracketed placeholders, and let the agent follow the links from there. It is the shortest path to a project where every external interaction has a controlled test adapter.

## Adopt the architecture

The material under [docs/guides](docs/guides/) and [docs/reference](docs/reference/rust-sqlite/README.md) is written for coding agents as much as for people. Copy it into your project, or just tell your agent to read it from here:

> Read docs/guides/interfaces.md, docs/guides/testing.md, and docs/guides/traces-and-replay.md. Inspect this project and identify one external dependency that makes testing expensive or hard to reproduce. Propose the smallest useful interface, implement a controlled test adapter, and verify one observable rule under a controlled failure without live service calls.

- [docs/guides/interfaces.md](docs/guides/interfaces.md) separates deterministic computation from its environment with ports and adapters.
- [docs/guides/testing.md](docs/guides/testing.md) makes verification repeatable and independent of paid services.
- [docs/guides/traces-and-replay.md](docs/guides/traces-and-replay.md) captures the evidence needed to reproduce failures.
- [docs/reference/rust-sqlite](docs/reference/rust-sqlite/README.md) holds the original, more detailed Rust and SQLite notes, including illustrative traits, decorators, and crate layout.
- [docs/README.md](docs/README.md) is the step-by-step adoption guide, with an [example architecture decision record](docs/decisions/001-agentic-clean-architecture.md) and a [blank template](docs/templates/architecture-decision.md).

Start with one external interaction and one rule that every change must preserve. Add an interface only where it enables a concrete test or reproduction.

## The talk

This repository was prepared for Austin King's five-minute talk at AI Tinkerers Seattle in September 2026, *Whose Engineering Taste Is Your Agent Inheriting?* The [slides](docs/slides/index.html) are a single HTML file; open it in a browser and press **N** for speaker notes. The [talk script](docs/ai_tinkerers_talk_sept_2026.md) and [presentation instructions](docs/slides/README.md) are alongside it.

## Sample code bases

Two implementations of the same contractor-payment workflow illustrate simple code versus a codebase using the Hexagonal architecture. Both enforce the same rules: money attached to an uncertain payment stays reserved, the payment identity is reused on retry, and a confirmed payment is never sent twice.

- [examples/contractor-payment-simple](examples/contractor-payment-simple/README.md) keeps the workflow, SQLite calls, and provider requests in one direct Python script.
- [examples/contractor-payment](examples/contractor-payment/README.md) uses explicit interfaces, injected adapters (stub, pass-through, recorder, playback), and correlated boundary traces.

Run them offline with synthetic Stripe-shaped responses:

```sh
python3 -B examples/contractor-payment/demo.py
python3 -B -m unittest discover -s examples/contractor-payment -v
python3 -B benchmarks/troubleshooting/compare.py
```

## Benchmark: a negative result

The [troubleshooting benchmark](benchmarks/troubleshooting/README.md) asks: **does using the Hexagonal architecture make coding agents more token efficient?** So far, the answer is no. In the 30-trial [pilot-v2](benchmarks/troubleshooting/results/pilot-v2/analysis/report.md), agents diagnosed the same payment failure against the simple app, the clean app, and the clean app with traces removed. Both arms without traces submitted every diagnosis. The arm with boundary traces submitted half of its diagnoses and hit the token cap on the rest. Every submitted diagnosis was judged correct.

The traces gave agents more evidence to read, and reading it cost more tokens than it saved. The pilot measured diagnosis and proposed reproduction steps only, not implemented fixes or the safety of agent-generated changes. Read the harness README for the protocol and its limits before drawing wider conclusions.

## License

MIT License, copyright (c) 2026 Austin "ozten" King. See [LICENSE](LICENSE).
