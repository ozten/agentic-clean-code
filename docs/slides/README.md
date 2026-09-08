# AI Tinkerers HTML slides

Open [index.html](index.html) directly in a modern browser. The deck is a self-contained HTML file with inline CSS, JavaScript, and speaker notes; no server, build step, external fonts, or network connection is needed to present it. Repository and guide links require access to their destinations.

Use Left/Right arrows, Space, or Page Up/Down to present. Slide 7 has four payment attempts; advancing walks through each attempt before leaving the slide. You can also select an attempt directly. On touch screens, swipe horizontally.

- **W** on slide 6 (or click **Wiring** beside `prepare`): show the actual adapter construction patterns. **Esc** closes the callout. Use this optional explanation for questions; the preceding interfaces slide covers the concepts in the main talk.
- **N**: toggle speaker notes with suggested timing.
- **O**: slide overview; **Esc** closes overlays.
- **F**: fullscreen (browser support permitting).
- **Home / End**: first / last slide.
- URL fragments such as `#6` and `#7.2` link to a slide or recovery step.
- Browser **Print / Save as PDF** prints all eleven visible slides. The recovery slide prints a table containing all four attempts.
- The take-home assignment slide ("One interaction. One rule. One offline test.") is currently hidden with the `hidden` attribute; it stays in the file and is skipped by navigation and print. Remove the attribute on its `<section>` to restore it.
- Slide 9 is a full-screen 4 × 4 keyword grid ordered roughly from easiest to hardest to adopt: linting, types, assertions/contracts, service virtualization, fault injection, time-travel testing, property-based testing, fuzzing, mutation testing, consumer-driven contract testing (Pact), automated infosec, chaos engineering, deterministic simulation, full-stack simulation, model checking, and formal proofs. Leave it visible briefly for a photograph.
- Slide 10 is the Q & A screen after the five-minute talk: a large embedded QR code links to https://github.com/ozten/agentic-clean-code. The QR code was generated locally and independently decoded to verify its destination; no runtime QR service is required.

## Five-minute sequence

| Time | Slide |
|---|---|
| 0:00–0:05 | Title · Whose engineering taste is your agent inheriting? |
| 0:05–0:25 | $500. Connection lost. Retry? |
| 0:25–1:00 | State your invariants; simulate failure paths; check behavior |
| 1:00–1:35 | Interfaces and four adapters: stub, passthrough, record, playback |
| 1:35–2:00 | View an HTTP trace: replay a 503 status and error message |
| 2:00–2:35 | Basic code and clean architecture, side by side |
| 2:35–3:40 | Four attempts: submit, retry, recover, click again |
| 3:40–4:00 | Captured interaction → fixture → behavior assertion |
| 4:00–4:50 | Open slot: pilot results moved after Q & A, assignment slide hidden |
| 4:50–5:00 | Keywords for other Software Architecture techniques |
| After 5:00 | Q & A · repository QR code |
| After Q & A | Pilot results backup: what the diagnosis pilot measured |

These are rehearsal targets, not measured speaking times. The HTML speaker notes are the current presentation sequence; they adapt the [earlier Markdown talk draft](../ai_tinkerers_talk_sept_2026.md) with an interfaces/adapters explanation before the code comparison and a separate, brief pilot-results slide.

## Source and evidence

The code comparison aligns selected lines from `examples/contractor-payment-simple/app.py` and `examples/contractor-payment/core.py` in three matching rows: load/create payment intent, obtain/validate a receipt, and confirm locally. A new payment reserves funds; an already-confirmed payment returns its saved receipt; an unresolved payment continues using the existing intent. The function handles first attempts and retries, but contains no retry loop. Both columns are excerpts, not complete functions. Omission comments name the inline work not displayed; adapter comments explain where the corresponding implementation lives in the clean version. Shorter orchestration is not a reduction in total implementation. Explanatory comments are labeled visually as comments. Both apps preserve the same payment rules; the slide does not claim that formal layers are required for correct behavior.

The recovery slide is a visual walkthrough of `demo.py` and `test_timeout_disk_full_recovery_and_duplicate_submission`, not Python executing in the browser. Its intermediate posting count comes from the test assertion. All provider outcomes are synthetic. The demo reopens a SQLite connection between attempts and injects a storage exception; it does not restart the process or fill a disk.

The playback slide describes an adoption workflow. Existing tests demonstrate HTTP playback and payment-state checks separately, not a complete capture-to-payment-regression demo. Pilot token ratios compare matched model/case pairs with completed diagnoses (clean without traces: 1.06–1.68× basic; with traces: 3.04–3.96× basic). The five unfinished trace trials are reported separately and excluded from the ratio range. Pilot counts come from the [pilot-v2 report](../../benchmarks/troubleshooting/results/pilot-v2/analysis/report.md). Review limitations and the distinction between diagnosis and safer code changes remain visible on screen and in notes.

For changes to the layout, check 1600 × 1000 and a smaller viewport, all four recovery states, keyboard navigation, notes, and print output. Keep text clear of the slide footer. No new Python samples or benchmark runs are needed for the deck.

The wiring callout uses existing constructors: `SqliteLedger`, `LedgerRecorder`, `SingleResponse.load`, `Recorder`, and `StripeTransfers`. It shows direct SQLite, wrapped ledger recording, and HTTP fixture playback with optional recording. Setup/imports, ledger seeding/cleanup, and correlation-ID creation are omitted. No mode-string factory, ledger playback, or live HTTP adapter is implied. The callout is optional and omitted from print output.

Slide 5 displays selected fields from [a synthetic HTTP 503 trace](fixtures/http-503-trace.json). The full trace was generated by the existing recorder, converted to playback, and checked to return status 503 and the stored error message. A local payment invocation with that replay retained the reservation and made no posting. This is not a live capture. The HTTP adapter currently rejects a non-200 response before inspecting its error body, so the displayed message is a transport response payload, not the application’s printed exception message.
