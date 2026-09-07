# Submission

## failed_boundary

The failure is at the offline provider-transport boundary, specifically receiving the response to the POST transfer request—not at ledger reservation or posting. `app/app.py:61-68` constructs a transfer request and `:69-71` validates it against the fixture; `:73-74` turns the recorded timeout into `TimeoutError` before the response/finalization code at `:75-97`. The incident traceback independently identifies `app/app.py:74` as the failing operation (`incident/stderr.txt:1-8`).

## evidence

The operator command and its exact payment inputs are recorded in `incident/report.md:3-10`: payment `milestone-42`, destination `acct_demo_contractor`, 50000 cents, and `now=1788706800`. The timeout fixture records the matching POST, amount, destination, transfer group, and idempotency key `contractor-payment:milestone-42` (`app/fixtures/timeout.json:3-15`), with outcome kind `timeout` and no response. `reproduce_incident` produced exit status 1 with the same timeout and traceback in `incident/reproductions/01/stderr.txt` (also reported by the tool). The incident database query shows the target payment row `(milestone-42, acct_demo_contractor, 50000, 1788706800, NULL)` and no target posting; these are direct rows in `incident/ledger.db` (the `payments` and `postings` tables).

## external_outcome

The provider's state is unknown. The timeout fixture proves only that this application received no response/receipt; it does not prove rejection, non-acceptance, or acceptance. In particular, there is no `tr_...` receipt for this payment locally, and the rules/code say a transfer response—not mere request dispatch—is the acceptance evidence. It is therefore possible that the provider accepted the transfer and the response was lost, but that cannot be established from these artifacts. The successful fixture's `tr_demo_500` is a separate playback fixture, not evidence of the real incident's remote state. Bank settlement is also not established by a transfer response.

## local_state

The pre-request ledger transaction committed the intent and reservation (`app/app.py:40-58`), then the provider work occurred outside that transaction (`:59-74`). Consequently the incident database has balances `(available=50000, reserved=50000, contractor=2535400)` and the target payment has `transfer_id=NULL`; there is no `postings` row for `milestone-42`. This means the $500 remains reserved, not available/spendable, and no local contractor posting or receipt was recorded. The existing prior postings explain the nonzero contractor balance but do not change the target's unresolved state. No release/rollback path runs on timeout; finalization is only at `:86-97`.

## reproduction

Deterministic offline reproduction: use the supplied operator command from the workspace root (`incident/report.md:7-10`) with the deployment's recorded timeout transport (the supplied `app/fixtures/timeout.json`, whose request exactly matches `app/app.py:61-71`), or call `pay` against that fixture on a copied/fresh initialized SQLite ledger. Control inputs to `payment_id=milestone-42`, destination `acct_demo_contractor`, cents `50000`, now `1788706800`; make the fixture outcome `{"kind":"timeout"}`. Assert exit status 1 and the `Response lost; remote transfer outcome is unknown` error. Assert the request carries idempotency key `contractor-payment:milestone-42`, amount 50000, destination, and transfer group, and assert the ledger has one intent with those immutable values, `transfer_id IS NULL`, no posting, available reduced by 50000, reserved increased by 50000, and contractor unchanged. The supplied `reproduce_incident` is a deterministic confirmation: reproduction 01 exited 1 with exactly that traceback. A complementary regression case can replay the same unresolved DB with `success.json` (same identity/amount/destination): assert one posting only, receipt `tr_demo_500`, reserved decreases by 50000, contractor increases by 50000, and a second same-identity success replay does not add another posting. Also assert that changing amount or destination for this existing identity is rejected (`app/app.py:42-48`).

## recovery

Keep `milestone-42` and its 50000 cents reserved; do not release the reservation and do not create a replacement payment ID. Within the 23-hour window (the code enforces this at `app/app.py:59-60`), have an authorized reconciliation/retry process query the provider or retry using exactly the same idempotency key, amount, and destination. If a matching `tr_...` transfer is confirmed, atomically record that receipt/posting and move reserved to contractor as the finalization block specifies (`app/app.py:86-97`), with an idempotency-safe check for an already-recorded receipt. If provider status remains unresolved or the 23-hour window has passed, escalate to manual reconciliation while leaving the reservation untouched. Do not infer success from the timeout and do not make the funds spendable again.
