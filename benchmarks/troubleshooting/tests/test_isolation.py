"""P1 parity and P2 isolation acceptance criteria as automated checks."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from harness.apps import ARMS
from harness.cases import CASES
from harness.incident import check_parity
from harness.isolation import FORBIDDEN_MARKERS, run_leak_checks
from harness.packaging import build_trial_workspace


class ParityTests(unittest.TestCase):
    def test_all_arms_match_for_happy_and_s1_to_s3(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = check_parity(Path(tmp))
            self.assertTrue(report["parity"], report["problems"])
            for case_id in ("S1", "S2", "S3"):
                arms = report["cases"][case_id]
                self.assertEqual({a["exit"] for a in arms.values()}, {1})
                self.assertTrue(all(a["has_traceback"] for a in arms.values()), "traceback must remain in every arm")
                self.assertEqual(len({a["error"] for a in arms.values()}), 1)
            self.assertEqual({a["traces"] for k, a in report["cases"]["S2"].items() if k != "clean"}, {0})
            self.assertEqual(report["cases"]["S2"]["clean"]["traces"], 3)
            self.assertEqual(report["cases"]["S1"]["clean"]["traces"], 1)
            self.assertEqual(report["cases"]["S3"]["clean"]["traces"], 2)


class WorkspaceTests(unittest.TestCase):
    def test_supplied_database_has_no_trigger_and_no_evaluator_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ARMS:
                trial = Path(tmp) / arm
                build_trial_workspace(trial, arm, "S2")
                db = trial / "workspace" / "incident" / "ledger.db"
                kinds = {k for k, in sqlite3.connect(db).execute("select type from sqlite_master")}
                self.assertNotIn("trigger", kinds)
                self.assertNotIn(b"TRIGGER", db.read_bytes())
                vault_kinds = {k for k, in sqlite3.connect(trial / "vault" / "ledger.db").execute("select type from sqlite_master")}
                self.assertIn("trigger", vault_kinds)
                for path in (trial / "workspace").rglob("*"):
                    if path.is_file() and path.suffix != ".db":
                        text = path.read_text(errors="replace")
                        for marker in FORBIDDEN_MARKERS:
                            self.assertNotIn(marker, text, f"{marker} in {path}")
                        self.assertNotIn(str(trial), text)

    def test_excluded_files_never_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ARMS:
                trial = Path(tmp) / arm
                build_trial_workspace(trial, arm, "S1")
                names = {p.name for p in (trial / "workspace" / "app").rglob("*")}
                for banned in ("README.md", "demo.py", "test_payment.py", "faults.py", "compare.py", "evaluator-result.json"):
                    self.assertNotIn(banned, names)
                self.assertEqual({"success.json", "timeout.json"}, {p.name for p in (trial / "workspace" / "app" / "fixtures").iterdir()})
                manifest = json.loads((trial / "workspace-manifest.json").read_text())
                self.assertIn("incident/stderr.txt", manifest["files"])
                self.assertIn("README.md", manifest["files"])

    def test_traceback_paths_are_normalized_and_useful(self):
        with tempfile.TemporaryDirectory() as tmp:
            for arm in ARMS:
                trial = Path(tmp) / arm
                build_trial_workspace(trial, arm, "S2")
                stderr = (trial / "workspace" / "incident" / "stderr.txt").read_text()
                self.assertIn("Traceback (most recent call last)", stderr)
                self.assertIn("/workspace/app/", stderr)
                self.assertIn("UPDATE payments SET transfer_id", stderr)
                self.assertNotIn(str(Path(tmp)), stderr)
                self.assertNotIn("harness", stderr)

    def test_clean_trace_metadata_has_no_host_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial = Path(tmp) / "clean"
            build_trial_workspace(trial, "clean", "S2")
            for trace in (trial / "workspace" / "incident" / "traces").glob("*/trace.json"):
                text = trace.read_text()
                self.assertNotIn(str(tmp), text)
                self.assertNotIn("/Users/", text)
                self.assertNotIn("hidden_", text)

    def test_case_digests_are_stable(self):
        self.assertEqual(len({c.digest() for c in CASES.values()}), 3)


class LeakCheckTests(unittest.TestCase):
    def test_adversarial_probes_reveal_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_leak_checks(Path(tmp))
            self.assertTrue(report["passed"], json.dumps(report["summary"]["failed"], indent=1))
            self.assertGreaterEqual(report["summary"]["probes"], 40)


if __name__ == "__main__":
    unittest.main()
