"""P6: tables from synthetic run directories; incomplete telemetry has no exact total; all attempts visible."""
import json
import tempfile
import unittest
from pathlib import Path

from harness.analysis import analyze_run


def make_run(root: Path, trials: list[dict]) -> Path:
    run = root / "run"
    (run / "trials").mkdir(parents=True)
    plan, state = [], {}
    for index, t in enumerate(trials, start=1):
        trial_id = f"trial-{index}"
        plan.append({"order": index, "trial_id": trial_id, "block_id": f"m-{t['case']}-r{t['rep']}", "model_role": "m",
                     "model": "model-x", "case": t["case"], "repetition": t["rep"], "arm": t["arm"], "replaces": None})
        state[trial_id] = {"status": t.get("status", "completed")}
        d = run / "trials" / trial_id
        d.mkdir()
        (d / "trial.json").write_text(json.dumps(plan[-1]))
        complete = t.get("tokens") is not None
        (d / "summary.json").write_text(json.dumps({
            "stop_reason": t.get("stop", "submitted"), "exact_total_tokens": t.get("tokens"),
            "known_token_lower_bound": t.get("lower", t.get("tokens") or 0), "telemetry_complete": complete,
            "subtotals": {"input_tokens": (t.get("tokens") or 0) - 100 if complete else None, "output_tokens": 100 if complete else None,
                          "cached_tokens": 0, "reasoning_tokens": 0}, "elapsed_seconds": 10, "tool_calls": 3,
            "known_cost_usd": "0.01", "estimated_cost_usd": "0.01" if complete else None}))
        (d / "grade.json").write_text(json.dumps({"final": {"correct": t.get("correct", True),
                                                             "verdict": "correct" if t.get("correct", True) else "incorrect"}}))
    (run / "plan.json").write_text(json.dumps({"trials": plan}))
    (run / "state.json").write_text(json.dumps({"trials": state, "paused": None}))
    (run / "manifest.json").write_text(json.dumps({"run_id": "run", "experiment_version": "t"}))
    (run / "budget.json").write_text(json.dumps({"cap_usd": "5", "committed_usd": "0.05", "reserved_usd": "0", "unresolved_usd": "0"}))
    return run


class AnalysisTests(unittest.TestCase):
    def test_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(Path(tmp), [
                {"case": "S2", "rep": 1, "arm": "simple", "tokens": 20000},
                {"case": "S2", "rep": 1, "arm": "clean", "tokens": 12000},
                {"case": "S2", "rep": 1, "arm": "clean-no-traces", "tokens": 18000},
                {"case": "S2", "rep": 2, "arm": "simple", "tokens": 22000},
                {"case": "S2", "rep": 2, "arm": "clean", "tokens": None, "lower": 5000, "stop": "transport_error"},
                {"case": "S2", "rep": 2, "arm": "clean-no-traces", "tokens": 3000, "correct": False},
                {"case": "S2", "rep": 3, "arm": "simple", "status": "needs_review"},
                {"case": "S2", "rep": 3, "arm": "clean", "status": "pending"},
                {"case": "S2", "rep": 3, "arm": "clean-no-traces", "status": "pending"},
            ])
            report = analyze_run(run)
            attempted = {(r["arm"]): r for r in report["tables"]["attempted"]}
            self.assertEqual(attempted["simple"]["completed"], 2)
            self.assertEqual(attempted["simple"]["needs_review"], 1)
            self.assertEqual(attempted["clean"]["telemetry_incomplete"], 1)
            self.assertEqual(attempted["clean-no-traces"]["correct"], 1)
            consumption = {r["arm"]: r for r in report["tables"]["correct_consumption"]}
            self.assertEqual(consumption["clean"]["n"], 1)               # the incomplete one is excluded
            self.assertEqual(consumption["simple"]["median_tokens"], 21000)
            unsuccessful = {r["trial"]: r for r in report["tables"]["unsuccessful"]}
            self.assertIn("trial-5", unsuccessful)                        # incomplete telemetry stays visible
            self.assertIsNone(unsuccessful["trial-5"]["tokens"])
            self.assertEqual(unsuccessful["trial-5"]["lower_bound"], 5000)
            self.assertIn("trial-6", unsuccessful)                        # short wrong answer is not a success
            self.assertIn("trial-7", unsuccessful)
            pairs = {r["comparison"]: r for r in report["tables"]["pairs"]}
            self.assertEqual(pairs["clean - simple"]["pairs"], 1)
            self.assertEqual(pairs["clean - simple"]["blocks"], 3)
            self.assertEqual(pairs["clean - simple"]["median_difference"], -8000)
            per = {r["arm"]: r for r in report["tables"]["per_completion"]}
            self.assertEqual(per["clean-no-traces"]["per_correct"], 21000)  # 18000 + 3000 consumed / 1 correct
            self.assertTrue((run / "analysis" / "report.md").exists())
            self.assertIn("kept visible", report["markdown"])

    def test_zero_success_arm_is_undefined(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = make_run(Path(tmp), [{"case": "S1", "rep": 1, "arm": "simple", "tokens": 100, "correct": False}])
            report = analyze_run(run)
            self.assertEqual(report["tables"]["per_completion"][0]["per_correct"], "undefined")


if __name__ == "__main__":
    unittest.main()
