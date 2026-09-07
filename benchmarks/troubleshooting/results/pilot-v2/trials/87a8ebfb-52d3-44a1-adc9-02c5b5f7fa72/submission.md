# Submission

## failed_boundary

The failure is the application's automatic-retry eligibility gate in `pay`, not the provider-transfer operation. On this invocation the existing `milestone-42` intent was found (the existing-intent path is `app/app.py:42-48`), then, after the intent transaction had ended, `app/app.py:59-60` rejected it because `now - created_at` was outside `[0, 23*3600)`. The supplied command fixes `now` at 1788706800 (`incident/report.md:7-11`); the resulting payment row has `created_at=1788620400`, so its age is 86,400 seconds (24 hours), exceeding 82,800 seconds (23 hours). The observed error and traceback identify line 60 (`incident/stderr.txt:1-8`), and the clean rerun produced the identical result (`/workspace/incident/reproductions/01/stderr.txt`). This occurs before request construction at lines 61-67 and before fixture/provider I/O at lines 68-75.

This is therefore a policy/retry-window failure at the local pre-provider boundary. It is not evidence of a provider rejection, malformed request, response validation failure, or post-response ledger-commit failure.

## evidence

* The incident describes the immutable requested facts as `milestone-42`, `acct_demo_contractor`, and 50000 cents, and gives the exact invocation (`incident/report.md:3-11`).
* The captured failed-run stderr says “outside the automatic retry window; reconcile” and its traceback terminates at `app/app.py:60` (`incident/stderr.txt:1-8`); `incident/exit-code.txt` records the failed process status.
* Reproduction 01, which starts from the ledger immediately before the command, again exited 1 with that same line-60 traceback (`/workspace/incident/reproductions/01/stderr.txt`).
* A SQLite query of `/workspace/incident/reproductions/01/ledger.db` returned `('milestone-42','acct_demo_contractor',50000,1788620400,None)`; its posting query returned `[]`; and its balance query returned `(available,reserved,contractor)=(50000,50000,2535400)`. The same targeted query against the incident DB returned the same row/state. The calculated age was 86400 seconds.
* The relevant implementation preserves the payment’s destination and amount on retries (`app/app.py:43-45`), returns if a receipt already exists (`app/app.py:46-47`), uses `contractor-payment:<payment_id>` as idempotency key (`app/app.py:61-66`), and only records posting/receipt plus the reserved-to-contractor movement after a valid transfer response (`app/app.py:86-97`).
* `app/fixtures/timeout.json:3-14` is a matching local playback artifact describing this request and a timeout, but the report explicitly says the deployment transport configuration is not included (`incident/report.md:13-16`). It cannot prove that this fixture was the transport selected for any earlier attempt.

## external_outcome

What is proven for the reported/reproduced invocation is that it never reached the source’s fixture I/O/provider-call portion: line 60 raises before lines 61-75. Thus that invocation sent no provider request through this application path.

What is not proven is whether a prior attempt during the lifetime of the durable intent reached the provider, whether it was accepted, or what transfer id it may have received. The durable row has no receipt, and the matching timeout fixture is not attributable to the earlier attempt because the actual environment configuration is unavailable. Consequently provider acceptance is unresolved/unknown; bank settlement is also not established even if a provider transfer were later confirmed. Do not infer a provider decline merely from this local retry-window error.

## local_state

The incident was left with an unresolved, durable payment intent: `payments.id='milestone-42'`, destination `acct_demo_contractor`, cents 50000, created_at 1788620400, and `transfer_id IS NULL` (targeted SQLite result from `/workspace/incident/reproductions/01/ledger.db`, matching `/workspace/incident/ledger.db`). There is no `postings` row for that payment. Balances are available=50000, reserved=50000, contractor=2535400. Therefore the $500 is still reserved, has not been posted to contractor, and has not been made available again. This matches the intended initial reservation transition in `app/app.py:50-57`; no code after a confirmed receipt (`app/app.py:93-96`) ran for this payment.

## reproduction

Deterministic reproduction: use a disposable SQLite database and establish an unresolved existing intent with the fixed facts `(id='milestone-42', destination='acct_demo_contractor', cents=50000, created_at=1788620400, transfer_id=NULL)`, one 50000-cent reservation (e.g., initial available=100000 then available=50000/reserved=50000), and no posting for that id. Invoke the exact reported command with `--now 1788706800` and a configured matching fixture; equivalently, use `reproduce_incident`, which already supplies the original pre-command ledger/environment. The controlled fault boundary is the stale age: 1788706800 - 1788620400 = 86400, while the guard at `app/app.py:59` permits strictly less than 82800.

Regression assertions: (1) `pay`/CLI fails with the specific reconcile/retry-window error and exit status 1; (2) the provider fixture/call seam is not reached (the guard precedes `open(fixture_path)` at lines 59-70); (3) payment destination, cents, created_at, and NULL receipt remain unchanged; (4) no posting is inserted for `milestone-42`; (5) balances remain exactly available=50000, reserved=50000, contractor=2535400 (or their pre-call values in an isolated fixture); and (6) no new payment id is generated. A complementary boundary test at `created_at + 23*3600 - 1` should permit the same-idempotency-key path, whereas exactly `created_at + 23*3600` must reject, since the implementation uses `<`, not `<=`.

## recovery

Treat `milestone-42` as an unresolved manual-reconciliation case. Preserve its exact durable identity, destination, amount, and the 50000-cent reservation; do not retry automatically now, do not create another payment id, and do not release the reserved amount into available funds. A qualified operator should reconcile the original provider operation using the original payment identity/idempotency key `contractor-payment:milestone-42` and the immutable amount/destination.

If authoritative reconciliation establishes that the provider accepted the matching transfer and supplies a matching `tr_...` receipt, record that one receipt and perform the single atomic local completion equivalent to `app/app.py:86-97`: one posting, reserved minus 50000, contractor plus 50000. If reconciliation cannot establish the remote outcome, retain the reservation and payment as unresolved. Any disposition following an authoritative negative provider result should be an explicit, audited manual resolution—not an automatic retry or a release based merely on this error.
