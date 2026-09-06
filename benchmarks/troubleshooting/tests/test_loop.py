"""Tool-loop behaviour with the scripted fake model: limits, telemetry, budget, crash recovery."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from harness.analysis import independent_raw_total
from harness.budget import BudgetGate
from harness.fake import DEFAULT_SCRIPT, DRY_RUN_PROFILE, FAKE_MODEL, S2_ANSWER, ScriptedClient
from harness.inference import InferenceError, ModelSettings
from harness.loop import Limits, TrialContext, TrialRunner
from harness.packaging import build_trial_workspace

SECRET = "sk-unit-test-secret-key-000000"


class LoopHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trial_dir = self.root / "trial"
        build_trial_workspace(self.trial_dir, "simple", "S2")

    def runner(self, client, limits=None, cap="5.00", arm="simple"):
        budget = BudgetGate(self.root / "run", Decimal(cap))
        ctx = TrialContext(trial_id="t1", trial_dir=self.trial_dir, workspace=self.trial_dir / "workspace",
                           vault=self.trial_dir / "vault", arm=arm, case="S2", model_settings=ModelSettings(FAKE_MODEL),
                           profile=DRY_RUN_PROFILE, limits=limits or Limits(), instructions="inst",
                           initial_input=(self.trial_dir / "workspace" / "README.md").read_text(), secrets=[SECRET])
        return TrialRunner(ctx, client, budget), budget

    @staticmethod
    def outputs(runner):
        return [i["output"] for i in runner.history if i.get("type") == "function_call_output"]

    def attempts(self):
        rows = {}
        for line in (self.trial_dir / "requests.jsonl").read_text().splitlines():
            row = json.loads(line)
            rows.setdefault(row["attempt_id"], []).append(row)
        return rows

    def test_happy_path_submits_with_exact_totals(self):
        runner, budget = self.runner(ScriptedClient())
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "submitted")
        self.assertTrue(summary["telemetry_complete"])
        self.assertEqual(summary["inference_calls"], len(DEFAULT_SCRIPT))
        self.assertEqual(summary["exact_total_tokens"], independent_raw_total(self.trial_dir))
        self.assertTrue((self.trial_dir / "submission.md").exists())
        self.assertEqual(json.loads((self.trial_dir / "submission.json").read_text()), S2_ANSWER)
        # Every attempt has a 'sent' row before its terminal row; preflight rows carry no solving tokens.
        for rows in self.attempts().values():
            self.assertEqual(rows[0]["status"], "sent")
            self.assertEqual(len(rows), 2)
        preflight = [r[-1] for r in self.attempts().values() if r[0]["purpose"] == "preflight"]
        self.assertEqual(len(preflight), len(DEFAULT_SCRIPT))
        self.assertTrue(all(r["telemetry"] == "not_applicable" for r in preflight))
        solving_total = sum(r[-1]["derived"]["request_total"] for r in self.attempts().values() if r[0]["purpose"] == "solving")
        self.assertEqual(solving_total, summary["exact_total_tokens"])
        # Budget settled: no outstanding reserve, committed equals estimated cost.
        self.assertEqual(budget.state.reserved_usd, Decimal("0"))
        self.assertEqual(str(budget.state.committed_usd), summary["estimated_cost_usd"])
        # Tool results were sent back as model input with the call ids.
        second = json.loads((self.trial_dir / "responses" / "0004-solving-request.json").read_text())
        outputs = [i for i in second["input"] if i.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["call_id"], "call_1")
        self.assertIn("reasoning", {i.get("type") for i in second["input"]})

    def test_v04_timeout_marks_unknown_and_sends_no_third_call(self):
        client = ScriptedClient(fail_on_call={2: InferenceError("timeout", "slow")})
        runner, budget = self.runner(client)
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "transport_error")
        self.assertEqual(client.create_calls, 2)
        self.assertFalse(summary["telemetry_complete"])
        self.assertIsNone(summary["exact_total_tokens"])
        self.assertGreater(summary["known_token_lower_bound"], 0)
        self.assertEqual(len(summary["missing_attempt_ids"]), 1)
        self.assertGreater(Decimal(summary["unresolved_reserve_usd"]), 0)
        self.assertGreater(budget.state.unresolved_usd, 0)
        timeout_rows = [r for rows in self.attempts().values() for r in rows if r.get("status") == "timeout"]
        self.assertEqual(timeout_rows[0]["telemetry"], "unknown")

    def test_v05_incomplete_response_counts_usage_and_is_not_a_submission(self):
        runner, _ = self.runner(ScriptedClient(incomplete_on=2))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "generation_limit")
        self.assertFalse(summary["submitted"])
        self.assertEqual(summary["inference_calls"], 2)
        self.assertEqual(summary["exact_total_tokens"], independent_raw_total(self.trial_dir))

    def test_token_cap_stops_before_sending(self):
        runner, _ = self.runner(ScriptedClient(), Limits(token_cap=3_000))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "token_limit")
        self.assertLessEqual(summary["exact_total_tokens"], 3_000)

    def test_tool_and_inference_limits(self):
        runner, _ = self.runner(ScriptedClient(), Limits(max_tool_calls=2))
        self.assertEqual(runner.run()["stop_reason"], "tool_limit")
        build_trial_workspace(self.trial_dir, "simple", "S2")
        runner, _ = self.runner(ScriptedClient(), Limits(max_inference_calls=1))
        self.assertEqual(runner.run()["stop_reason"], "inference_limit")

    def test_time_limit_terminates_and_keeps_records(self):
        runner, _ = self.runner(ScriptedClient(), Limits(max_seconds=0.0))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "time_limit")
        self.assertTrue((self.trial_dir / "summary.json").exists())

    def test_invalid_usage_pauses_batch(self):
        runner, _ = self.runner(ScriptedClient(bad_usage_on=1))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "usage_invalid")
        self.assertTrue(summary["pause_batch"])
        self.assertFalse(summary["telemetry_complete"])

    def test_unexpected_model_or_tier_is_protocol_violation(self):
        runner, _ = self.runner(ScriptedClient(returned_model="other-model"))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "protocol_violation")
        self.assertTrue(summary["pause_batch"])
        build_trial_workspace(self.trial_dir, "simple", "S2")
        runner, _ = self.runner(ScriptedClient(tier="priority"))
        self.assertEqual(runner.run()["stop_reason"], "protocol_violation")

    def test_snapshot_suffix_matches_requested_model(self):
        runner, _ = self.runner(ScriptedClient(returned_model=f"{FAKE_MODEL}-2026-09-01"))
        self.assertEqual(runner.run()["stop_reason"], "submitted")

    def test_budget_cap_refuses_before_post(self):
        client = ScriptedClient()
        runner, budget = self.runner(client, cap="0.01")
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "budget_cap")
        self.assertTrue(summary["pause_batch"])
        self.assertEqual(client.create_calls, 0)
        self.assertEqual(budget.state.refusals, 1)

    def test_cancel_file_stops_scheduling(self):
        client = ScriptedClient()
        runner, budget = self.runner(client)
        budget.cancel("operator stop")
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "cancelled")
        self.assertEqual(client.create_calls, 0)

    def test_text_only_turn_is_nudged_once_then_treated_as_submission(self):
        runner, _ = self.runner(ScriptedClient(script=[]))
        summary = runner.run()
        self.assertEqual(summary["stop_reason"], "submitted_text")
        self.assertEqual(summary["nudges"], 1)
        self.assertEqual(summary["inference_calls"], 2)

    def test_v08_key_absent_from_every_trial_artifact_and_tool_environment(self):
        script = [("run_shell", {"command": "env; python3 -c 'import os; print(sorted(os.environ))'", "timeout_seconds": 10}),
                  ("submit_diagnosis", S2_ANSWER)]
        runner, _ = self.runner(ScriptedClient(script))
        runner.run()
        env_output = (self.trial_dir / "tool-outputs" / "0001-run_shell.txt").read_text()
        self.assertNotIn("OPEN_AI", env_output)
        self.assertNotIn("sk-", env_output)
        for path in self.trial_dir.rglob("*"):
            if path.is_file() and path.suffix in (".json", ".jsonl", ".txt", ".md"):
                self.assertNotIn(SECRET, path.read_text(errors="replace"), path)

    def test_tool_output_truncation_metadata(self):
        script = [("run_shell", {"command": "python3 -c 'print(\"x\" * 40000)'", "timeout_seconds": 10}),
                  ("submit_diagnosis", S2_ANSWER)]
        runner, _ = self.runner(ScriptedClient(script))
        runner.run()
        events = [json.loads(l) for l in (self.trial_dir / "tool-events.jsonl").read_text().splitlines()]
        self.assertTrue(events[0]["truncated"])
        self.assertEqual(events[0]["raw_output_bytes"] > 40000, True)
        self.assertLessEqual(events[0]["delivered_bytes"], 16 * 1024 + 200)
        self.assertIn("output truncated", self.outputs(runner)[0])

    def test_workspace_paths_are_neutral_in_tool_output(self):
        script = [("run_shell", {"command": "pwd; ls /workspace; echo $HOME", "timeout_seconds": 10}),
                  ("submit_diagnosis", S2_ANSWER)]
        runner, _ = self.runner(ScriptedClient(script))
        runner.run()
        out = self.outputs(runner)[0]
        self.assertIn("/workspace", out)
        self.assertNotIn(str(self.trial_dir), out)
        self.assertIn("app", out)

    def test_reproduction_is_fresh_sanitized_and_recorded(self):
        import sqlite3

        script = [("reproduce_incident", {}), ("reproduce_incident", {}), ("submit_diagnosis", S2_ANSWER)]
        runner, _ = self.runner(ScriptedClient(script))
        summary = runner.run()
        self.assertEqual(summary["reproductions"], 2)
        for n in ("01", "02"):
            db = self.trial_dir / "workspace" / "incident" / "reproductions" / n / "ledger.db"
            kinds = {k for k, in sqlite3.connect(db).execute("select type from sqlite_master")}
            self.assertNotIn("trigger", kinds)
            stderr = (db.parent / "stderr.txt").read_text()
            self.assertIn("database or disk is full", stderr)
            self.assertNotIn(str(self.trial_dir), stderr)
        self.assertIn("Output directory: /workspace/incident/reproductions/02", self.outputs(runner)[1])


class CrashRecoveryTests(unittest.TestCase):
    """V11: a response saved but not acted on is never resent; an unanswered sent row needs review."""

    def test_scheduler_marks_in_progress_trial_for_review_and_does_not_resend(self):
        from harness import scheduler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "m.json"
            manifest.write_text(json.dumps({
                "experiment_version": "t", "phase": "dry-run", "models": {"m": {"id": "fake-model"}}, "arms": ["simple"],
                "cases": ["S2"], "repetitions": 1, "scheduler_seed": 1, "batch_usd_cap": "5.00",
                "pricing_snapshot": "pricing/openai-2026-09-06.json"}))
            run_dir = scheduler.plan_run(manifest, run_id="crash", runs_dir=root)
            plan = scheduler.load_plan(run_dir)
            state = scheduler.load_state(run_dir)
            trial_id = plan[0]["trial_id"]
            state["trials"][trial_id]["status"] = "in_progress"
            scheduler.save_state(run_dir, state)
            outcome = scheduler.execute_run(None, run_dir, dry_run=True)
            self.assertEqual(outcome["needs_review"], [trial_id])
            self.assertEqual(outcome["executed"], [])
            self.assertEqual(scheduler.load_state(run_dir)["trials"][trial_id]["status"], "needs_review")

    def test_ledger_reduction_is_idempotent(self):
        from harness.ledger import RequestLedger

        with tempfile.TemporaryDirectory() as tmp:
            ledger = RequestLedger(Path(tmp), "t")
            row = ledger.open_attempt("solving", {"model": "x"}, "x")
            ledger.close_attempt(row, status="completed", raw_usage={"input_tokens": 1}, derived={"request_total": 3})
            first = ledger.attempts()
            second = RequestLedger(Path(tmp), "t").attempts()
            self.assertEqual(first, second)
            self.assertEqual(len(first), 1)
            self.assertEqual(first[row["attempt_id"]]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
