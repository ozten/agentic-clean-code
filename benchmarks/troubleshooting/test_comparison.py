import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compare import FIXTURE, PAYMENT, compare, pay, run_variant, simple, snapshot
from adapters import NoCalls, SingleResponse, SqliteLedger, StripeTransfers


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)

    def test_same_happy_path_and_failure_state_with_different_evidence(self):
        with patch("builtins.print"):
            results = compare(self.root)
        for result in results:
            if result["scenario"] == "happy":
                self.assertEqual(result["state"], {"available": 50_000, "reserved": 0,
                    "contractor": 50_000, "postings": 1, "transfer_id": "tr_demo_500"})
            else:
                self.assertEqual(result["error"], "database or disk is full")
                self.assertEqual(result["state"], {"available": 50_000, "reserved": 50_000,
                    "contractor": 0, "postings": 0, "transfer_id": None})
            self.assertEqual(result["trace_count"], 3 if result["variant"] == "clean" else 0)
        for variant in ("simple", "clean", "clean-no-traces"):
            error = (self.root / "confirmation-failure" / variant / "stderr.txt").read_text()
            self.assertIn("Traceback", error)
            self.assertIn("database or disk is full", error)

    def test_traces_link_remote_success_to_failed_local_confirmation(self):
        target = self.root / "clean"
        run_variant("clean", "confirmation-failure", target)
        records = [json.loads(p.read_text()) for p in (target / "traces").glob("*/trace.json")]
        self.assertEqual(len({r["global_trace_id"] for r in records}), 1)
        by_operation = {(r["interface"], r["operation"]): r for r in records}
        self.assertEqual(by_operation["http", "send"]["outputs"]["body"]["id"], "tr_demo_500")
        confirmation = by_operation["ledger", "confirm"]
        self.assertEqual(confirmation["inputs"]["transfer_id"], "tr_demo_500")
        self.assertEqual(confirmation["metadata"]["error_code"], "IntegrityError")
        self.assertIn("database or disk is full", confirmation["metadata"]["error_message"])

    def test_both_recover_after_storage_fault_removed_and_ignore_duplicate(self):
        for variant in ("simple", "clean"):
            with self.subTest(variant=variant):
                target = self.root / variant
                run_variant(variant, "confirmation-failure", target)
                database = target / "ledger.db"
                with sqlite3.connect(database) as db:
                    db.execute("DROP TRIGGER fail_confirmation")
                if variant == "simple":
                    simple.pay(database, FIXTURE, PAYMENT.payment_id, PAYMENT.destination, PAYMENT.cents, 1_001)
                    # No fixture access allowed after a confirmed duplicate click.
                    simple.pay(database, target / "does-not-exist.json", PAYMENT.payment_id,
                               PAYMENT.destination, PAYMENT.cents, 1_002)
                else:
                    ledger = SqliteLedger(database)
                    try:
                        pay(PAYMENT, ledger, StripeTransfers(SingleResponse.load(FIXTURE)), 1_001)
                        pay(PAYMENT, ledger, StripeTransfers(NoCalls()), 1_002)
                    finally:
                        ledger.close()
                self.assertEqual(snapshot(database), {"available": 50_000, "reserved": 0,
                    "contractor": 50_000, "postings": 1, "transfer_id": "tr_demo_500"})


if __name__ == "__main__":
    unittest.main()
