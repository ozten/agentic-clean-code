# AI Tinkerers HTML slides

Open [index.html](index.html) directly in a modern browser. The deck is a self-contained HTML file with inline CSS, JavaScript, and speaker notes; no server, build step, external fonts, or network connection is needed to present it. Repository and guide links require access to their destinations.

Use Left/Right arrows, Space, or Page Up/Down to present. Slide 4 has four payment attempts; advancing walks through each attempt before leaving the slide. You can also select an attempt directly. On touch screens, swipe horizontally.

- **N**: toggle speaker notes with suggested timing.
- **O**: slide overview; **Esc** closes overlays.
- **F**: fullscreen (browser support permitting).
- **Home / End**: first / last slide.
- URL fragments such as `#3` and `#4.2` link to a slide or recovery step.
- Browser **Print / Save as PDF** prints all seven slides. The recovery slide prints a table containing all four attempts.
- The final slide links to the three guides and repository and provides a copyable assignment.

## Five-minute sequence

| Time | Slide |
|---|---|
| 0:00–0:35 | $500. Connection lost. Retry? |
| 0:35–1:10 | Whose engineering taste is your agent inheriting? |
| 1:10–2:00 | Basic code and clean architecture, side by side |
| 2:00–3:20 | Four attempts: submit, retry, recover, click again |
| 3:20–3:45 | Captured interaction → fixture → behavior assertion |
| 3:45–4:10 | What the diagnosis pilot measured |
| 4:10–5:00 | The assignment to take home |

These are rehearsal targets, not measured speaking times. The HTML speaker notes are the current presentation sequence; they adapt the [earlier Markdown talk draft](../ai_tinkerers_talk_sept_2026.md) with the requested code comparison and a separate, brief pilot-results slide.

## Source and evidence

The code comparison uses selected lines from `examples/contractor-payment-simple/app.py` (omissions marked) and the `pay` body in `examples/contractor-payment/core.py` (inline comments omitted). Explanatory comments are labeled visually as comments. Both apps preserve the same payment rules; the slide does not claim that formal layers are required for correct behavior.

The recovery slide is a visual walkthrough of `demo.py` and `test_timeout_disk_full_recovery_and_duplicate_submission`, not Python executing in the browser. Its intermediate posting count comes from the test assertion. All provider outcomes are synthetic. The demo reopens a SQLite connection between attempts and injects a storage exception; it does not restart the process or fill a disk.

The playback slide describes an adoption workflow. Existing tests demonstrate HTTP playback and payment-state checks separately, not a complete capture-to-payment-regression demo. Pilot counts come from the [pilot-v2 report](../../benchmarks/troubleshooting/results/pilot-v2/analysis/report.md). Review limitations and the distinction between diagnosis and safer code changes remain visible on screen and in notes.

For changes to the layout, check 1600 × 1000 and a smaller viewport, all four recovery states, keyboard navigation, notes, and print output. Keep text clear of the slide footer. No new Python samples or benchmark runs are needed for the deck.
