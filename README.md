# Agentic Clean Code

As coding agents make engineering effort more affordable, we can apply more of that effort to repeatability, testing, and troubleshooting.

This repository helps you give coding agents controllable dependencies, repeatable tests, and replayable failure evidence. Start with one external interaction and one rule that every change must preserve. Use existing functions and modules where they provide enough control; add interfaces where they enable a concrete test or reproduction.

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

Both preserve the same payment rules and recover correctly in the comparison tests; the clean version adds correlated traces. In the 30-trial [pilot-v2](benchmarks/troubleshooting/results/pilot-v2/analysis/report.md), each arm without traces submitted 10/10 diagnoses; the traces arm submitted 5/10, with five token-cap stops. All 25 submissions were judged correct in session review. This pilot found no token savings from traces. It evaluated diagnosis and proposed reproduction procedures, not implemented fixes or the safety of agent-generated changes. See the [measurement harness](benchmarks/troubleshooting/README.md) for the protocol and limits.

Read the [example adoption decision](docs/decisions/001-agentic-clean-architecture.md) for the architecture and its limits.

Open the [HTML slide deck](docs/slides/index.html) or read its [presentation instructions](docs/slides/README.md).

Prepared for Austin King's five-minute AI Tinkerers Seattle talk, September 2026. Adapted from his dotfiles architecture notes, with their Cantrip lineage preserved. Released under the [MIT license](LICENSE).
