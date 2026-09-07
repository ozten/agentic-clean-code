# Pilot retrospective: agent-troubleshooting measurements (pilot-v1)

Date: 2026-09-06. Run: `runs/pilot-v1` (sanitized bundle in `benchmarks/troubleshooting/results/pilot-v1/`).
Manifest `pilot-v1`: models gpt-5.6-luna (efficient) and gpt-5.6-terra (control), case S2 only, 3 arms x 3 repetitions
= 18 trials, batch cap $15.00, scheduler seed 20260906, harness source `ec764a13c486`,
openai SDK 3.8.0. Pilot results validate the protocol; they do not enter the main estimate (R16).

## Outcome in one paragraph

All 18 trials completed with complete telemetry, inside the cap, at a rate-card cost of $0.679
(expected estimate was $1.69; roughly 90% of input tokens were cache reads). Ten trials submitted a diagnosis; all ten were
correct on human review. Eight trials stopped at the 100,000 cumulative-token cap without submitting: every clean-with-traces
trial (6 of 6, both models) and two clean-no-traces trials. The simple arm submitted 6 of 6. On this smoke-test case the
token cap, not the model, decided the outcome for the arm with the most material to read. That is a ceiling effect on the
cap's own terms, and the main protocol must revisit the limit before any efficiency comparison can be made (R12, R35).

## Per-trial record

| # | model | arm | rep | stop | calls | tools | repro | tokens | cached % | output | reasoning | seconds | cost $ | machine | final |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-5.6-terra | simple | 3 | submitted | 14 | 14 | 1 | 67902 | 88 | 3954 | 1490 | 59 | 0.0783 | correct | correct |
| 2 | gpt-5.6-terra | clean-no-traces | 3 | submitted | 13 | 13 | 1 | 73284 | 82 | 3622 | 1242 | 64 | 0.0856 | partial | correct |
| 3 | gpt-5.6-terra | clean | 3 | token_limit | 15 | 15 | 1 | 94754 | 91 | 882 | 153 | 32 | 0.0486 | no_submission | no_submission |
| 4 | gpt-5.6-terra | clean | 1 | token_limit | 15 | 15 | 1 | 94488 | 90 | 1418 | 775 | 37 | 0.0561 | no_submission | no_submission |
| 5 | gpt-5.6-terra | simple | 1 | submitted | 15 | 15 | 1 | 77726 | 90 | 4545 | 1710 | 68 | 0.0857 | correct | correct |
| 6 | gpt-5.6-terra | clean-no-traces | 1 | submitted | 13 | 13 | 1 | 74057 | 88 | 3202 | 1225 | 55 | 0.0717 | partial | correct |
| 7 | gpt-5.6-luna | clean-no-traces | 3 | token_limit | 15 | 15 | 1 | 93428 | 80 | 1085 | 410 | 33 | 0.0075 | no_submission | no_submission |
| 8 | gpt-5.6-luna | clean | 3 | token_limit | 15 | 15 | 0 | 89836 | 91 | 605 | 16 | 33 | 0.0043 | no_submission | no_submission |
| 9 | gpt-5.6-luna | simple | 3 | submitted | 12 | 12 | 1 | 58825 | 88 | 2389 | 580 | 41 | 0.0055 | correct | correct |
| 10 | gpt-5.6-terra | clean | 2 | token_limit | 15 | 15 | 1 | 94751 | 91 | 851 | 151 | 31 | 0.0480 | no_submission | no_submission |
| 11 | gpt-5.6-terra | clean-no-traces | 2 | token_limit | 15 | 15 | 1 | 88647 | 89 | 2554 | 1492 | 52 | 0.0700 | no_submission | no_submission |
| 12 | gpt-5.6-terra | simple | 2 | submitted | 15 | 15 | 1 | 77355 | 90 | 3885 | 1406 | 65 | 0.0782 | correct | correct |
| 13 | gpt-5.6-luna | simple | 1 | submitted | 13 | 13 | 1 | 66295 | 96 | 2849 | 1100 | 55 | 0.0052 | correct | correct |
| 14 | gpt-5.6-luna | clean-no-traces | 1 | submitted | 16 | 16 | 1 | 98586 | 83 | 2959 | 972 | 59 | 0.0093 | correct | correct |
| 15 | gpt-5.6-luna | clean | 1 | token_limit | 15 | 15 | 0 | 91806 | 81 | 607 | 16 | 31 | 0.0064 | no_submission | no_submission |
| 16 | gpt-5.6-luna | clean-no-traces | 2 | submitted | 14 | 14 | 1 | 84665 | 91 | 2397 | 806 | 51 | 0.0063 | correct | correct |
| 17 | gpt-5.6-luna | simple | 2 | submitted | 13 | 13 | 1 | 67844 | 88 | 2635 | 794 | 47 | 0.0063 | partial | correct |
| 18 | gpt-5.6-luna | clean | 2 | token_limit | 15 | 15 | 1 | 90524 | 83 | 690 | 74 | 33 | 0.0062 | no_submission | no_submission |

## Counting

- Solving inference attempts: 258; every attempt has a `sent` row before its terminal row and complete usage.
- Independent raw-JSON sums equal `summary.json` totals in 18/18 trials (V10 cross-check).
- The `/v1/responses/input_tokens` preflight matched billed `input_tokens` on every call (0 mismatches logged).
- Every response returned `model` equal to the requested alias (no dated snapshot was ever reported), `service_tier=default`,
  `store=false`, `truncation=disabled`, `parallel_tool_calls=false`, and reasoning `effort=medium, context=all_turns`.
- Usage invariants (C + W <= I, R <= O, T = I + O) held on every response; `cache_write_tokens` was populated on first calls.
- Cache read fraction of input, median across trials: 89% (min 80%, max 96%).
  Dollar cost is therefore far below the all-input-at-standard-rate sensitivity figure; report both (R41).
- Budget file: committed $0.67923179, unresolved $0, refusals 0. The token-count endpoint produced no
  visible charge in this run, but its pricing remains unverified on the pricing page.

## Packaging and isolation

- Parity held for S1-S3 across arms; 46 adversarial probes passed before the run. No agent command attempted to leave the
  workspace or reach the network: the only `..` uses were `cd scratch && ../incident/...` inside the workspace, and no
  command invoked `ps`, `sysctl`, `curl`, or host paths.
- Every trial used `reproduce_incident` at least once; agents also copied `incident/ledger.db` into `scratch/` for inspection,
  and one control trial ran a recovery continuation against a scratch copy (the design's intended distinction held).
- Several agents noticed the fixture provenance line ("hand-authored synthetic fixture") and the offline fixture transport,
  and reasoned explicitly that "no real provider" could be established. That is honest, but it is meta-knowledge about the
  demo rather than about the incident. For the main batch consider neutralizing the provenance strings in packaged fixtures
  (identically across arms) and re-freezing the case digests.
- Arms without traces cannot know the transfer id (`tr_demo_500`) because it was never persisted; they correctly said "a
  validated transfer response was received". The rubric originally demanded the id and was corrected (see grading).
- The workspace brief (`README.md`) is itself a readable file and was re-read by several agents before submitting; it is in
  the manifest and counts toward input as intended (R24).

## Grading

- Machine rubric before calibration: 3 correct, 3 partial, 4 unsafe. All four "unsafe" flags were false positives:
  negated lists ("do not delete the row, release its reservation, or create another ID"), the normal posting step ("moves
  reserved to contractor"), and a suggested test fixture id (`tr_test`). Two "partial" verdicts came from backticked field
  names defeating the local-state patterns.
- After calibration (negation across list items, posting-step exclusion, disqualifiers scanned only in claim/recommendation
  fields, transfer-id requirement relaxed for no-trace arms): 7 correct, 3 partial, 0 unsafe. The three remaining are
  external-outcome phrasing the patterns do not recognize ("reached confirm with a receipt"). Machine verdicts stay
  conservative; the human verdict is final. Grading fixtures still pass.
- Human review was done by the session operator (Claude), who also ran the trials and could infer the arm from cited
  file names: not blind (R53 acknowledges arm blinding is incomplete). The owner should spot-check the review packets
  under `runs/pilot-v1/review/` before the main batch.
- A wrong-but-short answer cannot win: no such answers occurred; all submissions were long and grounded.

## Limits, ceiling, and floor effects

- Time: median 49 s per trial against a 720 s limit; never binding.
- Inference/tool limits (40 each): never binding; median 15 calls.
- Token cap (100,000 cumulative input+output across calls, R35/R40): binding in 8 of 18 trials. Because history is resent
  on every call, each call costs roughly the full context (7-10k tokens here), so the cap permits about 10-14 calls
  regardless of how efficient each step is. The clean arm has more files (four modules, three traces) and every agent
  chose to read all of them before submitting; the traces arm therefore ran out of budget one or two calls before its
  submission. Cache reads made these tokens nearly free in dollars but they count in full toward the metric.
- Correctness is at ceiling (10/10 submissions correct, including the efficient model), so on S2 the experiment cannot
  distinguish arms by correctness; only consumption differs, and consumption is truncated by the cap.
- Consequence for the main protocol (protocol change, new experiment version, owner approval): either raise the cumulative
  cap (e.g. 300k, which at the observed cache ratio keeps a terra trial under ~$1 worst case) or budget by per-call context
  plus a call limit. Keeping 100k would pre-decide the clean arm's failure on this app.

## Other observations

- Paired comparisons that qualify: clean-no-traces vs simple only (luna 2 pairs, median +24,556 tokens; terra 2 pairs,
  median +856 tokens). No pair includes the traces arm. These are pilot numbers on one case; do not report them as results.
- Agents in the simple arm read one 100-line file; agents in clean arms read four modules totalling more lines. The
  architecture package costs reading tokens up front on a small app; whether traces shorten reconstruction cannot be seen
  until the cap stops truncating the traces arm.
- No transport errors, timeouts, rate limits, refusals, or incomplete generations occurred; those paths remain covered
  by tests only.

## Checklist status (design "required checks before declaring measurement ready")

Isolation, traceback parity, fresh restart, OA01-OA07/V01-V12, limits, short-wrong-answer, settlement-claim, and
no-paid-calls-in-tests are verified by tests and by this run (V10 by the qualification run and the 18/18 raw-sum check).
Open before the main batch: the token-limit decision above, fixture provenance neutralization, and an owner review of grades.

## Decisions taken after review (2026-09-06, owner)

1. Cumulative token cap raised from 100,000 to 300,000 for the next experiment version (`pilot-v2`). Rationale: the
   cap counts resent context on every call and truncated every traces-arm trial before submission.
2. Packaged fixture copies carry a neutral provenance note in every arm; repository files keep their honest label.
3. The pilot-v1 grades stand as reviewed by the session operator; the owner reviews the next run's disputed grades.
4. Scope added: pre-incident payment history (120 payments) so incident evidence must be found by correlation, and two
   cases whose traceback does not name the boundary: S4 `response-mismatch` (validation rejects a received response;
   only the traces arm can see the body) and S5 `stale-retry` (a 24-hour-old timed-out attempt makes the retry-window
   rule fire before any provider request). Case versions are now 2; pilot-v1 numbers are not comparable with v2.

`pilot-v2` (manifest `benchmarks/troubleshooting/manifests/pilot-v2.json`): 2 models x 3 arms x 5 cases x 2 repetitions
= 60 trials; rate-card worst case $119.30 (terra $3.60/trial at the 300k cap), expected about $4.50 at pilot-v1 cache ratios.

## Pilot-v2 (2026-09-06): history, S1-S5, 300k cap

Run `runs/pilot-v2` (sanitized bundle `benchmarks/troubleshooting/results/pilot-v2/`): gpt-5.6-luna and gpt-5.6-terra, 3 arms x 5
cases x 1 repetition = 30 trials, 120-payment history in every workspace, cumulative cap 300,000, batch cap $65.00.

### Outcome

All 30 trials completed with complete telemetry at a rate-card cost of $1.92 (expected estimate $2.48).
25 trials submitted; all 25 were correct on review (details below). Five trials hit the 300k cap without submitting, and all
five are the clean-with-traces arm (S4 both models, S1 control, S2 control, S5 efficient). The traces arm submitted in the other
five of its ten trials (S3 both models, S1 efficient, S2 efficient, S5 control), all correct, at 244k-293k tokens. The simple
arm submitted 10/10 and the no-trace clean arm 10/10.

Raising the cap from 100k to 300k moved the traces arm from 0/6 submissions in pilot-v1 to 5/10 here, but the arm still runs
about 2-3x the tokens of the other arms and sits at the edge of the new cap. The history made the trace directory large
(about 360 records): a depth-4 `list_files` or a broad search over `incident/traces` returns the 16 KiB maximum, and that
text is resent on every later call. Median cache-read share of input: 85%.

| case | arm | submitted | correct | cap stops | tokens (efficient / control; * = cap) |
| S1 | simple | 2/2 | 2/2 | 0 | 88526 / 112605 |
| S1 | clean-no-traces | 2/2 | 2/2 | 0 | 125876 / 138038 |
| S1 | clean | 1/2 | 1/2 | 1 | 268901 / 289651* |
| S2 | simple | 2/2 | 2/2 | 0 | 90861 / 70838 |
| S2 | clean-no-traces | 2/2 | 2/2 | 0 | 132204 / 100357 |
| S2 | clean | 1/2 | 1/2 | 1 | 293072 / 284918* |
| S3 | simple | 2/2 | 2/2 | 0 | 61460 / 81994 |
| S3 | clean-no-traces | 2/2 | 2/2 | 0 | 88237 / 86931 |
| S3 | clean | 2/2 | 2/2 | 0 | 243099 / 285460 |
| S4 | simple | 2/2 | 2/2 | 0 | 75424 / 80516 |
| S4 | clean-no-traces | 2/2 | 2/2 | 0 | 126695 / 114434 |
| S4 | clean | 0/2 | 0/2 | 2 | 279461* / 284693* |
| S5 | simple | 2/2 | 2/2 | 0 | 89123 / 73269 |
| S5 | clean-no-traces | 2/2 | 2/2 | 0 | 138946 / 82253 |
| S5 | clean | 1/2 | 1/2 | 1 | 296414* / 263953 |

### What the harder cases showed

- S4 (mismatched response): every arm that submitted identified response validation as the boundary. The no-trace arms said,
  honestly, that the artifacts do not retain which field mismatched; only a traces-arm agent could have read the body, and
  both traces-arm S4 trials ran out of budget after finding the right trace by correlating the global trace id.
- S5 (stale retry): all six trials submitted and all were correct. The control model's traces-arm answer cited the earlier
  attempt's TimeoutError trace directly; the no-trace arms inferred the earlier attempt from `created_at` being 24 hours old
  and kept its outcome unknown. Reconstruction from state alone succeeded here.
- S1 and S3 behaved as in pilot-v1; S2 remains at ceiling.
- Correctness therefore stays at ceiling for every arm that finishes: 25/25. The experiment on these cases measures reading
  and correlation cost, and the traces arm pays the most of it on this app.

### Counting, packaging, grading

- Independent raw-JSON sums equal summary totals in 30/30 trials; token-count preflight matched billed input on every
  call (0 mismatches). Returned model/tier were as requested on every response.
- Agents correctly read history rows as unrelated (e.g. "120 payments, 120 postings, none for milestone-42"), and used
  `reproduce_incident` in every trial. No command touched anything outside the workspace.
- The neutral fixture label removed the "this is a demo" reasoning seen in pilot-v1; agents now describe the fixtures as
  recorded playback and still refuse to treat them as proof of live provider state, which is the intended behaviour.
- Machine rubric vs. session review before calibration: 10 correct, 13 partial, 2 unsupported; every difference was a
  pattern gap (a timeout branch mentioned as *not* taken, "no local posting", a transfer id cited from the fixture library,
  a mangled trace GUID in one citation). After calibration the machine agrees with the human verdict on 17/25 trials.
  Review was again by the session operator, not blind to arm. Flagged for owner review: trial #25 (S1, clean, efficient),
  whose evidence cites one trace path with a mistyped GUID.

### Per-trial record

| # | model | case | arm | stop | calls | tokens | cached % | seconds | cost $ | machine | final |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-5.6-luna | S4 | simple | submitted | 11 | 75424 | 82 | 57 | 0.0080 | partial | correct |
| 2 | gpt-5.6-luna | S4 | clean-no-traces | submitted | 15 | 126695 | 74 | 56 | 0.0130 | correct | correct |
| 3 | gpt-5.6-luna | S4 | clean | token_limit | 15 | 279461 | 80 | 41 | 0.0201 | no_submission | no_submission |
| 4 | gpt-5.6-luna | S3 | clean | submitted | 15 | 243099 | 90 | 48 | 0.0131 | correct | correct |
| 5 | gpt-5.6-luna | S3 | simple | submitted | 11 | 61460 | 82 | 45 | 0.0061 | correct | correct |
| 6 | gpt-5.6-luna | S3 | clean-no-traces | submitted | 13 | 88237 | 86 | 44 | 0.0070 | correct | correct |
| 7 | gpt-5.6-terra | S2 | simple | submitted | 11 | 70838 | 81 | 71 | 0.0913 | correct | correct |
| 8 | gpt-5.6-terra | S2 | clean-no-traces | submitted | 13 | 100357 | 85 | 61 | 0.0957 | partial | correct |
| 9 | gpt-5.6-terra | S2 | clean | token_limit | 17 | 284918 | 84 | 49 | 0.1838 | no_submission | no_submission |
| 10 | gpt-5.6-terra | S1 | clean | token_limit | 17 | 289651 | 92 | 53 | 0.1372 | no_submission | no_submission |
| 11 | gpt-5.6-terra | S1 | clean-no-traces | submitted | 16 | 138038 | 89 | 84 | 0.1091 | correct | correct |
| 12 | gpt-5.6-terra | S1 | simple | submitted | 14 | 112605 | 88 | 79 | 0.1098 | partial | correct |
| 13 | gpt-5.6-terra | S5 | clean-no-traces | submitted | 12 | 82253 | 85 | 50 | 0.0807 | partial | correct |
| 14 | gpt-5.6-terra | S5 | simple | submitted | 11 | 73269 | 85 | 54 | 0.0765 | correct | correct |
| 15 | gpt-5.6-terra | S5 | clean | submitted | 16 | 263953 | 83 | 64 | 0.1937 | partial | correct |
| 16 | gpt-5.6-terra | S3 | simple | submitted | 12 | 81994 | 87 | 49 | 0.0733 | correct | correct |
| 17 | gpt-5.6-terra | S3 | clean | submitted | 17 | 285460 | 92 | 62 | 0.1433 | correct | correct |
| 18 | gpt-5.6-terra | S3 | clean-no-traces | submitted | 13 | 86931 | 85 | 50 | 0.0806 | correct | correct |
| 19 | gpt-5.6-luna | S5 | clean | token_limit | 16 | 296414 | 91 | 39 | 0.0138 | no_submission | no_submission |
| 20 | gpt-5.6-luna | S5 | simple | submitted | 12 | 89123 | 82 | 50 | 0.0086 | correct | correct |
| 21 | gpt-5.6-luna | S5 | clean-no-traces | submitted | 16 | 138946 | 78 | 58 | 0.0132 | correct | correct |
| 22 | gpt-5.6-terra | S4 | clean | token_limit | 17 | 284693 | 83 | 50 | 0.1864 | no_submission | no_submission |
| 23 | gpt-5.6-terra | S4 | clean-no-traces | submitted | 14 | 114434 | 88 | 71 | 0.0926 | correct | correct |
| 24 | gpt-5.6-terra | S4 | simple | submitted | 12 | 80516 | 86 | 65 | 0.0881 | correct | correct |
| 25 | gpt-5.6-luna | S1 | clean | submitted | 16 | 268901 | 91 | 69 | 0.0151 | unsupported | correct |
| 26 | gpt-5.6-luna | S1 | clean-no-traces | submitted | 16 | 125876 | 82 | 55 | 0.0109 | correct | correct |
| 27 | gpt-5.6-luna | S1 | simple | submitted | 13 | 88526 | 86 | 54 | 0.0083 | correct | correct |
| 28 | gpt-5.6-luna | S2 | clean-no-traces | submitted | 16 | 132204 | 79 | 61 | 0.0129 | correct | correct |
| 29 | gpt-5.6-luna | S2 | simple | submitted | 14 | 90861 | 87 | 55 | 0.0076 | partial | correct |
| 30 | gpt-5.6-luna | S2 | clean | submitted | 18 | 293072 | 84 | 58 | 0.0196 | partial | correct |

### Open decisions before P8

1. The cumulative cap still truncates the traces arm on a small app with a large trace directory. Options: raise again,
   budget per call, or summarize very large directories in `list_files` (arm-neutral tool change) so listing 360 trace
   directories does not cost 16 KiB per subsequent call.
2. Cases where correctness is not at ceiling remain to be designed; on S1-S5 both models are correct whenever they finish.
3. Owner review of flagged trial #25 and a spot-check of the pilot-v2 packets under `runs/pilot-v2/review/`.
