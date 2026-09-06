"""P5: fixture answers receive the expected grades; measurement-ready grading checks."""
import json
import tempfile
import unittest
from pathlib import Path

from harness.grading import finalize, machine_grade, record_human_review

FIXTURES = Path(__file__).resolve().parents[1] / "grading" / "fixtures"
FILES = {"app/app.py", "app/core.py", "app/adapters.py", "app/tracing.py", "app/main.py", "app/fixtures/success.json",
         "app/fixtures/timeout.json", "incident/stderr.txt", "incident/stdout.txt", "incident/ledger.db",
         "incident/report.md", "incident/traces/trace-1/trace.json"}


class FixtureGrades(unittest.TestCase):
    def test_every_fixture_gets_its_expected_verdict(self):
        for path in sorted(FIXTURES.glob("*.json")):
            fixture = json.loads(path.read_text())
            with self.subTest(fixture=path.stem):
                grade = machine_grade(fixture["submission"], fixture["case"], FILES)
                self.assertEqual(grade["verdict"], fixture["expected_verdict"], grade)
                self.assertEqual(grade["correct"], fixture["expected_verdict"] == "correct")

    def test_short_wrong_answer_cannot_be_correct(self):
        fixture = json.loads((FIXTURES / "s2-short-wrong.json").read_text())
        grade = machine_grade(fixture["submission"], "S2", FILES)
        self.assertFalse(grade["correct"])
        self.assertGreaterEqual(len(grade["failed"]), 4)

    def test_settlement_claim_fails_even_with_transfer_id(self):
        fixture = json.loads((FIXTURES / "s2-correct.json").read_text())
        sub = dict(fixture["submission"])
        sub["external_outcome"] = "Transfer tr_demo_500 was created and the money has arrived at the bank, so it settled."
        grade = machine_grade(sub, "S2", FILES)
        self.assertFalse(grade["correct"])
        self.assertIn("settlement", " ".join(grade["disqualifiers"]))

    def test_invented_transfer_id_is_disqualifying(self):
        fixture = json.loads((FIXTURES / "s3-correct.json").read_text())
        sub = dict(fixture["submission"])
        sub["external_outcome"] = "The provider created transfer tr_1Abc999 but the response was lost."
        grade = machine_grade(sub, "S3", FILES)
        self.assertFalse(grade["correct"])

    def test_nonexistent_citation_is_unsupported(self):
        fixture = json.loads((FIXTURES / "s2-correct.json").read_text())
        sub = dict(fixture["submission"])
        sub["evidence"] = "See app/payment_service.py line 40."
        sub["failed_boundary"] = sub["failed_boundary"].replace("app/adapters.py", "the adapters module")
        grade = machine_grade(sub, "S2", FILES)
        self.assertEqual(grade["verdict"], "unsupported")

    def test_free_text_submission_is_graded(self):
        fixture = json.loads((FIXTURES / "s2-correct.json").read_text())
        text = "\n".join(fixture["submission"].values())
        grade = machine_grade({"free_text": text}, "S2", FILES)
        self.assertTrue(grade["free_text_submission"])
        self.assertEqual(grade["verdict"], "correct")

    def test_human_review_overrides_machine_and_records_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp) / "trials" / "t1"
            trial_dir.mkdir(parents=True)
            fixture = json.loads((FIXTURES / "s2-partial.json").read_text())
            (trial_dir / "submission.json").write_text(json.dumps(fixture["submission"]))
            (trial_dir / "trial.json").write_text(json.dumps({"trial_id": "t1", "case": "S2"}))
            (trial_dir / "summary.json").write_text(json.dumps({"stop_reason": "submitted"}))
            grade = record_human_review(Path(tmp), "t1", "yes", "reviewer judged the procedure adequate")
            self.assertTrue(grade["final"]["correct"])
            self.assertEqual(grade["final"]["source"], "human")
            self.assertTrue(grade["final"]["disagrees_with_machine"])
            self.assertEqual(finalize({"machine": {"correct": False, "verdict": "partial"}, "human": None})["source"], "machine")


if __name__ == "__main__":
    unittest.main()
