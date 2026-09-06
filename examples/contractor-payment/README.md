# Pay a contractor once, even when confirmation is lost

A fictional contractor marketplace releases an approved $500 milestone payment using Stripe Connect. The platform already has sufficient available Stripe funds. The transfer credits the contractor's connected Stripe account; a later bank payout is outside this example.

The real-world API is Stripe's `POST /v1/transfers`. All example responses are **hand-authored synthetic fixtures based on its documentation**, not recordings from Stripe. No accounts, credentials, network calls, or third-party packages are needed.

## Run from the repository root

Requires Python 3.10 or newer. Verified locally with Python 3.12.

```sh
python3 -B examples/contractor-payment/demo.py
python3 -B -m unittest discover -s examples/contractor-payment -v
```

Run one payment from the command line (creates and funds the ledger if absent):

```sh
python3 -B examples/contractor-payment/main.py --db /tmp/ledger.db --payment-id milestone-42 \
  --destination acct_demo_contractor --cents 50000 --now 1788706800 \
  --fixture examples/contractor-payment/fixtures/success.json --traces /tmp/traces
```

Choose the demo's trace location with `--traces /path/to/traces`. The demo creates a temporary SQLite ledger, reopens its connection between attempts, and retains the boundary traces at the selected location. It generates a fresh scenario each run; it does not resume the previous run's temporary ledger.

## The corner case

| Invocation | Wired external outcome | Local outcome |
|---|---|---|
| Initial submission | A timeout: the app cannot tell whether Stripe created the transfer. | Keep $500 reserved; do not claim success or release the money. |
| First retry | A successful transfer response. | Inject disk-full at the ledger's confirmation boundary; keep the durable intent. |
| Second retry | The same successful transfer response. | Use the original key and parameters; atomically save one posting and the receipt. |
| Duplicate click | No remote calls allowed. | Return the saved receipt. |

The narrative assumes Stripe accepted the first request before the response was lost. The application cannot observe that fact, and the timeout fixture does not pretend to prove it. The tests verify that the client preserves the request identity required by the provider's deduplication contract.

The local bookkeeping starts with $1,000 available. While uncertain, $500 remains available and $500 reserved. After confirmation, $500 remains available and $500 is recorded against the contractor. These are application ledger values, not live bank or Stripe balance queries. There are no fees, currencies other than USD, or other transfers in the scenario.

## One explicitly selected response

Each attempt constructs a new playback instance. There is no search across recordings, request-history inference, or provider simulator:

```python
playback = SingleResponse.load(FIXTURES / "success.json")
gateway = StripeTransfers(playback)
pay(payment, DiskFullOnConfirmation(ledger), gateway, now=1001)
```

The test expects an exception here. It then asserts the durable reservation and absence of a local posting. The fixture contains the expected request and one response; a different request or an extra call fails. To demonstrate recovery, the next invocation wires a fresh instance with the same response.

`StripeTransfers` exercises request form encoding and validation of the response's amount, destination, currency, group, and ID. It uses a supplied transport. The example does not ship authentication, a live network transport, an SDK integration, or a provider compatibility test.

## Where the architecture lives

| File | Responsibility |
|---|---|
| [core.py](core.py) | Immutable payment inputs, ledger/transfer interfaces, deterministic retry identity and age policy, interface-driven orchestration. |
| [adapters.py](adapters.py) | SQLite persistence, Stripe mapping, single-response playback, and no-call assertion. |
| [tracing.py](tracing.py) | GUID directories, shared correlation ID, serialized HTTP and ledger inputs/outcomes, and explicit conversion of one trace to a fixture. |
| [main.py](main.py) | Command-line entry point: one payment against a SQLite ledger, transport fixture from `--fixture` or `PAYMENT_FIXTURE`, optional `--traces`. |
| [faults.py](faults.py) | Test-only disk-full fault adapter used by the demo and tests; not part of application wiring. |
| [demo.py](demo.py) | Direct wiring of each invocation and visible checks. |
| [test_payment.py](test_payment.py) | Corner cases and contract assertions. |

The deterministic decisions consume values supplied by the caller, including time. SQLite and trace-writing code live in adapters. `pay` orchestrates effects through interfaces; it is not a pure function. The program controls those effects in tests by supplying adapters.

This example deliberately uses direct wiring, as an integration test should. It does not yet implement the reusable guides' full production/development config loader. HTTP playback and recording work, and a ledger decorator records preparation and confirmation, including the injected disk-full exception. Related HTTP and ledger records share a global trace ID. The playback converter currently accepts only HTTP records; ledger playback is not implemented.

## Rules checked

- Persist the payment identity and reserve funds before making an external request.
- Keep the same amount, destination, and idempotency key across retries.
- Retain reserved funds when the outcome is uncertain or local confirmation fails.
- Commit the local posting, balance changes, and receipt in one transaction.
- A confirmed payment must not produce another remote request or local posting.
- Stop automatic submission of an unresolved payment after 23 hours; require reconciliation.
- Fail on unexpected playback input or extra calls. No live fallback.

Tests additionally cover insufficient unreserved funds, changed payment parameters, malformed success data, failure before initial persistence, rollback after partial SQL work, and recorder storage failures. The disk-full adapter injects an `ENOSPC` exception; it does not test how SQLite behaves on a genuinely full filesystem. A separate SQLite trigger test verifies transaction rollback after intermediate local updates.

## Recording failure policy

The recorder persists an incomplete entry before delegating, then atomically replaces it with a completed record. If the initial write fails, the external action never starts. If the final HTTP trace write fails, the application propagates the error and leaves the payment reserved; the existing trace remains incomplete. For a ledger trace, the underlying transaction may already have committed: a failed final confirmation trace write does not undo that commit, and recovery reads the saved receipt without making another provider call. A failed trace write may mask an underlying transport error. This small example favors halting over continuing without evidence.

The trace sink uses direct filesystem I/O, avoiding recursive tracing. Atomic replacement does not guarantee durability through power loss. Trace GUIDs and timing come from the recorder's environment and are not inputs to payment decisions. The demo uses one fixed global GUID for repeatable storytelling; an application should create a new correlation ID per initiating operation. These synthetic requests contain no credentials; a real recorder needs a redaction policy before handling authenticated traffic.

## Boundaries of the example

This is an executable architecture teaching example, not a complete payments integration or general accounting ledger. It models one pool, one contractor, and sequential invocations. It does not implement approval/authentication, live Stripe behavior, bank settlement, refunds, webhooks, fees, reconciliation, multi-worker coordination, or distributed transactions. The payment ID is assumed to be the durable ID of the already-approved milestone, not a fresh ID generated on every click.

The 23-hour cutoff is a conservative local example policy. Stripe documents that idempotency keys can be pruned after at least 24 hours; a retry after pruning can create another transfer. No automatic retry is attempted beyond the local window. Non-success HTTP responses are retained for review rather than assigned a universal retry policy.

## Compare troubleshooting evidence

The [simple Python app](../contractor-payment-simple/README.md) preserves the same payment rules with direct calls and ordinary error reporting. Run the [comparison scaffold](../../benchmarks/troubleshooting/README.md) to see matching happy paths and failure states, with correlated traces added by the clean app. A third arm disables recording in the clean app.

The clean interfaces have type annotations, but a static type checker is not yet configured or run. The experiment currently concerns structure and diagnostic evidence; it does not establish a type-checking benefit or token savings.

## Sources

Provider documentation reviewed September 6, 2026:

- [Stripe: create a transfer](https://docs.stripe.com/api/transfers/create) — endpoint, amount units, destination, response, and sufficient-balance requirement.
- [Stripe: idempotent requests](https://docs.stripe.com/api/idempotent_requests) — preserving the request key and parameters, cached results, and retention limits.
- [Stripe: advanced error handling](https://docs.stripe.com/error-low-level) — unknown outcomes after network errors and why changing a key can duplicate an effect.
- [Stripe: manual payouts](https://docs.stripe.com/connect/manual-payouts) — distinguishes connected-account transfers from bank payouts and states Stripe does not provide escrow accounts.

See the [adoption decision](../../docs/decisions/001-agentic-clean-architecture.md) and [scenario selection](../../docs/examples/contractor-payment.md).
