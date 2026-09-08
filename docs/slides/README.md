# AI Tinkerers HTML slides

Open [index.html](index.html) directly in a modern browser. The deck is a self-contained HTML file with inline CSS, JavaScript, and speaker notes; no server, build step, external fonts, or network connection is needed to present it. Repository and guide links require access to their destinations.

Use Left/Right arrows, Space, or Page Up/Down to present. Slide 5 has four payment attempts; advancing walks through each attempt before leaving the slide. You can also select an attempt directly. On touch screens, swipe horizontally.

- **W** on slide 4 (or click **Wiring** beside `prepare`): show the actual adapter construction patterns. **Esc** closes the callout. Use this optional explanation for questions; the preceding interfaces slide covers the concepts in the main talk.
- **N**: toggle speaker notes with suggested timing.
- **O**: slide overview; **Esc** closes overlays.
- **F**: fullscreen (browser support permitting).
- **Home / End**: first / last slide.
- URL fragments such as `#4` and `#5.2` link to a slide or recovery step.
- Browser **Print / Save as PDF** prints all eight slides. The recovery slide prints a table containing all four attempts.
- The final slide links to the three guides and repository and provides a copyable assignment.

## Five-minute sequence

| Time | Slide |
|---|---|
| 0:00–0:30 | $500. Connection lost. Retry? |
| 0:30–1:10 | State your invariants; simulate failure paths; check behavior |
| 1:10–1:50 | Interfaces and four adapters: stub, passthrough, record, playback |
| 1:50–2:30 | Basic code and clean architecture, side by side |
| 2:30–3:40 | Four attempts: submit, retry, recover, click again |
| 3:40–4:00 | Captured interaction → fixture → behavior assertion |
| 4:00–4:25 | What the diagnosis pilot measured |
| 4:25–5:00 | The assignment to take home |

These are rehearsal targets, not measured speaking times. The HTML speaker notes are the current presentation sequence; they adapt the [earlier Markdown talk draft](../ai_tinkerers_talk_sept_2026.md) with an interfaces/adapters explanation before the code comparison and a separate, brief pilot-results slide.

## Source and evidence

The code comparison aligns selected lines from `examples/contractor-payment-simple/app.py` and `examples/contractor-payment/core.py` in three matching rows: load/create payment intent, obtain/validate a receipt, and confirm locally. A new payment reserves funds; an already-confirmed payment returns its saved receipt; an unresolved payment continues using the existing intent. The function handles first attempts and retries, but contains no retry loop. Both columns are excerpts, not complete functions. Omission comments name the inline work not displayed; adapter comments explain where the corresponding implementation lives in the clean version. Shorter orchestration is not a reduction in total implementation. Explanatory comments are labeled visually as comments. Both apps preserve the same payment rules; the slide does not claim that formal layers are required for correct behavior.

The recovery slide is a visual walkthrough of `demo.py` and `test_timeout_disk_full_recovery_and_duplicate_submission`, not Python executing in the browser. Its intermediate posting count comes from the test assertion. All provider outcomes are synthetic. The demo reopens a SQLite connection between attempts and injects a storage exception; it does not restart the process or fill a disk.

The playback slide describes an adoption workflow. Existing tests demonstrate HTTP playback and payment-state checks separately, not a complete capture-to-payment-regression demo. Pilot token ratios compare matched model/case pairs with completed diagnoses (clean without traces: 1.06–1.68× basic; with traces: 3.04–3.96× basic). The five unfinished trace trials are reported separately and excluded from the ratio range. Pilot counts come from the [pilot-v2 report](../../benchmarks/troubleshooting/results/pilot-v2/analysis/report.md). Review limitations and the distinction between diagnosis and safer code changes remain visible on screen and in notes.

For changes to the layout, check 1600 × 1000 and a smaller viewport, all four recovery states, keyboard navigation, notes, and print output. Keep text clear of the slide footer. No new Python samples or benchmark runs are needed for the deck.

The wiring callout uses existing constructors: `SqliteLedger`, `LedgerRecorder`, `SingleResponse.load`, `Recorder`, and `StripeTransfers`. It shows direct SQLite, wrapped ledger recording, and HTTP fixture playback with optional recording. Setup/imports, ledger seeding/cleanup, and correlation-ID creation are omitted. No mode-string factory, ledger playback, or live HTTP adapter is implied. The callout is optional and omitted from print output.
