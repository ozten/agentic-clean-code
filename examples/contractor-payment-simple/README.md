# Simple Python comparison app

[app.py](app.py) keeps the payment workflow, direct SQLite calls, and provider request handling together. It has no type annotations, interface abstractions, dependency-injection setup, or boundary traces. The offline fixture path is ordinary input configuration.

It is a handwritten teaching baseline, not the output of a sampled coding harness. It intentionally retains the same payment identity, reservation, validation, and atomic local posting rules as the clean example. A short script can implement those rules correctly.

From the repository root:

```sh
python3 -B examples/contractor-payment-simple/app.py
python3 -B benchmarks/troubleshooting/compare.py
```

The first command runs the happy path. `app.py --db PATH --payment-id ID --destination ACCT --cents N --now T --fixture FILE` runs one payment against a ledger file (created and funded if absent), the same interface the clean app's `main.py` offers. The second compares this app with the [clean architecture app](../contractor-payment/README.md), using the same successful synthetic provider response and the same injected confirmation-write failure.

Both produce an error and a full ordinary traceback. The clean app additionally captures correlated boundary traces. Both retain the same local reservation and can recover once storage is available. No real API calls or payments occur.

The clean example has annotated interfaces, but the repository does not yet configure or run a static type checker. This comparison cannot attribute an improvement to type checking. See the [benchmark protocol](../../benchmarks/troubleshooting/README.md).
