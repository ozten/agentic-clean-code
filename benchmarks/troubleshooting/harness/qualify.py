"""Harness qualification exercise, unrelated to the payment incidents (design R08, V10).

The model inspects a small Python file, runs its supplied test, and returns a grounded answer
through a submit tool. It exercises: two or more function-tool turns with call ids carried
into later inputs, tool results counted as model input, exact usage aggregation matching an
independent raw-JSON sum, and the protocol settings (OA03) being accepted by the model.
Real calls happen only through an explicit manifest with a batch_usd_cap.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .analysis import independent_raw_total
from .budget import BudgetGate
from .env import load_settings
from .inference import ModelSettings
from .ledger import now_iso
from .loop import Limits, TrialContext, TrialRunner
from .scheduler import (harness_source_hash, load_manifest, load_pricing, make_client, model_settings_for,
                        profile_for, sdk_version)
from .tools import TOOL_SCHEMAS, ToolExecutor

STATS_PY = '''"""Small statistics helpers."""


def middle(values):
    """Return the lower-middle element of the sorted values (not the mean of the two middles)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    return ordered[(len(ordered) - 1) // 2]


def spread(values):
    return max(values) - min(values)
'''

TEST_PY = '''import unittest

from stats import middle, spread


class StatsTests(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(middle([3, 1, 2]), 2)

    def test_even_lower_middle(self):
        self.assertEqual(middle([4, 1, 3, 2]), 2)

    def test_spread(self):
        self.assertEqual(spread([4, 1, 3, 2]), 3)


if __name__ == "__main__":
    unittest.main()
'''

QUESTION = """# Qualification workspace

The directory `app/` holds a small Python module `app/stats.py` and its test `app/test_stats.py`.

1. Read `app/stats.py`.
2. Run the test file with `run_shell` (for example `cd app && python3 -B -m unittest -v test_stats`).
3. Call `submit_answer` with: the exact value `middle([9, 4, 7, 1])` returns according to the
   source you read; how many tests ran and how many failed; and the file and line you relied on.

Paths are relative to the workspace root. Do not guess: read and run.
"""

SUBMIT_SCHEMA = {"type": "function", "name": "submit_answer", "strict": True,
                 "description": "Submit the qualification answer. The exercise ends at this call.",
                 "parameters": {"type": "object", "additionalProperties": False,
                                "properties": {"middle_value": {"type": "string", "description": "Exact return value of middle([9, 4, 7, 1])."},
                                               "tests_ran": {"type": "integer"}, "tests_failed": {"type": "integer"},
                                               "evidence": {"type": "string", "description": "File and line relied on."}},
                                "required": ["middle_value", "tests_ran", "tests_failed", "evidence"]}}
QUALIFY_TOOLS = [t for t in TOOL_SCHEMAS if t["name"] not in ("reproduce_incident", "submit_diagnosis")] + [SUBMIT_SCHEMA]
QUALIFY_FIELDS = ("middle_value", "tests_ran", "tests_failed", "evidence")

QUALIFY_SCRIPT = [
    ("read_file", {"path": "app/stats.py", "start_line": None, "max_lines": None}),
    ("run_shell", {"command": "cd app && python3 -B -m unittest -v test_stats", "timeout_seconds": 30}),
    ("submit_answer", {"middle_value": "4", "tests_ran": 3, "tests_failed": 0, "evidence": "app/stats.py:7"}),
]


def build_qualification_workspace(trial_dir: Path) -> Path:
    workspace = trial_dir / "workspace"
    (workspace / "app").mkdir(parents=True, exist_ok=True)
    (workspace / "scratch").mkdir(exist_ok=True)
    (workspace / "app" / "stats.py").write_text(STATS_PY)
    (workspace / "app" / "test_stats.py").write_text(TEST_PY)
    (workspace / "README.md").write_text(QUESTION)
    (trial_dir / "vault").mkdir(exist_ok=True)
    return workspace


def evaluate_answer(submission: dict | None) -> tuple[bool, list[str]]:
    problems = []
    if not submission:
        return False, ["no submission"]
    if str(submission.get("middle_value", "")).strip() != "4":
        problems.append(f"middle_value {submission.get('middle_value')!r} != '4'")
    if str(submission.get("tests_ran")) != "3":
        problems.append(f"tests_ran {submission.get('tests_ran')!r} != 3")
    if str(submission.get("tests_failed")) != "0":
        problems.append(f"tests_failed {submission.get('tests_failed')!r} != 0")
    if "stats.py" not in str(submission.get("evidence", "")):
        problems.append("evidence does not cite app/stats.py")
    return not problems, problems


def run_qualification(manifest_path: Path, dry_run: bool = False, model_role: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    settings = load_settings()
    run_dir = (settings.runs_dir / f"qualification-{now_iso().replace(':', '').replace('-', '')[:15]}").resolve()
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({**manifest, "phase": "qualification", "dry_run": dry_run,
                                                        "harness_source_sha256": harness_source_hash(),
                                                        "openai_sdk_version": sdk_version(), "frozen_at": now_iso()}, indent=2))
    if not dry_run:
        from .preflight import format_report, run_preflight

        result = run_preflight()
        print(format_report(result))
        if not result.ok:
            return {"ok": False, "escalate": result.kind, "message": result.escalation_message()}
    budget = BudgetGate(run_dir, Decimal(str(manifest.get("qualification_usd_cap", manifest["batch_usd_cap"]))))
    outcomes = {}
    all_ok = True
    roles = [model_role] if model_role else list(manifest["models"])
    pricing_path = None
    for role in roles:
        trial_dir = run_dir / "trials" / role
        trial_dir.mkdir(parents=True)
        workspace = build_qualification_workspace(trial_dir)
        if dry_run:
            from .fake import DRY_RUN_PROFILE, ScriptedClient

            client = ScriptedClient(QUALIFY_SCRIPT)
            profile = DRY_RUN_PROFILE
        else:
            client = make_client(manifest, False, 120.0)
            from .env import REPO_ROOT

            profiles = load_pricing(REPO_ROOT / "benchmarks" / "troubleshooting" / manifest["pricing_snapshot"])
            profile = profiles[manifest["models"][role].get("pricing_profile") or manifest["models"][role]["id"]]
        ctx = TrialContext(
            trial_id=f"qualification-{role}", trial_dir=trial_dir, workspace=workspace, vault=trial_dir / "vault",
            arm="qualification", case="Q0", model_settings=model_settings_for(manifest, role, dry_run), profile=profile,
            limits=Limits(max_inference_calls=12, max_tool_calls=12, max_seconds=300),
            instructions="You are verifying a small Python module. Use the tools; read and run before answering. "
                         "Finish by calling submit_answer.",
            initial_input=QUESTION, secrets=[settings.openai_api_key], tool_schemas=QUALIFY_TOOLS,
            submit_tool="submit_answer", submit_fields=QUALIFY_FIELDS)
        executor = ToolExecutor(trial_dir, workspace, trial_dir / "vault", None, None)
        runner = TrialRunner(ctx, client, budget, executor)
        summary = runner.run()
        answer_ok, problems = evaluate_answer(runner.submission)
        # V10 checks
        solving_payloads = [json.loads(p.read_text()) for p in sorted((trial_dir / "responses").glob("*-solving-request.json"))]
        call_ids_preserved = all(
            any(item.get("type") == "function_call_output" for item in payload["input"])
            for payload in solving_payloads[1:]) if len(solving_payloads) > 1 else False
        raw_total = independent_raw_total(trial_dir)
        totals_match = raw_total == summary["exact_total_tokens"]
        returned_models = {r.get("returned_model") for r in runner.ledger.attempts().values() if r.get("purpose") == "solving"}
        returned_tiers = {r.get("returned_service_tier") for r in runner.ledger.attempts().values() if r.get("purpose") == "solving"}
        ok = answer_ok and summary["stop_reason"] == "submitted" and summary["inference_calls"] >= 2 \
            and call_ids_preserved and totals_match and summary["telemetry_complete"]
        all_ok &= ok
        outcomes[role] = {"ok": ok, "answer_ok": answer_ok, "problems": problems, "stop_reason": summary["stop_reason"],
                          "inference_calls": summary["inference_calls"], "tool_calls": summary["tool_calls"],
                          "exact_total_tokens": summary["exact_total_tokens"], "independent_raw_total": raw_total,
                          "totals_match": totals_match, "call_ids_preserved": call_ids_preserved,
                          "returned_models": sorted(m for m in returned_models if m), "returned_tiers": sorted(t or "null" for t in returned_tiers),
                          "estimated_cost_usd": summary["estimated_cost_usd"], "subtotals": summary["subtotals"],
                          "trial_dir": str(trial_dir)}
    result = {"ok": all_ok, "run_dir": str(run_dir), "models": outcomes, "budget": budget.summary(), "dry_run": dry_run}
    (run_dir / "qualification-result.json").write_text(json.dumps(result, indent=2, default=str))
    return result
