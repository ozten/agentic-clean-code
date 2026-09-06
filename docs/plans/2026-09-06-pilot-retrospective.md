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
