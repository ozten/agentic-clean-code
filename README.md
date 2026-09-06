# Agentic Clean Code

As coding agents make engineering effort more affordable, we can apply more of that effort to repeatability, testing, and troubleshooting.

This repository provides reusable architecture guidance for separating deterministic code from nondeterministic environments through interfaces. Controlled environments make tests repeatable. Boundary traces supply the evidence for the bug report nobody has time to write, and replay can turn that evidence into a regression test.

Start with [the adoption guide](docs/README.md). You can use these documents with any language or coding agent; the guides are language-neutral, and a small Python example makes one adoption concrete.

Try the [contractor-payment example](examples/contractor-payment/README.md): recover from a lost response and a failed local save without changing the payment identity or recording it twice. It runs offline using synthetic Stripe-shaped responses:

```sh
python3 -B examples/contractor-payment/demo.py
python3 -B -m unittest discover -s examples/contractor-payment -v
```

Compare the same payment failure in a direct Python script and the clean version:

```sh
python3 -B benchmarks/troubleshooting/compare.py
```

Both produce the same ledger outcome; the clean version adds correlated traces. The [measurement harness](benchmarks/troubleshooting/README.md) runs isolated agent trials against both apps with exact OpenAI usage accounting (`make preflight`, `make test`, `make pilot`); measurements have not been collected yet.

Read the [example adoption decision](docs/decisions/001-agentic-clean-architecture.md) for the architecture and its limits.

Prepared for Austin King's five-minute AI Tinkerers Seattle talk, September 2026. Adapted from his dotfiles architecture notes, with their Cantrip lineage preserved. Released under the [MIT license](LICENSE).
