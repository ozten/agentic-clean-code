# Design: measure coding-agent troubleshooting effort

Status: Implementation specification; OpenAI API-key access selected; execution pending

Date: 2026-09-06

Owner: Austin King

Revision: OpenAI Responses API and exact usage accounting prescribed on 2026-09-06.

## Outcome

Produce reproducible measurements and a short, honest visual comparison of agents investigating equivalent payment failures in two Python applications. Measure whether explicit architecture and boundary traces help an agent reach a correct, evidence-supported diagnosis with less effort. Results may support, qualify, or contradict that hypothesis.

This document specifies work; it does not authorize or perform paid agent runs, implement a runner, select final model versions, or report results. The [benchmark harness](../../benchmarks/troubleshooting/README.md) now implements packaging, isolation, the Responses tool loop, accounting, scheduling, grading, and analysis (P1–P6); paid execution still requires an approved manifest. This design is authoritative where the older scaffold still leaves provider, authentication, or accounting choices open.

## Decisions to carry forward

1. Keep both apps in Python, using the same interpreter and equivalent payment behavior.
2. Use one efficient OpenAI model and one stronger OpenAI control model through the same API-key-authenticated Responses API harness. Compare architecture arms within each model first.
3. Begin with diagnosis and a reproduction procedure, not a code-repair contest. The current incident is an injected environment failure; both apps already preserve funds correctly.
4. Treat correctness as the gate for efficiency claims. Short incorrect answers do not count as successful troubleshooting.
5. Keep each fixture adapter simple: one explicitly selected request/outcome per invocation. A state machine is not a prerequisite.
6. Observe real searches and tool use without scripting an inefficient route for the baseline or an efficient route for the clean app.
7. Include a clean-app-without-traces arm to separate some of the effect of recording from the broader architecture package.
8. Require exact per-response API usage; subscription sessions, estimated transcript token counts, and incomplete usage totals cannot enter the exact-token comparison.
9. Keep rich implementation details in the repository. Show an outcome, observed troubleshooting steps, and a small amount of measured evidence in the five-minute talk.

## Questions and claims

| ID | Question | Evidence needed |
|---|---|---|
| Q1 | Does the clean app with traces reduce troubleshooting tokens at acceptable correctness? | Correctness, failures, and token distributions for matched trials. |
| Q2 | How much of the difference comes from traces? | Compare identical clean code with and without recorder wiring. |
| Q3 | Can an efficient model diagnose successfully with this evidence? | Its own success rate and consumption in every arm, plus a stronger control. |
| Q4 | Does evidence reduce reconstruction work? | Observable tool actions and grounded conclusions, not inferred private reasoning. |
| Q5 | Does the effect persist across different failure locations? | A small, fixed scenario suite; distinguish scenarios from repeated runs. |

Do not claim that the experiment proves hexagonal architecture always wins, that generated scripts are generally poor, or that a particular harness produced this baseline. Both apps were hand-authored here. This is a controlled example, not a representative sample of all generated projects.

The experiment starts after the application and incident evidence exist. It does not establish faster initial implementation, cheaper lifetime maintenance, or the effect of adding Markdown guidance to a fresh coding task. Those would need separate experiments. Neither app currently has an enforced static type-checking gate; do not attribute results to type checking.

## Experimental arms

| ID | Source and wiring | Agent evidence |
|---|---|---|
| A: `simple` | Direct Python workflow with SQLite and request handling together. | Ordinary output, full application traceback, equivalent incident state. |
| B: `clean` | Core interfaces, injected adapters, HTTP and ledger recorders. | The same classes of output/state plus correlated boundary traces. |
| C: `clean-no-traces` | Identical clean implementation with recorders omitted. | Ordinary output, full application traceback, equivalent incident state. |

R01. Every arm must retain the same request identity, currency/amount, destination, validation, reservation behavior, and atomic local-posting semantics for the selected case. Test happy-path and failure-state parity before agent trials.

R02. Preserve useful ordinary diagnostics in A and C. Do not strip traceback frames, obscure variable names, pad source files, remove useful tests, or introduce avoidable defects to make B look better. Normalize only environment-specific path prefixes and evaluator-only frames, consistently across arms.

R03. Give all arms the same business brief, allowed tools, initial report, and evidence-directory discovery instructions. Use neutral workspace names such as `/workspace/app` and `/workspace/incident`, not labels like `bad-code` or `best-architecture`.

R04. Keep production source and naturally available artifacts discoverable; do not preload every file into the prompt. Reading traces consumes context and counts toward usage. Do not tell B which trace contains the answer while giving A an open-ended task.

R05. Interpret B versus C as the incremental effect of recording in this clean implementation. Interpret A versus B as a package comparison. A versus C still differs in code organization and interface annotations; none of these alone isolates every architectural feature.

R06. Optional follow-up: add ordinary structured logging to A and repeat the comparison. This tests whether a simpler intervention supplies the important evidence. Another separate experiment can compare agent-created apps with and without the Markdown guidance. Neither extension belongs in the first measurement batch.

## OpenAI access and harness contract

OA01. Use **OpenAI API keys with API billing**, loaded from `OPENAI_API_KEY` in the runner process. Require a dedicated OpenAI project for the experiment and record its project ID. No subscription/OAuth login, browser session, provider proxy, or automatic fallback is permitted in this experiment. Missing credentials must fail before a trial starts. The key must not appear in manifests, command lines, transcripts, application traces, or the solving sandbox's environment. Only the host-side inference client receives it. See [API authentication](https://developers.openai.com/api/reference/overview#authentication).

OA02. Implement one small Python tool loop using the pinned official `openai` SDK and `POST https://api.openai.com/v1/responses`. Pin the SDK version in the implementation's dependency lock file and the harness source hash in the experiment manifest. Use local function tools for file inspection, shell commands, and the isolated reproduction service. Do not use hosted web/file search, hosted code execution, subagents, or an uninstrumented commercial coding CLI in the measured run. This measures our controlled agent harness, not a named product's default behavior.

OA03. Each model request must set `stream=false`, `store=false`, `background=false`, `service_tier="default"`, `parallel_tool_calls=false`, and `truncation="disabled"`. Preserve the requested model/settings and the returned model/service tier. An unexpected model or tier invalidates the controlled trial and pauses scheduling. No hidden compaction, summarization, model routing, or implicit auxiliary LLM calls. Require a qualifying model pair that supports the specified interface; do not silently drop unsupported settings. These are experiment choices using the [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create).

OA04. Maintain complete conversation history explicitly in the runner. Do not use `previous_response_id` or shared Conversations. Preserve full model output items and function-call IDs before appending tool results, including opaque reasoning items when returned. Never try to decode or display encrypted reasoning. Start every trial with new history. Fix reasoning effort to `medium` for both selected reasoning models; pin the reasoning-context policy per model when supported and document it. Do not vary temperature or invent unsupported determinism settings. See [stateless reasoning continuity](https://developers.openai.com/api/docs/guides/reasoning#preserve-reasoning-without-stored-responses).

OA05. Disable SDK automatic retries, and verify with a transport stub that an injected connection error or 429 produces exactly one inference POST. In measured trials, terminate on a transport/API error instead of retrying invisibly. A replacement is a new trial under the predeclared infrastructure-failure policy. A timeout does not establish zero billing: retain its request identity and mark usage unknown when no terminal usage is available.

OA06. Log a locally generated attempt UUID before sending each request; send it as `X-Client-Request-Id`. Persist `x-request-id` when returned, the response `id`, request payload/hash, returned status, error/incomplete reason, complete response JSON, and raw `usage`. Flush the response record before executing its tool calls. Aggregate each inference attempt once; duplicate response-log ingestion must not increase totals. Preserve a request ledger even if the process crashes before a response is recorded.

OA07. Model IDs remain mandatory manifest values selected and qualified before the pilot; there is no runtime default model. Both must be OpenAI API models available to the experiment project. Record exact snapshots where supported. The efficient/stronger labels are selection roles, not measured results. Neither API account setup nor future paid trials are performed by editing this document.

## Model and harness selection

Use an efficient, lower-cost model that can already use the selected harness competently. A less capable model is interesting because the talk asks what engineering work becomes affordable; it is not useful if it fails basic file reading or tool calls. Pair it with a stronger model supported by the same harness.

R07. Select two exact OpenAI Responses model IDs at implementation time after checking project access, current prices, and the OA01–OA07 contract. Save the qualification results and model documentation URLs. The endpoint, provider, API-key authentication, and usage fields are already fixed by this design.

R08. Run a small harness qualification exercise unrelated to the payment incidents: inspect a small Python file, execute a supplied test, and return a grounded answer. Qualification tests tool competence; do not select a model by which one produces the largest architecture gap.

R09. Use the same versioned Python Responses tool loop, instructions, tool schemas, permissions, and limits across arms. Record model and SDK versions. No model fallback or alternative harness is allowed within a batch.

R10. Set reasoning effort to `medium` and pin any supported reasoning-context setting in the manifest. Qualify support before trials. Keep these settings constant across arms. Within-model token comparisons are primary; cross-model consumption and dollar comparisons remain separate.

R11. A stronger model is a robustness check, not a rescue agent for the efficient model. Each trial starts fresh. No second agent, reviewer agent, or model escalation in measured solving runs initially. Grader usage is separate.

R12. If a model fails almost every pilot trial in every arm, retain that pilot result and reconsider task/model fit before a new frozen experiment. If all arms solve immediately, report the ceiling; do not weaken models or hide diagnostics until a desired difference appears. A null result on this small app is useful.

## Scenarios and sample sizes

Use sequential, single-worker payments and synthetic external responses. Preserve the same application-visible condition across arms.

| Case | Environmental outcome | Required distinction |
|---|---|---|
| S1: preparation fails | Local durable preparation fails before an external submission. | No provider request was made; no committed reservation/posting. |
| S2: confirmation fails | Provider response returns a transfer ID; local confirmation transaction fails. | Provider response received, local reservation retained, no committed posting. |
| S3: response is lost | Submission produces a timeout with no response available to the application. | Remote outcome remains unknown; retain reservation and retry identity. |

R13. Treat the existing S2 trigger scenario as a smoke test and possible presentation example. It is intentionally small; its full traceback may already make diagnosis easy. Do not assume many grep calls are necessary.

R14. Implement S1 and S3 equivalently in both apps before the main batch. A selected invocation needs only one provider response or timeout. Use the same opaque reproduction boundary for both arms; do not require a stateful provider simulator.

R15. A clean-only trace-sink failure is valuable for architecture testing, but is not a matched main-suite case because A has no recorder. Keep that existing regression test outside the comparative aggregate.

R16. Proposed pilot: 2 models × 3 arms × 1 smoke-test case × 3 repetitions = 18 trials. Use it to validate isolation, counting, grading, limits, and ceiling/floor effects. Pilot trials do not enter the final estimate after the protocol changes.

R17. Proposed main batch: 2 models × 3 arms × 3 cases × 10 repetitions = 180 trials. This is a practical descriptive sample, not a power calculation. Repetition estimates variability on these cases; it does not turn three incidents into 180 independent software problems. If funds/time require fewer trials, record the reduced fixed count before launching, and label results exploratory.

R18. Match trials by `(model, case, repetition)` into blocks containing A, B, and C. Shuffle arm order using a recorded scheduler seed. This seed controls assignment, not model determinism. Do not run all A trials first and B trials later. Initially run at low fixed concurrency to reduce machine-load variation.

## Isolation and leakage prevention

The current artifacts are a demonstration bundle, not yet a safe agent-evaluation package. Merely asking the agent not to inspect evaluator files is insufficient.

R19. Build a fresh isolated filesystem/process environment per trial. Include only that arm's application source, neutral setup information, allowed ordinary fixtures, and incident evidence. Do not mount the parent repository, home directories, prior conversations, other trial outputs, global skill libraries, or evaluator credentials.

R20. Exclude this design, the benchmark README, `compare.py`, `evaluator-result.json`, solution-oriented tests, demo scripts that narrate the answer, the talk, and the adoption ADR. Ordinary tests may remain only if they do not reveal the exact incident; document identical inclusion rules. This first experiment measures architecture/artifacts, not the effect of supplying the answer in an ADR.

R21. The current SQLite trigger is visible through `sqlite_master`. Do not copy it into the agent's incident database. Export only application schema/data into a fresh snapshot, or enforce a genuine process/filesystem boundary that keeps fault injection outside the workspace. Test explicitly that trigger text and evaluator paths cannot be recovered from the supplied snapshot or traceback.

R22. Likewise, the source must not embed the selected incident's trigger, a hardcoded chosen response, or a helper called `fail_confirmation` that supplies the answer. Normal success/error fixture libraries may be available equally, but the mapping identifying the incident's external outcome belongs to the external test environment. Do not hide ordinary application code just because it is useful evidence.

R23. Tracebacks must retain actual application failure locations for all arms. Remove only evaluator-side frames/path disclosures under a documented common policy. Inspect serialized trace metadata for host paths and hidden case names as well.

R24. Disable conversation carryover, personal memory, automatic repository indexing across trials, and untracked background agents. Persist a manifest of exactly what the agent could read. Capture any harness auto-loaded instructions and account for their input tokens.

R25. The solving environment may run local Python/tests and inspect its snapshot. Its only external execution endpoint is the provided reproduction tool. The harness's model connection is outside the application sandbox. Block payment-provider traffic and unrelated network access, without blocking the inference connection needed to run the trial.

R26. Add adversarial isolation checks before paid evaluation: attempts to list parent directories, inspect process commands, open evaluator paths, query database triggers, or read previous trial artifacts must not reveal the answer. A container without the relevant mounts may suffice; a directory convention alone does not.

## Reproduction tool contract

R27. Provide the same named reproduction command/tool to all arms. It resets a disposable copy of the supplied application state and runs the incident under a hidden, fixed environment. It returns ordinary process output/exit status and any artifacts that arm naturally produces. It must not return the root-cause label or an evaluator summary.

R28. Executing reproduction is observation, not an oracle. For S3, the tool must preserve uncertainty rather than returning an authoritative remote-transfer count unavailable to the application.

R29. Keep an immutable incident snapshot and write re-runs to new directories. Record every reproduction invocation in the agent event stream. Reset external fixture consumption and local state before each requested fresh run; document how a recovery continuation differs from a fresh incident reproduction.

R30. Keep fault injection outside agent-readable source and process metadata. For the first diagnosis-only phase, application source can be read-only while a scratch directory remains writable. Implementing and evaluating a regression test is a later phase unless the runner can safely run submitted tests without exposing the oracle.

R31. Do not use one shared remote fixture service whose consumed state leaks across trials. Each invocation receives its explicit outcome independently. Avoid building WireMock-style state machinery for these three cases.

## Task and stopping behavior

R32. Start from the existing [task prompt](../../benchmarks/troubleshooting/task.md), but make submission requirements explicit: identify the failed boundary, cite the evidence, distinguish known and unknown remote state, describe local state, give a deterministic reproduction procedure and assertions, and recommend safe recovery. Do not name the fault location in the prompt.

R33. Supply a common, short statement of payment semantics, including stable retry identity, reservation rules, and the permitted retry window. Do not make one model's provider-documentation recall a hidden requirement. No web browsing is needed to solve these local cases.

R34. A concise final answer is allowed. Do not require hidden chain-of-thought, narration after every command, a minimum number of searches, or a prescribed troubleshooting sequence. A correct answer grounded in existing artifacts need not rerun the app if its reproduction procedure is verifiable.

R35. Stop on the first completed final submission, 12 minutes elapsed, 40 inference calls, 40 local tool invocations, or 100,000 cumulative API-reported input-plus-output tokens, whichever limit is reached first. Set an 8,192-token maximum generated output per inference call, including reasoning, with the budget reduction below. A response ending `incomplete` at its generation limit is an unsuccessful `generation_limit` stop, not a correct final answer; include its usage. These pilot limits may change only in a versioned manifest before the main batch, equally across arms.

R36. Before each inference call, count the exact pending model input through `POST /v1/responses/input_tokens`, using the same model, history, instructions, tool schemas, and supported rendering settings as generation. Log that preflight separately. Let `B = 100000 - observed_total_tokens`; use `max_output_tokens = min(8192, B - counted_input_tokens)`. If fewer than 1,024 output tokens remain, or context cannot fit the request, stop without sending generation. Apply the per-call deadline `min(120 seconds, remaining trial time)`; include counting latency in elapsed trial time. Actual returned usage is authoritative; a count mismatch or cap overrun pauses the batch for investigation. Counting is a preflight, not solving usage; do not add its input-count result to inference totals. See [token counting](https://developers.openai.com/api/docs/guides/token-counting).

R37. All sent inference attempts remain in the ledger, including errors, refusals, incomplete responses, and timeouts. Missing terminal usage is `unknown`, never zero. Preserve the trial as `telemetry_incomplete`, keep it in the attempted-trial report, exclude it from exact-token aggregates, and display known consumption as a lower bound. Apply a separate, predefined correctness/infrastructure classification. Replacements receive new IDs and cannot erase the original attempt.

## Usage and event collection

R38. Persist non-streaming Responses API response JSON and its exact `usage` object for every inference attempt with a returned response. No rounded UI counters, transcript retokenization, or SDK run-level totals are acceptable as the primary source. SDK aggregate totals may be compared against the independently summed response ledger as a check.

R39. Use the fixed OpenAI field mapping and equations in the accounting contract below. Cached input and cache-write input are breakdowns of input; reasoning is a breakdown of output. Never sum those breakdowns on top of their parent totals. Validate integers, ranges, and total equality on every response.

R40. Primary metric: `trial_total_tokens = sum(response.usage.input_tokens + response.usage.output_tokens)` across every solving inference attempt with complete telemetry, including unsuccessful attempts. Count repeated context at each call. Publish input, output, cached input, cache-write input, and reasoning subtotals. A trial with any unknown inference usage has no exact total; retain only its known lower bound. Preflight requests, grading, and setup belong to separate ledgers.

R41. Use provider-default caching behavior without trial-specific prompt padding or arm-specific cache tuning. Record effective model caching settings and `cached_tokens`/`cache_write_tokens`. Do not claim fresh history guarantees a cold provider cache. Randomize arm order, report cache fractions, and calculate observed-cache cost separately from a clearly labeled all-input-at-standard-rate sensitivity estimate.

R42. Capture all tool calls, arguments, start/end times, exit codes, and outputs actually delivered to the model. Keep untruncated raw tool outputs separately if supported, marking how much was returned. Apply identical output-size limits across arms; proposed initial cap is 16 KiB per tool output, with explicit truncation metadata and a common way to read more.

R43. Disable extra inference paths and compaction in this controlled harness. Every inference POST must have a ledger entry. Any unaccounted model call, missing usage, or unexpected API surface makes exact telemetry incomplete and pauses scheduling. Do not degrade silently to an estimated total; the runner must satisfy this contract before the main batch.

R44. Extend the record template with OpenAI project/model/SDK identifiers, request-ledger paths, preflight counts, exact usage fields and derived totals, telemetry completeness, pricing snapshot ID, spend reserves, and stop reasons. Also record source, incident, prompt, tool-schema and manifest hashes; Python/platform settings; and raw request/response artifacts. Never store the API key.

R45. Collect a coarse action taxonomy from observable tool activity: discover files, search text, read source, read incident evidence, query local state, reproduce/test, and other. Preserve raw events. A single shell call can do several things; annotate compound commands as multiple subactions only when reliably parsed, otherwise mark them mixed. Python-based searching should not disappear merely because the command lacks `grep` or `rg`.

R46. Searching a trace with `rg` is evidence inspection, not a sign of poor architecture. Count file reads, distinct files, repeated reads, tool-output bytes, reproduction attempts, and failed commands as descriptive context. Do not construct a “wasted steps” score from tool names alone.

R47. Optional reviewer-derived milestone: earliest visible statement that correctly identifies the failed boundary and cites supporting evidence, with cumulative usage up to that point. This is not the time at which the model privately understood the problem. Final correctness and final consumption remain primary.

## Exact OpenAI token and cost accounting

The following equations and validation cases are normative. Use the [Responses usage schema](https://developers.openai.com/api/reference/python/resources/responses/methods/retrieve) as the raw data contract. Persist new API fields even when the current report does not use them.

### Per-inference-response fields

| Symbol | JSON field | Interpretation |
|---|---|---|
| `I` | `usage.input_tokens` | Total input for this response. |
| `C` | `usage.input_tokens_details.cached_tokens` | Cache-read subset of `I`. |
| `W` | `usage.input_tokens_details.cache_write_tokens` | Cache-write subset of `I`, when supported. |
| `O` | `usage.output_tokens` | All reported generated tokens. |
| `R` | `usage.output_tokens_details.reasoning_tokens` | Reasoning subset of `O`. |
| `T` | `usage.total_tokens` | API total; must equal `I + O`. |

```text
ordinary_input_tokens = I - C - W
non_reasoning_output_tokens = O - R
request_total_tokens = I + O
trial_total_tokens = SUM(request_total_tokens for each solving inference attempt)
```

`non_reasoning_output_tokens` is not “visible answer tokens”: generated formatting/tool-call structure may also be counted. Do not tokenize the answer and substitute that count. See [output token accounting](https://developers.openai.com/api/docs/guides/token-counting#understand-output-token-counts).

Required invariants: all present counters are nonnegative integers (booleans are invalid); `C + W <= I`; `R <= O`; `T == I + O`. A missing `I`, `O`, or `T`, or a violated invariant, stops scheduling. Require the supported breakdown fields. An older qualified model may normalize absent `W` to zero **only** if its pinned documentation/pricing profile establishes that there is no separate cache-write category; record that normalization explicitly. Never infer zero from an unexplained missing value.

Token totals count every inference call from the initial task to final submission, including instructions, tool schemas, repeated history, and tool results when consumed as model input. Do not add local tool-output bytes or estimated tool-result tokens again. No extra model-based judge, summarizer, or router may appear in that solving ledger. If a separately enabled judge uses the API, its requests and costs have a separate `purpose=grading` ledger.

### Dollars are a separate measure

Archive the applicable [OpenAI pricing](https://developers.openai.com/api/docs/pricing) and [cache accounting rules](https://developers.openai.com/api/docs/guides/prompt-caching#calculate-input-cost) at the start of each experiment. Record model snapshot, `service_tier`, currency, effective date, context-length brackets, and prices per million tokens. Do not bake today's rates into source code.

For a price profile with disjoint input categories, define:

```text
request_cost_usd = (
    (I - C - W) * ordinary_input_usd_per_million
  + C * cached_input_usd_per_million
  + W * cache_write_usd_per_million
  + O * output_usd_per_million
) / 1_000_000
```

Use the model's documented full cache-write rate, not just a surcharge. For a model without separate cache-write pricing, `W=0` under its verified normalization. Reasoning is already in `O`, so it has no second additive charge. Models with unsupported pricing rules cannot enter a dollar comparison until the calculator supports and validates their rate profile.

Reserve each pending request at `counted_input_tokens * max(applicable input-category rates) + max_output_tokens * output_rate`, divided by one million, plus a separately specified allowance for any charged counting request. Apply the correct context bracket and freeze any supported model-specific pricing adjustments in the profile. Replace the reserve with observed cost after valid usage arrives. Keep a reserve unresolved on an unknown-billing timeout; do not release it merely because the client stopped waiting. Serial inference is the initial scheduling policy.

`batch_usd_cap` is required; there is no unlimited or default-dollar fallback. It covers all planned phases and replacement attempts, with qualification/preflight/grading tracked separately from solving. An unresolved billing event stops new scheduling for review. Provider usage/cost reports, if later available, are a reconciliation check; they cannot supply invented per-trial attribution when request-level telemetry is missing. Label calculated costs as rate-card estimates, not invoices, unless actual billed amounts have been reconciled.

### Artifact schema requirements

Each run contains `manifest.json`, `requests.jsonl`, `tool-events.jsonl`, immutable request/response JSON files, `submission.md`, `grade.json`, and `summary.json`. This is a required future layout, not a claim that those files exist now.

Each request-ledger row must include `trial_id`, `attempt_id`, `sequence`, `purpose` (`solving`, `preflight`, `qualification`, or `grading`), timestamps, payload hash/path, client request ID, server request ID if present, response ID if present, requested/returned model and tier, response status, raw usage, derived counters, pricing-profile ID, reserve/cost, telemetry status, and failure reason. A preflight row stores its count but contributes zero **solving inference tokens**; its possible financial cost and elapsed time are separate. Never count the same response twice on resume.

A summary must include the exact totals or `null`, `known_token_lower_bound`, `usage_complete`, missing-attempt IDs, per-category subtotals, request/tool counts, stop reason, correctness, estimated cost or `null`, known cost, and unresolved cost reserve. Preserve `null` for unknowns. Reports must visibly count excluded/partial-telemetry trials rather than silently dropping them.

### Golden cases and acceptance tests

These numbers are artificial unit-test data, **not benchmark measurements or actual OpenAI prices**.

| Response | `I` | `C` | `W` | `O` | `R` | `T` |
|---|---:|---:|---:|---:|---:|---:|
| One | 1,000 | 600 | 200 | 200 | 120 | 1,200 |
| Two | 1,500 | 1,000 | 0 | 300 | 200 | 1,800 |

Use fictional per-million prices of ordinary input `$2`, cache reads `$0.20`, cache writes `$2.50`, and output `$10`.

V01. Adding the two responses yields input `2,500`, output `500`, total `3,000`, cache reads `1,600`, cache writes `200`, reasoning `320`, ordinary input `700`, and non-reasoning output `180`. It must not yield `5,120` by double-counting input/output breakdowns.

V02. The rate-card calculator returns `$0.00302` and `$0.00420`, totaling `$0.00722`, using decimal arithmetic. It must not add another reasoning charge, apply cache discounts to all input, or charge a cache-write surcharge as its full price.

V03. Duplicated ingestion of response One still yields `1,200`, not `2,400`. Separate actual inference attempts cannot be collapsed just because their prompts match.

V04. Response One followed by a timeout without usage yields exact trial tokens `null`, known lower bound `1,200`, incomplete telemetry, and an unresolved billing reserve. No third inference call is automatically sent.

V05. A returned `incomplete` response with complete usage contributes all its input/output tokens even if visible text is empty. A refusal also consumes its reported usage; neither is a correct diagnosis by default.

V06. Negative counts, boolean counters, `C + W > I`, `R > O`, mismatched `T`, missing required counters, and an unexplained absent cache-write field are rejected. The explicitly verified legacy `W=0` branch has its own test.

V07. With `99,000` tokens already consumed and `500` pending input tokens, the remaining `500` output allowance is below the `1,024` floor, so no inference POST occurs. With `90,000` consumed and `2,000` pending input, set `max_output_tokens=8,000`. The input-count response itself must not inflate the solving total.

V08. A missing API key fails locally, and subscription credentials cannot substitute for it. A canary test confirms the key is absent from tool subprocess environments, serialized artifacts, and error logging.

V09. Injected 429, connection error, and timeout produce one inference attempt each with retries disabled. SDK automatic retries must not create an unlogged second request. Logged preflight traffic is distinguishable from inference traffic.

V10. A two-turn function-tool smoke test retains call IDs and all required response items, includes tool results in the second call's measured input, and yields the same total from independent raw-JSON aggregation and the run summary. This is the only part of accounting qualification that needs real model calls; schedule it under a declared qualification budget.

V11. Restart after saving a response but before executing its tool call does not resend that inference request. Restart after an ambiguous unsaved response marks unknown telemetry and requires review. Token totals do not depend on how often analysis reads the ledger.

V12. Removing the API key and disabling network still permits all ordinary application tests and synthetic accounting tests. Paid qualification and measured batches require an explicit runner entry point and populated budget manifest; they cannot be triggered by default test discovery.

## Correctness grading

R48. Use a scenario-specific rubric with six dimensions: failed boundary, external outcome/uncertainty, local state, evidence citations, reproducibility, and safe recovery. Require all critical dimensions for success; allow equivalent terminology and implementation approaches.

R49. Grade S1 as no observed provider call and no committed preparation, S2 as a returned transfer response with unconfirmed local posting, and S3 as an unknown remote outcome. Never require an answer to infer bank settlement or real physical disk capacity from synthetic evidence.

R50. Disqualifying errors include issuing a new payment identity for an unresolved payment, freeing uncertain reserved funds, claiming a trace proves bank settlement, or inventing an API response not present in evidence. State why a run failed; do not compress every failure into one unexplained number.

R51. A correct reproduction procedure identifies controlled inputs, the fault boundary, expected local state, and meaningful assertions. A human or evaluator must verify that the proposed steps could exercise the claimed condition. Merely saying “write a test” is insufficient. In phase one, do not demand code execution from an answer format that only requested a procedure.

R52. Separate machine-checkable facts from judgment. Validate state/citation existence mechanically where possible; use a written rubric for explanation and recovery. An optional model judge must be calibrated against human review and cannot be the only authority for disputed safety/correctness claims. Account for its cost separately.

R53. Blind graders to model identity and token/time metrics where possible. Architecture may be inferable from cited files; acknowledge incomplete arm blinding. Review all disagreements and all runs considered for stage presentation. Do not grade based on whether the model used the preferred tools.

## Analysis and budget

R54. Report trial counts, success rate by arm/model/case, stop reasons, and missing telemetry first. Then show input/output consumption and elapsed time for successes. Keep unsuccessful-run consumption visible in a separate panel or table.

R55. For paired blocks where both compared arms succeed, compute paired differences and ratios, reporting how many pairs qualify. That conditional comparison can favor easy surviving cases; disclose exclusions. Also show total consumed tokens divided by successful completions across all attempts, with zero-success arms marked undefined. Treat that aggregate as descriptive, not a guaranteed expected cost.

R56. Keep the three case results separate before any macro-average. If giving uncertainty intervals, resample matched blocks within cases and label that they describe repeated-run variability on this small suite, not generalization to all software. Do not treat every model call as an independent sample.

R57. Cross-model comparisons require correctness and current pricing, not raw token ratios alone. A statement that an efficient model with traces matches a stronger model without them needs a predefined acceptable success-rate margin and enough trials; this small design supports an exploratory observation, not a broad equivalence claim.

R58. Use the request-level dollar formula and conservative spend reservations below with a frozen official OpenAI pricing snapshot. Require `batch_usd_cap` as an explicit positive manifest value before paid work. At fixed concurrency one, reserve worst-case input/output cost before each inference POST; stop if the cap cannot cover it. Keep an unresolved reserve for unknown usage until reconciled. Include preflight charges if applicable, qualification, replacements, and grading in their own budget lines. A dashboard/project alert is supplemental; application-side admission controls enforce the experiment cap.

R59. Freeze and save the main-run manifest before execution. Do not stop when a favorable result appears, keep expanding only losing arms, or silently change the prompt. Protocol changes create a new experiment version. Publish unfavorable and null results alongside favorable ones.

## Audience illustration

Use roughly 45–60 seconds of the talk for this comparison; replace the existing comparison beat rather than adding a new technical lecture. Keep the techniques menu and repository handoff.

R60. First visual: the same $500 payment and matching happy-path outcomes. Next, show the common error and the clean app's additional evidence as three readable events: “reserved,” “provider response received,” “confirmation save failed.” Do not display raw GUIDs or a wall of JSON.

R61. If measurements exist, show two aligned lanes of actual agent actions with cumulative usage: for example, source search, source read, state inspection, reproduction, final diagnosis versus evidence read, focused source check, final diagnosis. These sequences are illustrative possibilities, not scripts the runner should enforce. Use the same scale and event classification in both lanes.

R62. Label visible facts as searches, reads, reproductions, and grounded conclusions. Avoid “here the model thinks harder” or “direct reasoning” as a measured internal mechanism. A fair spoken line is: **“Here the agent reconstructs what happened from code and state. Here it starts with a recorded account of what happened.”** Use it only if the observed trials support it.

R63. Grep is a good tool. The interesting question is how much context the agent had to gather before reaching a correct conclusion, not whether it used a search command. If both agents use `rg` effectively and finish quickly, show that outcome. Do not perform an intentionally long manual grep routine and label it measured agent behavior.

R64. Choose a representative paired trial by a rule fixed before inspecting presentation candidates: use the designated S2 case and primary efficient model; among pairs where both succeed, choose the pair closest to the median combined token consumption, breaking ties by run ID. Display whether its gap is typical of the aggregate. If it is unrepresentative, use aggregate plots rather than swapping to a dramatic outlier. If no pair qualifies, show the success/failure distribution instead.

R65. Alongside the lanes, show success counts and a compact within-model token chart with units, model, case count, repetitions, and the treatment labels. Example format: “correct diagnoses: n/N; median metered tokens among successful runs: measured value.” Never fill these placeholders with invented numbers.

R66. Use recorded terminal clips or static transcript-derived frames with readable labels. Preserve order, disclose time compression/omitted idle periods, and do not stitch actions from different trials into one apparent run. Provide links to raw trial IDs in the repository for audience follow-up. Do not expose account credentials in exports.

R67. If the efficient model benefits while the stronger one does not, present the interaction explicitly. If traces increase tokens but improve correctness, lead with reliability. If no useful difference appears, keep the architecture demonstration and say measurement did not establish a token saving on this task.

R68. Keep “fewer tokens” distinct from “lower dollar cost,” “fewer commands,” and “faster.” A token count is not a measure of intelligence or engineering taste. Static type checking, documentation adoption, and initial coding effort are not tested here.

## Implementation work packages and acceptance criteria

| Package | Deliverable | Acceptance criterion |
|---|---|---|
| P1: freeze cases | Versioned cases, parity checks, neutral source packages. | A/B/C produce matching payment outcomes for S1–S3; no deliberately weakened baseline. |
| P2: isolation | Per-trial workspace builder and external reproduction boundary. | Leak checks cannot find fault triggers, evaluator code, other arms, or prior trials. |
| P3: OpenAI harness | API-key-only Responses loop, request ledger, exact usage, preflight budgeting. | OA01–OA07 and V01–V12 pass; no subscription fallback, hidden retries, missing calls, or double-counted tokens. |
| P4: scheduler | Fixed manifest, randomized blocks, limits, resumability. | No duplicate completed trial is billed on resume; replacements retain original records. |
| P5: grading | Scenario rubric, fact checks, human review workflow. | Correct, partially correct, unsafe, and unsupported example answers receive expected grades. |
| P6: analysis | Per-case/arm/model tables, exact token/cost sums, paired summaries, event timelines. | Golden accounting cases pass; incomplete telemetry has no exact total; all attempts remain visible. |
| P7: pilot | 18-trial proposed qualification batch and retrospective. | Counting, packaging, grading, and limits are validated before freezing the main protocol. |
| P8: measured batch | Approved, fixed-size experiment and artifact archive. | Spend cap enforced; all trials accounted for; no changes made to favor a result. |
| P9: presentation | Representative recorded comparison and aggregate chart. | Every displayed action/count links to an actual trial; caveats fit the claim. |

Required inference implementation: the OA01–OA07 OpenAI Python Responses tool loop; subscription-backed or uninstrumented alternative harnesses do not satisfy this specification. Suggested future layout: extend `benchmarks/troubleshooting/` with runner adapters, package builder, cases, grading, analysis, and an experiment manifest. Store generated runs outside tracked source by default. Commit only reviewed, sanitized result bundles intentionally. The `openai` SDK must be pinned; the container implementation remains an implementation choice subject to the leakage tests.

## Required checks before declaring measurement ready

- A trial cannot read evaluator-only data, including via SQLite schema introspection or traceback paths.
- The ordinary traceback remains equally useful across all arms.
- Restarting the trial does not reuse consumed fixtures, model context, or cached repository summaries.
- OA01–OA07 and V01–V12 pass: OpenAI API-key-only access, raw response usage, correct cache/reasoning accounting, no hidden inference, and no silent zero-fill for missing usage.
- Time/token/tool limits terminate runs and preserve their cost and transcript.
- A wrong but short answer cannot win an efficiency comparison.
- An unsupported claim that a bank payment settled fails grading even if the fixture contains a transfer ID.
- A clean run that uses more tokens remains in the published data and can appear in the representative presentation.
- No measured agent calls or paid provider calls occur during ordinary example tests.

## Sources and rationale

OpenAI API implementation requirements were checked against the official [authentication reference](https://developers.openai.com/api/reference/overview#authentication), [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [usage example](https://developers.openai.com/api/reference/python/resources/responses/methods/retrieve), [token-counting guide](https://developers.openai.com/api/docs/guides/token-counting), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning), [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching), and [pricing page](https://developers.openai.com/api/docs/pricing). Exact model availability, pinned SDK support, and applicable rates must be revalidated before execution. No API key was needed or used to write this specification.

This experimental design is our proposal, not a reproduction of an existing benchmark. It uses the distinction between tasks, repeated trials, observed transcripts, and outcomes described in [Anthropic's agent-evaluation guide](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents). That guide also motivates combining objective checks with calibrated review rather than trusting an agent's claim of completion.

Control environment resources and record execution conditions; agentic coding measurements can be affected by infrastructure variation, as discussed in [Anthropic's infrastructure-noise analysis](https://www.anthropic.com/engineering/infrastructure-noise). These references support evaluation hygiene, not a claim that this architecture reduces tokens. Sources reviewed September 6, 2026.
