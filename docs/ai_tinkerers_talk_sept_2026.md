# Agentic Clean Code: What If We Could Afford to Test It?

**Austin King · AI Tinkerers Seattle · September 2026**

Five-minute talk draft. Slide cues and speaker notes are not spoken. Timing is a rehearsal target.

## Slide 1 — Did we just pay twice? [0:00–0:45]

**On screen:** “You send $500. Confirmation disappears. Do you retry?”

You're building an app that pays contractors. You send five hundred dollars, and the connection drops. Did the payment happen? Is it safe to try again?

That's the kind of failure I want my agent to help me test.

At Mozilla, I saw innovation in fuzz testing. At Amazon, I saw QA teams eliminated to reduce costs. Those experiences left me thinking about the testing we can afford.

As intelligence gets cheaper, what if we spent more of it exploring failures like this?

## Slide 2 — Whose engineering taste are you inheriting? [0:45–1:20]

**On screen:** “Your agent has defaults. Give it architectural guidance.”

Without architectural guidance, you inherit the flavor and quality of whatever coding harness you're using—the tool directing your agent.

It writes tests. But I don't want to assume it has good engineering taste. Does it test the difficult failure? Can it reproduce a bug? Or does the happy path just turn green?

Agentic Clean Code supplies structure: explicit interfaces, controlled test environments, and recorded evidence. A few Markdown documents make those expectations concrete.

## Slide 3 — Control the environment [1:20–2:15]

**On screen:** `Payment decisions → interface → real service OR chosen test response`

The technique is called ports and adapters. Put an interface between your code and its environment: the payment service, storage, the clock.

Now you can choose exactly what the environment does in a test, while running the actual payment logic.

Our example uses Stripe Connect to send an approved contractor payment. We reserve the amount locally before submitting it.

If confirmation disappears, that money stays reserved. “We don't know” must never mean “available to spend again.”

For each test, we supply one response. A timeout. A success. A storage failure. We can explore each condition deliberately.

## Slide 4 — Same failure, different evidence [2:15–3:20]

**On screen:** Two Python apps. Happy path: both succeed. Failure: both show “database or disk is full.” Clean app additionally shows “payment reserved → transfer response received → confirmation save failed.” Use artifacts from the comparison script; keep full traces available in the repo.

Here are two versions of the same payment app, both in Python. One is a straightforward script. The other follows our architecture. Both work on the happy path.

Now give them the same failure: the payment response arrives, but saving the confirmation fails.

The simple app gives you an error and a traceback. The clean app also gives you the connected story: which payment, what the provider returned, and which local operation failed.

That's evidence an agent can use to investigate and reproduce the failure. The ideal bug report nobody has time to write.

Both examples use synthetic responses; no money moves. We've stubbed a benchmark to measure the agent tokens needed for troubleshooting. We haven't measured those savings yet.

## Slide 5 — Things we can afford to try [3:20–4:15]

**On screen — a menu to photograph, not a checklist to read aloud:**

| Technique | What to explore |
|---|---|
| Property-based testing | Generate examples; check rules that must hold. |
| Fuzz testing | Search for failures with unusual inputs. |
| Fault injection / chaos engineering | Simulate timeouts, crashes, and full disks. |
| Time-travel testing | Exercise clock changes and accumulated state. |
| Service virtualization / record and replay | Control external dependencies. |
| Contract testing | Check expectations at interfaces. |
| Model checking — TLA+, Stateright | Explore possible states in a model. |
| Formal proofs — Lean | Prove stated properties under explicit assumptions. |

These are keywords for your next research session.

Ask your agent: what happens if this request arrives twice? If the disk fills up? If we run for ten years? Can you generate inputs that break this assumption?

Some of these techniques once needed more specialist time than a small project could justify. Agents give us a chance to explore them more widely.

More agents can still share the same mistaken assumption. Agreement isn't verification.

You still need to say what must remain true. For this payment: uncertainty must never make reserved money spendable again.

Agents write the code. You own the invariants—the rules your project must never break.

## Slide 6 — Take three documents home [4:15–5:00]

**On screen:** `agentic-clean-code` + repository link/QR code before presenting

**Three documents:** Interfaces · Isolated testing · Traces and replay

I've put these practices into an open-source repository: agentic-clean-code.

Three guides let you bring your own engineering standards into your next project. The payment example runs locally, and an example decision record explains its architecture.

Start with one dependency. Tell your agent: read these docs, isolate this interaction, and show me a meaningful test that runs without calling the live service.

Then try capturing a failure and turning it into a regression test.

My goal is fewer tokens spent rediscovering context, and more effort spent testing the failures that matter.

As intelligence gets cheaper, let's spend more of it on the engineering work we always wished we had time to do.

## Preparation notes

- Rehearse aloud and adjust the timing; pause on the diagram and leave the techniques menu visible long enough to photograph.
- Add the public repository URL and QR code to the final slide after confirming the repository is published. Run the [payment demo](../examples/contractor-payment/README.md) beforehand and use a short recording if live terminal work would crowd the five-minute slot.
- The example uses synthetic Stripe-shaped responses, not live captures. It verifies our request identity and local bookkeeping; it does not prove remote deduplication or bank settlement. Call it a contractor payment, not escrow.
- Keep GUIDs, directory layout, serialization, idempotency headers, and adapter modes in the repository; the spoken explanation focuses on controlling failures and verifying recovery.
- The clean version records HTTP and ledger interactions, including the failed confirmation. The comparison preserves full ordinary tracebacks for both versions.
- Both apps are handwritten teaching examples. Do not describe the simple version as measured harness output, or claim static type checking is configured.
- Use the [comparison generator](../benchmarks/troubleshooting/README.md) for matching happy/failure artifacts. Agent runs and token collection remain future work; no percentage savings are available.
- The Mozilla and Amazon statements reflect Austin's account. The draft deliberately makes no claim that Mozilla invented fuzz testing.
- If showing a real trace, use a reviewed, sanitized fixture. Show the initiating action, a relevant request/response, expected behavior, and the replay test result.
- Repository handoff: [adoption guide](README.md), [interfaces](guides/interfaces.md), [testing](guides/testing.md), and [traces and replay](guides/traces-and-replay.md).
