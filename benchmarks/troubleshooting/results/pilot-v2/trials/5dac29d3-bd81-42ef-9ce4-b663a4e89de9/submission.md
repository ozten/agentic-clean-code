# Submission

## failed_boundary

The failure was at the provider transport boundary while creating the transfer, after the local intent/reservation and before local confirmation. `pay()` calls `transfers.create()` at `app/core.py:47-53`; `StripeTransfers.create()` sends the POST at `app/adapters.py:105-115`, and the playback transport raises the timeout at `app/adapters.py:139-147`. It therefore never reached `ledger.confirm()` (`app/core.py:53`). This is not evidence that the provider rejected the transfer; it is a lost response.

## evidence

The incident command and payment parameters are recorded in `incident/report.md:3-16`. The captured request fixture `app/fixtures/timeout.json:4-15` specifies POST `/v1/transfers`, amount 50000, destination `acct_demo_contractor`, transfer group `milestone-42`, and idempotency key `contractor-payment:milestone-42`, with outcome kind `timeout`. The captured stack in `incident/stderr.txt:1-14` identifies `SingleResponse.send()` as raising `TimeoutError: Response lost; remote transfer outcome is unknown`. Re-running the supplied invocation with `reproduce_incident` produced the same exit status 1 and the same error. A direct SQLite inspection of `incident/ledger.db` showed balances `(available=50000, reserved=50000, contractor=2535400)`, payment row `('milestone-42','acct_demo_contractor',50000,1788706800,NULL)`, 120 total postings, and zero posting for milestone-42. The request construction and response validation are also explicit in `app/adapters.py:105-125`.

## external_outcome

The application definitely prepared and attempted the exact provider request represented by the fixture, and its response was unavailable. The provider's state is unknown: the transfer may have been accepted (with a response lost), or may not have been accepted. There is no transfer ID in the local receipt column and no provider response artifact proving either outcome. The success fixture (`app/fixtures/success.json:12-23`) is only a local playback scenario and does not establish what happened in this incident. Also, even a transfer response would establish provider acceptance to the connected account, not bank settlement, per the application semantics.

## local_state

The durable intent exists for payment identity `milestone-42`, destination `acct_demo_contractor`, 50000 cents, created at 1788706800, with `transfer_id=NULL`. The 50000 cents moved from available to reserved before I/O (`app/adapters.py:44-61`), and remain reserved. No posting was created and contractor balance was not increased for this payment. This is the intended conservative state for an unresolved remote outcome; `NeedsReconciliation` is documented as meaning not to release reserved money (`app/core.py:6-8`).

## reproduction

Use a disposable copy/ledger at the exact pre-command state, invoke the supplied command from the workspace root: `python3 -B app/main.py --db incident/ledger.db --payment-id milestone-42 --destination acct_demo_contractor --cents 50000 --now 1788706800` under the deployment's timeout fixture configuration (the supplied `reproduce_incident` does exactly this). The controlled fault is `app/fixtures/timeout.json`'s `kind: timeout`, whose request must exactly match the encoded request and whose transport must make one call then raise `TimeoutError`. Assert exit status 1, empty stdout, the timeout/unknown-outcome error on stderr, and exactly one provider-boundary call. Assert the database has the existing payment with unchanged identity/destination/amount, `transfer_id IS NULL`, balances `(50000,50000,2535400)`, and no `postings` row for `milestone-42`; assert no confirmation/posting occurs. A retry regression assertion should use the same payment ID, amount, destination, and idempotency key (the retry key is generated at `app/core.py:39-44`), never a new identity; a matching successful provider response such as `tr_demo_500` should then atomically create one posting and move reserved to contractor through `app/adapters.py:63-79`.

## recovery

Do not release the 50000-cent reservation, edit the row to look successful, or create another payment ID. First reconcile the provider using the durable identity/idempotency key `contractor-payment:milestone-42` and the exact amount/destination (this investigation did not contact a provider). If reconciliation shows no accepted transfer and the intent is still within the 23-hour automatic window, retry with the same identity and exact parameters; `app/core.py:39-44` permits that window and `app/adapters.py:105-113` sends the same key. If the provider reports an accepted transfer, record its verified `tr_...` receipt through the existing confirmation path, preserving the single posting. If the window has expired, or provider state cannot be established, leave funds reserved and perform manual reconciliation rather than freeing them or issuing a new payment.
