# Whose Engineering Taste Is Your Agent Inheriting?

**Austin King · AI Tinkerers Seattle · September 2026**

Five-minute talk draft. Slide cues and preparation notes are not spoken. Timing is a rehearsal target; allow pauses for the payment-state reveals. Uses the existing demo and tests. The [HTML slide deck](slides/index.html) adapts this draft into seven slides with the requested side-by-side code comparison. Its embedded speaker notes and [timing guide](slides/README.md) are the current presentation sequence.

## Slide 1 — $500. Connection lost. Retry? [0:00–0:40]

**On screen:** “You send $500. Confirmation disappears. Do you retry?”

You're building an app that pays contractors. You send five hundred dollars, and the connection drops. Did the payment happen? Is it safe to try again?

Before asking an agent to handle that error, I want to state one rule: money attached to an uncertain payment stays reserved. “We don't know” must never mean “available to spend again.”

That's the kind of engineering judgment I want my agent's changes to preserve.

## Slide 2 — Whose engineering taste are you inheriting? [0:40–1:25]

**On screen:** “One rule. A controlled failure. An executable check.”

When you ask an agent to write tests, you're leaving a lot of decisions open. Which failures? What should happen afterward? What would make the test fail?

Whose engineering taste are you inheriting?

I want to put my standards into the checks its changes have to pass. For this payment: preserve the reservation, reuse the payment identity, and don't send another request after confirmation.

As agents take on more work between human reviews, I want these expectations written down and checked every time. Start with one interaction you can control in a test. An existing function or module may already give you enough control.

## Slide 3 — Choose the failure. Check the recovery. [1:25–3:10]

**On screen:** `Payment logic → controlled provider response + local SQLite ledger`

Reveal the following states in order, displaying dollars rather than the demo's raw cents. Keep the assertion next to the state it checks. Use the existing demo output or a short recording.

| Attempt | Chosen outcome | Local result / check |
|---|---|---|
| Submit | Response lost | $500 stays reserved. |
| Retry | Response received; confirmation save fails | $500 stays reserved; no posting. |
| Recover | Response received; save succeeds | One local posting; same request identity. |
| Click again | No provider call allowed | Saved receipt returned; still one posting. |

Here's a small Python example. All provider responses are synthetic; no money moves. We're running the application's payment logic with a real local SQLite database.

I don't have to wait for the payment service to time out. The test supplies that outcome.

The response disappears. Five hundred dollars stays reserved.

On the next attempt, the response arrives, but we inject a failure while saving its confirmation. The money still stays reserved. There's no local posting.

We reopen the database between attempts, so the recovery has to use what was actually saved. Try again: one local posting, using the original payment identity and request.

Click again. This time the test forbids another payment request. The application returns the saved receipt.

The supplied response checks the request and rejects an unexpected extra call. The ledger assertions check what survived the failures. Those are concrete standards a future change must preserve.

The useful architectural choice is giving the test control at the interaction that can fail. Here, small interfaces let us supply responses and inject a storage fault without changing the payment logic.

These checks establish our application's behavior. They don't prove what a live payment provider does.

## Slide 4 — Keep useful failure evidence [3:10–3:50]

**On screen:** `Captured interaction → reviewed fixture → test with an expected-behavior assertion`

**Small caption:** Workflow; existing tests demonstrate playback and payment-state checks separately.

When you capture a useful failure, you can keep it as a fixture for a regression test. The recording supplies what happened at the boundary. Your rule supplies what should happen. Replay alone doesn't tell you the behavior was right.

We also tried traces in a diagnosis benchmark. Our pilot found no token savings; half the trace runs hit the token cap. We haven't measured whether these controls help agents make safer changes. That's a separate question.

## Slide 5 — Give your next agent this assignment [3:50–5:00]

**On screen, kept visible through the close:** Repository URL/QR before presenting. Three guides: **Interfaces · Isolated testing · Traces and replay**.

> Read these three guides. Pick one external interaction. State one rule that must survive a failure. Use an existing boundary or add the smallest useful one. Show me an offline test that checks the rule. Report the command, what you observed, and what remains unknown.

I've put the guidance and both Python examples in an open-source repository, agentic-clean-code.

Start with one dependency in your own project. Name a failure that matters and the behavior you expect afterward. Ask your agent to show you an offline test that checks it.

You may already have the right test or the right place to control the dependency. Use it. The goal is a check that future changes have to pass.

Ask for the command it ran, the result it observed, and what that result doesn't establish. A recorded response tells you what the application saw; it doesn't tell you everything that happened elsewhere.

We can spend more of this newly affordable engineering effort exploring the failures we used to leave untested.

Whose engineering taste is your agent inheriting? Put yours in the checks its changes have to pass.

## Preparation notes

- Rehearse aloud. The state table needs pauses; trim speech before accelerating the demonstration. Leave the final assignment visible long enough to photograph.
- Run `python3 -B examples/contractor-payment/demo.py` and `python3 -B -m unittest discover -s examples/contractor-payment -v` from the repository root. Use existing artifacts or a short recording; no new sample or deliberate-bug variant is needed.
- Slide 3 uses `demo.py` and `test_timeout_disk_full_recovery_and_duplicate_submission`. The demo reopens a database connection, not a whole application process. The test verifies no posting after the save failure; the demo's terminal output does not print that intermediate count. Present it as a test assertion, not fabricated terminal output.
- The disk-full adapter injects an exception before confirmation. A separate existing SQLite-trigger test verifies rollback after intermediate SQL changes. Neither fills a physical disk. The demo has sequential invocations, not concurrent workers.
- Responses are synthetic Stripe-shaped fixtures, not live captures. Checks cover request identity and local bookkeeping, not live remote deduplication or bank settlement. Call this a contractor payment, not escrow.
- Keep capture-to-regression to roughly 15–20 seconds. Existing tests separately demonstrate HTTP trace conversion/playback and payment-state assertions. Do not imply a new complete capture-to-payment-regression demonstration exists. Ledger playback is not implemented.
- Both Python apps are handwritten and preserve the same payment rules. The simple app also accepts explicit time and fixtures. The HTML deck includes their comparison as requested, showing explicit boundaries alongside direct calls. Do not present it as evidence that formal layers are necessary for correctness or testability.
- Pilot-v2: 30 trials, five cases, two models, three arms, one repetition per combination. Each arm without traces submitted 10/10; traces submitted 5/10 with five token-cap stops. All 25 submissions were judged correct in session review, conducted by the coding-agent session operator rather than a blinded independent human reviewer. See the [report](../benchmarks/troubleshooting/results/pilot-v2/analysis/report.md) and [retrospective](plans/2026-09-06-pilot-retrospective.md).
- The benchmark supplies payment rules and a reproduction tool, excludes existing tests, and asks for diagnosis plus a proposed reproduction procedure. It does not evaluate implemented fixes or executable regression-test quality. Raw trace browsing adds reading overhead; no dedicated trace-query tool was supplied. Avoid generalizing token ratios into dollar or time savings.
- Architecture and verification guidance is a proposed practice; safer high-volume agent work remains a motivation, not a measured result of this pilot. No new benchmark is required for this talk.
- Add the public repository URL and QR after checking the published destination. Repository handoff: [adoption guide](README.md), [interfaces](guides/interfaces.md), [testing](guides/testing.md), [traces and replay](guides/traces-and-replay.md), and [agent instructions](templates/agent-instructions.md).
- Further techniques belong in the [adoption guide's further experiments](README.md#further-experiments), not the spoken five-minute sequence. Keep GUIDs, file layout, adapter modes, and request headers in the repo.
