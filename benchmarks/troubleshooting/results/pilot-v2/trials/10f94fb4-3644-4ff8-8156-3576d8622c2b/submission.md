# Submission

## failed_boundary

The failure is at the local SQLite durable-intent write, not at the provider boundary. In `pay`, the code starts its first transaction at `app/app.py:40-41`, debits `available` and credits `reserved` at lines 50-52, and then inserts the payment intent at lines 56-57. The `INSERT INTO payments` at line 56 raised `sqlite3.IntegrityError: database or disk is full` (the original traceback is `incident/stderr.txt:1-8`; reproduction 01 reports the identical traceback). Thus the failure happened before the retry-window check, fixture read, request construction/use, or provider outcome handling (`app/app.py:59-75`). The evidence identifies SQLite storage/capacity as the reported error, but does not distinguish a genuinely full disk from another SQLite condition that maps to that error.

The supplied exact invocation is recorded in `incident/report.md:7-16`; `reproduce_incident` reran it from the pre-command ledger and again exited 1 at this same insert, with output in `incident/reproductions/01/stderr.txt`.

## evidence

The operator inputs are `milestone-42`, `acct_demo_contractor`, and 50000 cents (`incident/report.md:3-5,9-11`). The process exited 1 (`incident/exit-code.txt:1`) and emitted no stdout (`incident/stdout.txt`, zero bytes). The stack trace directly locates the failed statement at `app/app.py:56` (`incident/stderr.txt:3-8`). Source ordering establishes that no fixture is opened until line 69 and no timeout/response branch can run until lines 71-75, after the failed insert.

Post-incident SQLite inspection of `incident/ledger.db` found no `payments` row where `id = 'milestone-42'` and no `postings` row where `payment_id = 'milestone-42'`; the independently rerun ledger `incident/reproductions/01/ledger.db` has the same absence. Both have balance row `(id=1, available=100000, reserved=0, contractor=2535400)`. The same inspection found 120 payments and 120 postings totaling 2,535,400 cents, and `PRAGMA integrity_check` returned `ok` and `foreign_key_check` returned no rows. Those are observations of the existing ledger, not evidence that its historical contractor total was caused by this incident.

The transaction is explicitly scoped by `with db` (`app/app.py:40-58`), so the final unchanged balance and absent payment are consistent with rollback of the preceding balance update when line 56 raised. The code’s intended request, if execution got that far, would use `Idempotency-Key: contractor-payment:<payment_id>` (`app/app.py:62-66`). The bundled timeout fixture has the exact incident request and labels its recorded outcome timeout (`app/fixtures/timeout.json:3-14`), but there is no artifact proving that fixture was reached or used in this failed run.

## external_outcome

For this invocation, the application did not reach its provider/fixture I/O: the only provider I/O is after the failed local insert (`app/app.py:68-75`). Therefore this run did not issue a provider request through this application, and it obtained no transfer response or `tr_...` receipt. In particular, the timeout fixture is not evidence of a timeout in this run; it is merely a fixture available in the source tree. The local evidence cannot independently query or prove an external provider’s global state, but it provides no indication that this invocation caused a remote transfer. No bank-settlement conclusion is possible either.

## local_state

No durable intent exists for `milestone-42`, its `transfer_id` is absent because its payment row is absent, and no posting exists. The $500 was not left reserved: the observed balance remains available=100000, reserved=0, contractor=2535400. This means the attempted update of available/reserved did not commit with the failed insert. The unrelated-looking historical totals should be preserved and separately reconciled if needed; SQLite structural checks being clean do not establish financial-history correctness.

## reproduction

Use the supplied deterministic incident replay: call `reproduce_incident` (equivalent inputs are the command in `incident/report.md:9-11`). It starts from the ledger immediately before the operator command and deterministically produces exit status 1 and the `database or disk is full` exception at `app/app.py:56` (observed in reproduction 01).

For a focused regression test, start from a controlled SQLite ledger with the incident pre-state (at minimum balance `(1,100000,0,2535400)` and no `milestone-42` payment/posting), invoke `pay` with fixture/request inputs `milestone-42`, `acct_demo_contractor`, 50000, and 1788706800, and fault-inject `sqlite3.IntegrityError('database or disk is full')` precisely when executing the `INSERT INTO payments` SQL at line 56. A connection wrapper/test seam can inject this directly; alternatively use a SQLite database deliberately constrained so that this specific insert returns SQLITE_FULL. Assert: (1) `pay` raises and no provider transport/fixture-open operation occurred; (2) there is no payment row, posting, or receipt for `milestone-42`; (3) balances exactly equal their pre-call values, particularly available=100000 and reserved=0; and (4) no partial posting exists. This validates that intent plus reservation is atomic under the local-write failure, rather than testing the later timeout behavior. A separate success-path test can use `app/fixtures/success.json:13-26` and assert exactly one posting, reserved reduced by 50000, contractor increased by 50000, and receipt `tr_demo_500`; it must use the same identity/request fields.

## recovery

Do not manufacture a different payment ID, alter the amount/destination, or manually release/reclassify funds. First remediate and verify the local SQLite storage/capacity failure and re-check that `milestone-42` still has no payment, posting, or receipt. Then rerun using the same approved identity `milestone-42`, destination `acct_demo_contractor`, and 50000 cents, which produces the required idempotency key `contractor-payment:milestone-42` (`app/app.py:62-66`). Given the proved pre-provider failure, reusing that identity is the safe continuation rather than issuing a second payment identity.

If that later attempt succeeds and returns a validated receipt, let the existing atomic finalization path post it (`app/app.py:86-97`). If it gets as far as a timeout/unconfirmed response, the newly committed intent/reservation must remain reserved and be retried only with that same identity within 23 hours, or manually reconciled after the window (`app/app.py:59-60`); never free it merely because the response is uncertain.
