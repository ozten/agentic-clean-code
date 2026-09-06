# Scenario: an approved contractor payment with an uncertain outcome

## Choice

Use a fictional contractor marketplace with **Stripe Connect**. A customer has already paid, funds are available, and a $500 milestone is approved. The application's job is to release the contractor's payment and keep its local records consistent through failures.

This keeps the visible story to one amount, two account roles, one external API, and a local ledger. The question for the audience is: **“If confirmation is lost, how do we avoid paying twice?”**

The [runnable example](../../examples/contractor-payment/README.md) uses an actual documented request shape with synthetic fixtures. It is an offline demonstration of our application behavior; no real funds move.

## Real services considered

| Service | Relevant API | Fit for this example |
|---|---|---|
| Stripe Connect | [`POST /v1/transfers`](https://docs.stripe.com/api/transfers/create) | Chosen: an explicit transfer to a connected account with a compact response and documented retry identity. |
| Dwolla | [`POST /transfers`](https://developers.dwolla.com/docs/api-reference/transfers/initiate-a-transfer) | Closer to bank-to-bank movement, but the talk would need to distinguish transfer initiation from later processing. |
| Escrow.com | [Create a transaction](https://www.escrow.com/api/docs/create-transaction) | Suitable if actual escrow is the subject; its buyer/seller transaction workflow adds concepts this five-minute example does not need. |

Stripe explicitly distinguishes transfers, bank payouts, and escrow in its [manual payout documentation](https://docs.stripe.com/connect/manual-payouts). The selected example is a contractor payment between Stripe account balances; neither its local reservation nor delayed confirmation should be called escrow.

## Failure sequence

1. Durably record the approved payment identity and reserve $500 locally.
2. Submit the external transfer. The app observes a timeout. It cannot know whether the request took effect.
3. Retry using the original request identity. Receive a success response, but inject disk-full while saving its confirmation locally.
4. Reopen the ledger and retry again with the same identity. Save the recovered receipt and local posting atomically.
5. Submit the same payment once more. Return its saved receipt without calling the provider.

The local states are **reserved/uncertain** and **confirmed**. Uncertainty must not make the reserved amount spendable again. The application does not pretend that local and external writes share a transaction.

The tests establish local bookkeeping and unchanged retry requests. Deduplication of real remote actions still depends on the provider's documented contract and supported time window; the fixtures cannot establish that Stripe implemented that contract correctly.

## Keep playback small

Each invocation receives one fixture through direct wiring. The fixture specifies the expected request and one outcome: timeout or success. Identical requests with different outcomes pose no lookup problem because the test selects the adapter instance. An unexpected call fails.

The same pattern works for a small end-to-end entry point: wire its dependencies before running it. Add a sequence or stateful service only when a scenario requires it. [WireMock scenarios](https://wiremock.org/docs/stateful-behaviour/) provide explicit state transitions for that later stage; they are not a prerequisite or a dependency of this repository.

## Matched troubleshooting comparison

The [comparison scaffold](../../benchmarks/troubleshooting/README.md) uses the same successful response and an injected failure at the same local confirmation write in two Python implementations. Both preserve the reservation. The simple app emits an ordinary error and traceback; the clean app also records correlated HTTP and ledger traces. A third arm uses the clean code without recorders.

The comparison is a narrower incident than the multi-invocation recovery demo above. It measures a prospective diagnosis task, not a live provider outcome or a type-checking benefit. Agent usage has not been measured.

## Presentation use

Show the same $500 remaining reserved through the failures and being posted once on recovery. The audience sees a difficult condition become a repeatable test. Keep the request headers, GUIDs, SQLite transactions, and matching rules in the repository.

The talk should say “the test verifies we preserve the payment identity and record it once,” rather than claiming an offline test proves that a live provider never duplicates a transfer.
