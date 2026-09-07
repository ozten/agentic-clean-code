# Submission

## failed_boundary

The failure was at the provider-transfer transport boundary: `StripeTransfers.create` built the POST and called `transport.send` (`app/adapters.py:105-115`), after the durable ledger prepare but before local confirmation. The configured single-response transport raised `TimeoutError` (`app/adapters.py:139-147`), so `pay` never reached `ledger.confirm` (`app/core.py:47-54`). This is not a validation failure or a ledger-confirm failure.

## evidence

The incident command and payment parameters are recorded in `incident/report.md:3-16`. The prepare trace (`incident/traces/trace-dbc6c5fc-55fe-4fb8-b2f8-d26285822df6/trace.json:5-27`) shows a completed prepare for `milestone-42`, `acct_demo_contractor`, 50000 cents at time 1788706800, with `transfer_id: null`. The HTTP trace (`incident/traces/trace-f41c88fe-5e1c-40e6-bd9c-98a316e2189c/trace.json:5-22`) shows the exact POST, amount, destination, transfer group, and idempotency key `contractor-payment:milestone-42`; it has no output and records `TimeoutError` / “Response lost; remote transfer outcome is unknown”. `incident/stderr.txt:1-23` independently shows the same exception stack through `pay` and `transport.send`. The SQLite query of `incident/ledger.db` shows the durable row `(id='milestone-42', destination='acct_demo_contractor', cents=50000, created_at=1788706800, transfer_id=NULL)`, balances `(available=50000, reserved=50000, contractor=2535400)`, and no posting for this payment. The application code explains these states: prepare reserves and inserts the intent before I/O (`app/adapters.py:44-61`), while confirm creates the posting, transfers reserved to contractor, and saves the receipt (`app/adapters.py:63-79`).

## external_outcome

The provider's state is unknown, not proven failed and not proven accepted. The recorded request was handed to the configured transport and the response was lost; there is no provider response or `tr_...` receipt in the artifacts. Therefore the evidence cannot establish whether Stripe accepted the transfer, and it also cannot establish bank settlement (which is outside this application). The exact request identity is nevertheless known, so any reconciliation/retry must use that same idempotency key and unchanged payment data.

## local_state

The payment intent durably exists and its 50,000 cents remain reserved: available is 50,000, reserved is 50,000, contractor is 2,535,400. `payments.transfer_id` is NULL and there is no posting for `milestone-42`; hence the local ledger has not credited the contractor or made these funds available again. This is the required unresolved state. The process exited 1 as recorded by `incident/exit-code.txt` and `incident/report.md:3-5`.

## reproduction

Use the supplied deterministic command from `incident/report.md:7-16` (or call `reproduce_incident`): `python3 -B app/main.py --db incident/ledger.db --payment-id milestone-42 --destination acct_demo_contractor --cents 50000 --now 1788706800 --traces incident/traces`. The deployment-selected fixture is the controlled timeout fixture: `SingleResponse.send` checks the exact fixture request, permits only one call, then raises `TimeoutError` (`app/adapters.py:128-147`). Assert exit status 1; stderr contains `Response lost; remote transfer outcome is unknown`; exactly one completed ledger/prepare trace and one completed HTTP/send trace exist, with the HTTP trace containing the exact POST and `contractor-payment:milestone-42`, `outputs: null`, and `error_code: TimeoutError`; no confirm trace exists. Assert the database has exactly one unchanged intent row for this identity and data, `transfer_id IS NULL`, no posting for it, and balances are available=50000, reserved=50000, contractor=2535400. A regression test should additionally assert that a retry path never changes identity, amount, destination, or key and that confirmation occurs only after a matching `tr_...` response; it must not create a second payment row or posting for the timeout case.

## recovery

Treat `milestone-42` as unresolved. Do not release or otherwise make the 50,000 reserved cents spendable, and do not create a replacement payment ID. Since the intent is timestamped 1788706800 and the policy permits automatic retry for less than 23 hours (`app/core.py:39-44`), perform provider reconciliation/retry only through the existing payment identity and exact same amount/destination, using `contractor-payment:milestone-42`; provider idempotency should return the existing transfer if it was accepted, or safely attempt that same identity if it was not. On a matching `tr_...` response, run the existing atomic `confirm` path, which creates one posting and moves reserved to contractor. If the 23-hour window has passed, or provider lookup remains unavailable, leave the row and funds reserved and escalate to manual reconciliation; never infer failure from the timeout and never issue a new identity.
