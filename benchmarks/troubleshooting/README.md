# Troubleshooting measurement harness

Question: **How many coding-agent tokens does it take to correctly explain and reproduce the same payment failure, given each application's available evidence?**

Status: harness implemented through the pilot stage (work packages P1–P6 of the [design](../../docs/plans/2026-09-06-agent-troubleshooting-measurements.md)); the 18-trial pilot (P7) runs only from an approved manifest. No token-saving result exists yet. The measured batch (P8) and presentation (P9) require a separately frozen manifest.

## Comparison arms

| Arm | Application | Available diagnostic evidence |
|---|---|---|
| `simple` | Direct Python script, SQLite and request handling in one workflow. | Standard error and full traceback. |
| `clean` | Python core, explicit interfaces, injected adapters. | Same standard error and traceback, plus HTTP and ledger traces. |
| `clean-no-traces` | The exact clean code with recorders omitted at wiring. | Standard error and full traceback. |

All arms use the same Python interpreter, amount, destination, idempotency key, request fixtures, database schema, initial funds, and injected environment. `harness parity` verifies matching happy-path and failure states for every case.

## Cases

| Case | Hidden environment | Application-visible condition |
|---|---|---|
| S1 `preparation-failure` | Storage fault on the initial payment-intent write. | `database or disk is full` before any provider request; nothing committed. |
| S2 `confirmation-failure` (smoke test) | Storage fault on the confirmation write. | Provider response received; `database or disk is full` saving it; reservation retained. |
| S3 `response-lost` | Timeout fixture wired as the provider transport. | `Response lost; remote transfer outcome is unknown`; reservation retained. |
| S4 `response-mismatch` (v2) | A 200 transfer response whose amount is 1% lower than requested. | Validation rejects the response (`Unconfirmed payment response` / `Response does not match the payment`); reservation retained. Only the traces arm can see the response body. |
| S5 `stale-retry` (v2) | An earlier attempt 24 hours before the incident timed out; the operator retries. | `Payment is outside the automatic retry window`; no provider request in this run; the earlier attempt's outcome is unknown. |

Cases are frozen in `harness/cases.py` (version 2) with content digests recorded in every run manifest. Faults are SQLite triggers applied to a vault copy of the ledger that the agent never sees; the incident's provider fixture and any precursor run live in the vault too. The supplied `incident/ledger.db` is a sanitized export of tables and rows only. Expected results are balance deltas plus the incident payment's row, so a pre-incident history can exist; error wording is matched per arm because each app's ordinary message is part of its diagnostics (R02).

## Pre-incident history (v2)

`history.py` runs N earlier payments through the arm's own entry point before the incident (distinct ids, destinations, amounts, simulated times over 30 days; about 10% time out first and are retried successfully). The ledger therefore has many rows and the traces arm has hundreds of records; the incident's evidence must be found by correlation. Trace timestamps are set to the simulated clock so they agree with ledger `created_at` values, identically across arms. History is built once per (arm, profile, precursor) per run and copied into every trial. Packaged fixture copies carry a neutral provenance note in every arm (pilot-v1 agents had reasoned about the repository's "hand-authored synthetic" label instead of the incident).

## Commands

```sh
uv sync --frozen                    # pinned openai SDK (3.8.0)
make preflight                      # validate OPEN_AI_API_KEY with GET /v1/models; no completions
make test                           # example tests + harness tests; no network
make parity                         # happy + S1–S5 across all arms, with a small history
make leak-check                     # 46 adversarial isolation probes
make estimate MANIFEST=benchmarks/troubleshooting/manifests/pilot.json
make qualify MANIFEST=...           # R08 qualification exercise (paid)
make pilot MANIFEST=...             # plan + execute (paid; resumable with --run)
make grade RUN=runs/<id>            # machine rubric + blinded review packets
make review ... / harness review    # record human verdicts
make analyze RUN=runs/<id>
```

`harness run --dry-run` executes the same pipeline with a scripted fake model and fictional prices. Generated runs live under `runs/` (gitignored).

## Configuration and secrets

Copy `.env.example` to `.env`. The key is read from `OPEN_AI_API_KEY` in `.env` only and passed explicitly to the SDK; the SDK's own environment lookup is never used, and tool subprocesses receive a minimal environment with no inherited variables. The preflight exits 2 (missing), 3 (auth), or 4 (network after bounded retries) with an `ESCALATE:` line; paid commands refuse to start unless it passes.

## Per-trial layout

```
runs/<run>/manifest.json            frozen manifest + harness hash, SDK/Python versions, prompt and schema hashes
runs/<run>/plan.json state.json     block order (seeded), per-trial status
runs/<run>/budget.json              cap, committed, reserved, unresolved
runs/<run>/trials/<trial>/
  workspace/                        README.md, app/, incident/, scratch/   (what the agent can read)
  vault/                            fault-bearing ledger, evaluator result  (never readable)
  workspace-manifest.json           every readable file with sha256
  requests.jsonl                    one row before each POST, one after; purposes preflight|solving
  responses/NNNN-*-{request,response}.json
  tool-events.jsonl tool-outputs/   every tool call, raw untruncated outputs
  submission.md/json summary.json grade.json
```

## Isolation

Every tool command and application run executes under a macOS Seatbelt profile (`sandbox-exec`): deny by default; read access to the system, the pinned interpreter, and the trial workspace; writes only to `scratch/` (plus a reproduction output directory during `reproduce_incident`); no networking; no process listing. Docker is not available on the development machine. `harness leak-check` attacks a built workspace with 23 probes per arm (parent listing, vault reads, trigger introspection, raw database bytes, `ps`, `sysctl`, repository and home reads, environment dumps, provider and inference hosts, DNS, writes into `app/` and `incident/`, symlink escape, previous-trial artifacts).

Path normalization (R02/R23): the real workspace path becomes `/workspace` and the interpreter prefix `/python` in every output, identically for all arms. No traceback frames are removed; the application runs as a subprocess, so no evaluator frames exist.

Inclusion rules (R20): production modules, the entry point, and the shared fixture library. Excluded from every arm: READMEs, demo scripts, tests, the fault adapter module, the comparison generator, evaluator outputs, and design documents. The clean app's test module reproduces the S2 mechanism, so tests are excluded symmetrically.

## Reproduction tool

`reproduce_incident` restores the immutable pre-incident snapshot (history included), applies the hidden environment, runs the operator's invocation, and writes sanitized output to `incident/reproductions/NN/`. It returns process output and exit status only. A recovery continuation (running the application against the post-incident ledger) is something the agent can do itself under `scratch/`; the tool always performs a fresh incident reproduction.

## Accounting

`harness/accounting.py` implements the design's field mapping, invariants, aggregation, and rate-card cost with Decimal arithmetic. Preflight token counts (`/v1/responses/input_tokens`) are logged with `purpose=preflight` and contribute nothing to solving totals. Missing usage is `null`, never zero; a trial with any unknown attempt keeps only a lower bound and its reserve stays unresolved in the budget file.

## Grading

`harness/grading.py` scores six dimensions with pattern checks plus mechanical citation existence, and flags disqualifiers (new identity, released funds, settlement claims, invented transfer ids). Fixture answers under `grading/fixtures/` cover correct, partial, unsafe, unsupported, and short-wrong submissions. Machine verdicts are provisional: `harness grade` writes blinded review packets (no model, tokens, or time) and `harness review` records the human verdict that becomes `final`. No model judge is used in the pilot.

## Required checks before declaring measurement ready

| Check (design) | Verification |
|---|---|
| A trial cannot read evaluator-only data, including via SQLite schema introspection or traceback paths. | `tests/test_isolation.py` (`LeakCheckTests`, `WorkspaceTests`), `make leak-check` |
| The ordinary traceback remains equally useful across all arms. | `tests/test_isolation.py::ParityTests`, `test_traceback_paths_are_normalized_and_useful` |
| Restarting the trial does not reuse consumed fixtures, model context, or cached repository summaries. | Fresh workspace, vault, and history per trial (`packaging.build_trial_workspace`, `TrialRunner.__init__`); `test_reproduction_is_fresh_sanitized_and_recorded`; `CrashRecoveryTests` |
| OA01–OA07 and V01–V12 pass. | `tests/test_accounting.py` (V01–V07), `tests/test_env_preflight.py` (V08, V12), `tests/test_inference.py` (V09, OA03, OA05, OA06), `tests/test_loop.py` (V04, V05, V08, V11), qualification run (V10, real calls) |
| Time/token/tool limits terminate runs and preserve their cost and transcript. | `test_token_cap_stops_before_sending`, `test_tool_and_inference_limits`, `test_time_limit_terminates_and_keeps_records` |
| A wrong but short answer cannot win an efficiency comparison. | `tests/test_grading.py::test_short_wrong_answer_cannot_be_correct`; `tests/test_analysis.py` (only correct trials enter consumption tables) |
| An unsupported settlement claim fails grading even with a transfer ID. | `tests/test_grading.py::test_settlement_claim_fails_even_with_transfer_id` |
| A clean run that uses more tokens remains in the published data. | `tests/test_analysis.py` (all attempts visible; no filtering by direction) |
| No measured agent calls or paid provider calls occur during ordinary example tests. | Example tests patch `socket.connect`; harness tests use in-process mock transports and the scripted fake; `NoPaidPathTests` |

Manual verification remaining: V10 (two-turn function-tool smoke test with real usage) and the model-specific acceptance of the OA03 settings happen in the paid qualification run, under the manifest's `qualification_usd_cap`.

## Evaluator rubric — keep out of agent workspaces

A correct submission must locate the failed boundary for its case, distinguish a returned transfer response from proof of settlement (S2) or preserve uncertainty (S3) or state that no request was made (S1), describe the retained reservation and missing posting (or untouched funds for S1), cite existing artifacts, give a verifiable reproduction with assertions, and recommend recovery that keeps the payment identity and reserved funds. See `harness/cases.py` for the per-case rubric text.
