# Workspace

You are troubleshooting a failed contractor payment. Everything you may inspect is under this
workspace; refer to files as `/workspace/...` or with paths relative to the workspace root.

- `app/`: the application source (read-only). Its command-line entry point is `{{ENTRY}}`.
- `incident/`: the incident report (`incident/report.md`) and every artifact the failed run produced.
- `scratch/`: the only writable directory. Copy files here if you want to modify or run experiments.

## Payment semantics

- A payment is identified by its durable `payment_id`; that identity is also the provider
  idempotency key (`contractor-payment:<payment_id>`). Retries must reuse the same identity,
  amount, and destination.
- Before any provider request, the application records the payment intent and moves the
  amount from `available` to `reserved` in its ledger.
- A provider transfer response carries a transfer id (`tr_...`). It confirms that the provider
  accepted the transfer to the contractor's connected account; it does not prove a bank
  settlement, which is outside this system.
- After a transfer response, the application atomically records one posting, moves the amount
  from `reserved` to `contractor`, and saves the transfer id as the receipt.
- Automatic retry with the same identity is permitted for 23 hours after intent creation;
  after that the payment requires manual reconciliation.
- Reserved funds for an unresolved payment must stay reserved; never release them or create a
  new payment identity merely because a step failed.

## Tools

- `list_files`, `read_file`, `search_text`: inspect the workspace.
- `run_shell`: run a shell command in the workspace (no network; Python 3 and sqlite3 are
  available; writes only succeed under `scratch/`).
- `reproduce_incident`: rerun the operator's exact invocation under the same environment,
  starting from a freshly funded ledger. Output goes to a new directory under
  `incident/reproductions/`. This is observation of the failure, not an oracle.
- `submit_diagnosis`: submit your final answer. The trial ends at your first submission.

Limits: at most 40 model turns and 40 tool calls, 12 minutes, and a total token budget.
Tool outputs longer than 16 KiB are truncated with a marker; use `read_file` with an offset
to read more.

## Task

{{TASK}}
