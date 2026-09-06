"""P4: fixed manifest, randomized blocks, resume without double billing, replacements, spend estimate."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from harness import scheduler
from harness.budget import BudgetExceeded, BudgetGate

MANIFEST = {"experiment_version": "t", "phase": "dry-run", "models": {"efficient": {"id": "fake-model"}, "control": {"id": "fake-model"}},
            "arms": ["simple", "clean", "clean-no-traces"], "cases": ["S2"], "repetitions": 3, "scheduler_seed": 20260906,
            "batch_usd_cap": "5.00", "pricing_snapshot": "pricing/openai-2026-09-06.json"}


class PlanTests(unittest.TestCase):
    def test_plan_is_seeded_and_interleaves_arms(self):
        a = scheduler.build_plan(MANIFEST)
        b = scheduler.build_plan(MANIFEST)
        self.assertEqual([t["arm"] for t in a], [t["arm"] for t in b])
        self.assertEqual(len(a), 18)
        orders = {tuple(t["arm"] for t in a[i:i + 3]) for i in range(0, 18, 3)}
        self.assertGreater(len(orders), 1, "arm order must vary between blocks")
        self.assertNotEqual([t["arm"] for t in a[:6]], ["simple"] * 6)

    def test_manifest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps({**MANIFEST, "batch_usd_cap": "0"}))
            with self.assertRaises(ValueError):
                scheduler.load_manifest(path)
            path.write_text(json.dumps({**MANIFEST, "models": {"x": {"id": ""}}}))
            with self.assertRaises(ValueError):
                scheduler.load_manifest(path)
            bad = dict(MANIFEST)
            del bad["batch_usd_cap"]
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                scheduler.load_manifest(path)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / "m.json"
        self.manifest.write_text(json.dumps({**MANIFEST, "repetitions": 1, "models": {"m": {"id": "fake-model"}}}))
        self.run_dir = scheduler.plan_run(self.manifest, run_id="r1", runs_dir=self.root)

    def test_frozen_manifest_records_versions_and_hashes(self):
        frozen = json.loads((self.run_dir / "manifest.json").read_text())
        for key in ("harness_source_sha256", "openai_sdk_version", "tool_schema_sha256", "instructions_sha256",
                    "task_prompt_sha256", "pricing_snapshot_sha256", "cases_frozen", "fixed_request_settings"):
            self.assertIn(key, frozen)
        self.assertEqual(frozen["openai_sdk_version"], "3.8.0")
        self.assertTrue((self.run_dir / "pricing-snapshot.json").exists())

    def test_resume_never_bills_a_completed_trial_again(self):
        first = scheduler.execute_run(None, self.run_dir, dry_run=True, max_trials=2)
        self.assertEqual(len(first["executed"]), 2)
        committed_after_first = Decimal(BudgetGate(self.run_dir).state.committed_usd)
        second = scheduler.execute_run(None, self.run_dir, dry_run=True)
        self.assertEqual(second["skipped_completed"], 2)
        self.assertEqual(len(second["executed"]), 1)
        self.assertEqual(second["remaining"], 0)
        third = scheduler.execute_run(None, self.run_dir, dry_run=True)
        self.assertEqual(third["executed"], [])
        self.assertEqual(Decimal(BudgetGate(self.run_dir).state.committed_usd),
                         committed_after_first + Decimal(second["executed"][0]["cost"]))
        # Every trial directory holds exactly one ledger and one summary.
        for trial in scheduler.load_plan(self.run_dir):
            self.assertTrue((self.run_dir / "trials" / trial["trial_id"] / "summary.json").exists())

    def test_replacement_keeps_original_record(self):
        scheduler.execute_run(None, self.run_dir, dry_run=True, max_trials=1)
        original = scheduler.load_plan(self.run_dir)[0]
        replacement = scheduler.replace_trial(self.run_dir, original["trial_id"], "infrastructure failure")
        state = scheduler.load_state(self.run_dir)
        self.assertEqual(state["trials"][original["trial_id"]]["status"], "replaced")
        self.assertEqual(replacement["replaces"], original["trial_id"])
        self.assertTrue((self.run_dir / "trials" / original["trial_id"] / "summary.json").exists())
        outcome = scheduler.execute_run(None, self.run_dir, dry_run=True)
        self.assertIn(replacement["trial_id"], [e["trial_id"] for e in outcome["executed"]])

    def test_cancel_stops_new_trials(self):
        scheduler.cancel_run(self.run_dir, "stop now")
        outcome = scheduler.execute_run(None, self.run_dir, dry_run=True)
        self.assertEqual(outcome["executed"], [])
        self.assertEqual(outcome["paused"], "cancelled")

    def test_budget_cap_enforced_across_trials(self):
        gate = BudgetGate(self.root / "gate", Decimal("0.10"))
        gate.admit(Decimal("0.06"), "solving", "a")
        with self.assertRaises(BudgetExceeded):
            gate.admit(Decimal("0.05"), "solving", "b")
        gate.settle(Decimal("0.06"), Decimal("0.01"), "solving", "a")
        gate.admit(Decimal("0.05"), "solving", "b")
        gate.hold_unresolved(Decimal("0.05"), "solving", "b", "timeout")
        self.assertEqual(gate.state.unresolved_usd, Decimal("0.05"))
        self.assertEqual(gate.headroom, Decimal("0.04"))
        with self.assertRaises(ValueError):
            BudgetGate(self.root / "gate", Decimal("1.00"))     # cap cannot be changed silently

    def test_estimate_reports_expected_and_worst_case(self):
        path = self.root / "real.json"
        path.write_text(json.dumps({**MANIFEST, "models": {"efficient": {"id": "gpt-5.6-luna"}, "control": {"id": "gpt-5.6-terra"}},
                                    "batch_usd_cap": "15.00"}))
        estimate = scheduler.estimate_spend(path)
        self.assertEqual(estimate["trials"], 18)
        self.assertGreater(Decimal(estimate["worst_case_usd"]), Decimal(estimate["expected_usd"]))
        self.assertTrue(estimate["cap_covers_worst_case"])
        self.assertEqual(Decimal(estimate["by_model"]["control"]["worst_case_usd_per_trial"]), Decimal("1.20"))


if __name__ == "__main__":
    unittest.main()
