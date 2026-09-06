"""Per-case/arm/model tables, exact sums, paired summaries, event timelines (design R54-R57, P6).

Order of reporting follows R54: attempted trials, stop reasons, and missing telemetry first;
then consumption among correct trials; unsuccessful consumption in its own table. Paired
differences use blocks where both compared arms are correct with complete telemetry, and the
report says how many pairs qualify (R55). Cases are kept separate (R56).
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def load_trials(run_dir: Path) -> list[dict]:
    run_dir = Path(run_dir).resolve()
    plan = json.loads((run_dir / "plan.json").read_text())["trials"]
    state = json.loads((run_dir / "state.json").read_text())["trials"]
    rows = []
    for trial in plan:
        trial_dir = run_dir / "trials" / trial["trial_id"]
        status = state.get(trial["trial_id"], {}).get("status", "pending")
        summary = json.loads((trial_dir / "summary.json").read_text()) if (trial_dir / "summary.json").exists() else {}
        grade = json.loads((trial_dir / "grade.json").read_text()) if (trial_dir / "grade.json").exists() else {}
        events = []
        if (trial_dir / "tool-events.jsonl").exists():
            events = [json.loads(l) for l in (trial_dir / "tool-events.jsonl").read_text().splitlines() if l.strip()]
        requests = []
        if (trial_dir / "requests.jsonl").exists():
            reduced: dict[str, dict] = {}
            for line in (trial_dir / "requests.jsonl").read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    reduced[row["attempt_id"]] = {**reduced.get(row["attempt_id"], {}), **row}
            requests = list(reduced.values())
        rows.append({**trial, "status": status, "summary": summary, "grade": grade, "events": events,
                     "requests": requests, "correct": bool(grade.get("final", {}).get("correct")),
                     "verdict": grade.get("final", {}).get("verdict"), "tokens": summary.get("exact_total_tokens"),
                     "telemetry_complete": summary.get("telemetry_complete"), "stop_reason": summary.get("stop_reason")})
    return rows


def independent_raw_total(trial_dir: Path) -> int | None:
    """Sum usage from the immutable response files, independent of summary.json (V10 cross-check)."""
    total = 0
    for path in sorted((trial_dir / "responses").glob("*-solving-response.json")):
        data = json.loads(path.read_text())
        usage = data.get("usage") or {}
        if "input_tokens" not in usage or "output_tokens" not in usage:
            return None
        total += usage["input_tokens"] + usage["output_tokens"]
    return total


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def _fmt(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.0f}" if value >= 100 else f"{value:.2f}"
    return str(value)


def analyze_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    rows = load_trials(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    out_dir = run_dir / "analysis"
    out_dir.mkdir(exist_ok=True)
    groups = defaultdict(list)
    for row in rows:
        groups[(row["model"], row["case"], row["arm"])].append(row)
    lines = [f"# Analysis: {manifest.get('run_id')} ({manifest.get('experiment_version')})", ""]

    # 1. Attempted trials, stop reasons, telemetry.
    lines += ["## Trials attempted", "", "| model | case | arm | planned | completed | needs_review | pending | correct | telemetry incomplete | stop reasons |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    table1 = []
    for key in sorted(groups):
        trials = groups[key]
        completed = [t for t in trials if t["status"] == "completed"]
        review = [t for t in trials if t["status"] == "needs_review"]
        pending = [t for t in trials if t["status"] in ("pending", "in_progress")]
        correct = [t for t in completed if t["correct"]]
        incomplete = [t for t in completed if t["telemetry_complete"] is False]
        reasons = defaultdict(int)
        for t in completed:
            reasons[t["stop_reason"]] += 1
        entry = {"model": key[0], "case": key[1], "arm": key[2], "planned": len(trials), "completed": len(completed),
                 "needs_review": len(review), "pending": len(pending), "correct": len(correct),
                 "telemetry_incomplete": len(incomplete), "stop_reasons": dict(reasons)}
        table1.append(entry)
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {len(trials)} | {len(completed)} | {len(review)} | {len(pending)} | {len(correct)} | {len(incomplete)} | {dict(reasons)} |")
    lines.append("")

    # 2. Consumption among correct trials with complete telemetry.
    lines += ["## Consumption among correct trials (complete telemetry only)", "",
              "| model | case | arm | n correct | median total tokens | min | max | median input | median output | median cached | median reasoning | median seconds | median tool calls |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    table2 = []
    for key in sorted(groups):
        ok = [t for t in groups[key] if t["status"] == "completed" and t["correct"] and t["telemetry_complete"]]
        tokens = [t["tokens"] for t in ok]
        sub = lambda name: _median([t["summary"].get("subtotals", {}).get(name) for t in ok])
        entry = {"model": key[0], "case": key[1], "arm": key[2], "n": len(ok), "median_tokens": _median(tokens),
                 "min": min(tokens) if tokens else None, "max": max(tokens) if tokens else None,
                 "median_input": sub("input_tokens"), "median_output": sub("output_tokens"),
                 "median_cached": sub("cached_tokens"), "median_reasoning": sub("reasoning_tokens"),
                 "median_seconds": _median([t["summary"].get("elapsed_seconds") for t in ok]),
                 "median_tool_calls": _median([t["summary"].get("tool_calls") for t in ok])}
        table2.append(entry)
        lines.append("| " + " | ".join(_fmt(entry[k]) for k in ("model", "case", "arm", "n", "median_tokens", "min", "max", "median_input", "median_output", "median_cached", "median_reasoning", "median_seconds", "median_tool_calls")) + " |")
    lines.append("")

    # 3. Unsuccessful consumption, kept visible.
    lines += ["## Unsuccessful or incomplete trials (consumption kept visible)", "",
              "| model | case | arm | trial | verdict | stop reason | exact tokens | known lower bound | telemetry |", "|---|---|---|---|---|---|---:|---:|---|"]
    table3 = []
    for row in rows:
        if row["status"] == "completed" and row["correct"] and row["telemetry_complete"]:
            continue
        if row["status"] in ("pending",):
            continue
        entry = {"model": row["model"], "case": row["case"], "arm": row["arm"], "trial": row["trial_id"],
                 "verdict": row["verdict"], "stop_reason": row["stop_reason"], "tokens": row["tokens"],
                 "lower_bound": row["summary"].get("known_token_lower_bound"),
                 "telemetry": "complete" if row["telemetry_complete"] else ("incomplete" if row["telemetry_complete"] is False else "n/a"),
                 "status": row["status"]}
        table3.append(entry)
        lines.append(f"| {entry['model']} | {entry['case']} | {entry['arm']} | {entry['trial'][:8]} | {entry['verdict']} | {entry['stop_reason']} | {_fmt(entry['tokens'])} | {_fmt(entry['lower_bound'])} | {entry['telemetry']} ({entry['status']}) |")
    lines.append("")

    # 4. Tokens per successful completion (descriptive, all attempts).
    lines += ["## Total tokens consumed per correct completion (all attempts, descriptive)", "",
              "| model | case | arm | attempts | correct | known tokens consumed | tokens per correct completion |", "|---|---|---|---:|---:|---:|---:|"]
    table4 = []
    for key in sorted(groups):
        done = [t for t in groups[key] if t["status"] == "completed"]
        consumed = sum((t["summary"].get("known_token_lower_bound") or 0) for t in done)
        correct = sum(1 for t in done if t["correct"])
        per = (consumed / correct) if correct else None
        entry = {"model": key[0], "case": key[1], "arm": key[2], "attempts": len(done), "correct": correct,
                 "consumed": consumed, "per_correct": per if correct else "undefined"}
        table4.append(entry)
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {len(done)} | {correct} | {consumed} | {_fmt(per) if correct else 'undefined'} |")
    lines.append("")

    # 5. Paired blocks.
    lines += ["## Paired differences (blocks where both arms are correct with complete telemetry)", "",
              "| model | case | comparison | qualifying pairs | of blocks | median difference (tokens) | median ratio |", "|---|---|---|---:|---:|---:|---:|"]
    pairs_out = []
    blocks = defaultdict(dict)
    for row in rows:
        blocks[(row["model"], row["case"], row["repetition"])][row["arm"]] = row
    comparisons = [("clean", "simple"), ("clean", "clean-no-traces"), ("clean-no-traces", "simple")]
    for model in sorted({r["model"] for r in rows}):
        for case in sorted({r["case"] for r in rows}):
            model_blocks = [b for k, b in blocks.items() if k[0] == model and k[1] == case]
            for left, right in comparisons:
                diffs, ratios = [], []
                for block in model_blocks:
                    a, b = block.get(left), block.get(right)
                    if a and b and a["correct"] and b["correct"] and a["telemetry_complete"] and b["telemetry_complete"]:
                        diffs.append(a["tokens"] - b["tokens"])
                        ratios.append(a["tokens"] / b["tokens"] if b["tokens"] else None)
                entry = {"model": model, "case": case, "comparison": f"{left} - {right}", "pairs": len(diffs),
                         "blocks": len(model_blocks), "median_difference": _median(diffs), "median_ratio": _median(ratios)}
                pairs_out.append(entry)
                lines.append(f"| {model} | {case} | {left} minus {right} | {len(diffs)} | {len(model_blocks)} | {_fmt(entry['median_difference'])} | {_fmt(entry['median_ratio'])} |")
    lines.append("")

    # 6. Cost.
    budget = json.loads((run_dir / "budget.json").read_text()) if (run_dir / "budget.json").exists() else {}
    known = sum(Decimal(t["summary"].get("known_cost_usd", "0")) for t in rows if t["summary"])
    lines += ["## Spend (rate-card estimates, not invoices)", "",
              f"- known solving cost: ${known}", f"- budget file: committed ${budget.get('committed_usd')} / cap ${budget.get('cap_usd')}; unresolved ${budget.get('unresolved_usd')}", ""]

    # 7. Timelines with cumulative usage.
    timelines = {}
    for row in rows:
        if not row["events"]:
            continue
        cumulative = 0
        solving = sorted((r for r in row["requests"] if r.get("purpose") == "solving"), key=lambda r: r["sequence"])
        usage_by_seq = [(r["sequence"], (r.get("derived") or {}).get("request_total")) for r in solving]
        timeline = []
        # Each tool event follows the response that requested it; attribute usage in order.
        response_index = 0
        for event in row["events"]:
            if str(event.get("tool", "")).startswith("_"):
                continue
            if response_index < len(usage_by_seq):
                cumulative += usage_by_seq[response_index][1] or 0
                response_index += 1
            timeline.append({"tool": event.get("tool"), "kind": event.get("kind"), "cumulative_tokens": cumulative,
                             "delivered_bytes": event.get("delivered_bytes"), "exit_code": event.get("exit_code")})
        timelines[row["trial_id"]] = {"arm": row["arm"], "case": row["case"], "model": row["model"],
                                      "correct": row["correct"], "timeline": timeline}

    report = {"tables": {"attempted": table1, "correct_consumption": table2, "unsuccessful": table3,
                         "per_completion": table4, "pairs": pairs_out},
              "known_cost_usd": str(known), "timelines": timelines, "markdown": "\n".join(lines)}
    (out_dir / "report.md").write_text(report["markdown"])
    (out_dir / "tables.json").write_text(json.dumps({k: v for k, v in report.items() if k != "markdown"}, indent=2, default=str))
    return report
