import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters import NoCalls, SingleResponse, SqliteLedger, StripeTransfers
from faults import DiskFullOnConfirmation
from core import NeedsReconciliation, Payment, pay
from tracing import LedgerRecorder, Recorder, fixture_from_trace

FIXTURES = Path(__file__).parent / "fixtures"
PAYMENT = Payment("milestone-42", "acct_demo_contractor", 50_000)


class PaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.db"
        self.ledger = SqliteLedger(self.path)
        self.ledger.seed()
        self.addCleanup(lambda: self.ledger.close())
        # Any accidental network connection fails the test, even without API keys.
        self.network = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def restart(self):
        self.ledger.close()
        self.ledger = SqliteLedger(self.path)

    def response(self, name="success.json"):
        return SingleResponse.load(FIXTURES / name)

    def test_timeout_disk_full_recovery_and_duplicate_submission(self):
        timeout = self.response("timeout.json")
        with self.assertRaises(TimeoutError):
            pay(PAYMENT, self.ledger, StripeTransfers(timeout), 1_000)
        timeout.assert_consumed()
        self.assertEqual(self.ledger.snapshot(),
                         {"available": 50_000, "reserved": 50_000, "contractor": 0})
        self.restart()
        success = self.response()
        with self.assertRaises(OSError) as failure:
            pay(PAYMENT, DiskFullOnConfirmation(self.ledger), StripeTransfers(success), 1_001)
        self.assertEqual(failure.exception.errno, errno.ENOSPC)
        success.assert_consumed()
        self.assertEqual(self.ledger.posting_count(), 0)
        self.restart()
        recovery = self.response()
        self.assertEqual(pay(PAYMENT, self.ledger, StripeTransfers(recovery), 1_002), "tr_demo_500")
        recovery.assert_consumed()
        self.assertEqual(timeout.calls, success.calls)
        self.assertEqual(success.calls, recovery.calls)
        pay(PAYMENT, self.ledger, StripeTransfers(NoCalls()), 1_003)
        self.assertEqual(self.ledger.posting_count(), 1)
        self.assertEqual(self.ledger.snapshot(),
                         {"available": 50_000, "reserved": 0, "contractor": 50_000})

    def test_intent_write_failure_prevents_remote_call(self):
        with patch.object(self.ledger, "prepare", side_effect=OSError(errno.ENOSPC, "disk full")):
            with self.assertRaises(OSError):
                pay(PAYMENT, self.ledger, StripeTransfers(NoCalls()), 1_000)
        self.assertEqual(self.ledger.snapshot()["available"], 100_000)

    def test_changed_amount_or_destination_rejected_before_remote_call(self):
        self.ledger.prepare(PAYMENT, 1_000)
        for changed in [Payment("milestone-42", PAYMENT.destination, 60_000),
                        Payment("milestone-42", "acct_someone_else", 50_000)]:
            with self.subTest(payment=changed), self.assertRaises(ValueError):
                pay(changed, self.ledger, StripeTransfers(NoCalls()), 1_001)

    def test_reserved_money_cannot_be_spent_again(self):
        self.ledger.prepare(PAYMENT, 1_000)
        with self.assertRaises(ValueError):
            pay(Payment("milestone-43", PAYMENT.destination, 60_000),
                self.ledger, StripeTransfers(NoCalls()), 1_001)
        self.assertEqual(sum(self.ledger.snapshot().values()), 100_000)

    def test_old_unknown_payment_requires_reconciliation(self):
        self.ledger.prepare(PAYMENT, 1_000)
        with self.assertRaises(NeedsReconciliation):
            pay(PAYMENT, self.ledger, StripeTransfers(NoCalls()), 1_000 + 23 * 3600)
        self.assertEqual(self.ledger.snapshot()["reserved"], 50_000)

    def test_wrong_response_keeps_reservation(self):
        playback = self.response()
        playback.fixture["outcome"]["response"]["body"]["amount"] = 1
        with self.assertRaises(NeedsReconciliation):
            pay(PAYMENT, self.ledger, StripeTransfers(playback), 1_000)
        self.assertEqual(self.ledger.snapshot()["reserved"], 50_000)
        self.assertEqual(self.ledger.posting_count(), 0)

    def test_single_response_rejects_extra_call(self):
        playback = self.response()
        gateway = StripeTransfers(playback)
        gateway.create(PAYMENT, "contractor-payment:milestone-42")
        with self.assertRaises(AssertionError):
            gateway.create(PAYMENT, "contractor-payment:milestone-42")

    def test_record_and_explicitly_play_back_one_response(self):
        root = Path(self.tmp.name) / "traces"
        gateway = StripeTransfers(Recorder(self.response(), root, "shared-demo-id"))
        receipt = pay(PAYMENT, self.ledger, gateway, 1_000)
        trace, = root.glob("trace-*/trace.json")
        record = json.loads(trace.read_text())
        self.assertEqual(record["global_trace_id"], "shared-demo-id")
        self.assertEqual(trace.parent.name, "trace-" + record["trace_id"])
        playback = SingleResponse(fixture_from_trace(trace))
        self.assertEqual(StripeTransfers(playback).create(
            PAYMENT, "contractor-payment:milestone-42"), receipt)
        playback.assert_consumed()

    def test_recorded_timeout_can_be_played_back(self):
        root = Path(self.tmp.name) / "traces"
        with self.assertRaises(TimeoutError):
            pay(PAYMENT, self.ledger,
                StripeTransfers(Recorder(self.response("timeout.json"), root, "shared-demo-id")), 1_000)
        trace, = root.glob("trace-*/trace.json")
        with self.assertRaises(TimeoutError):
            StripeTransfers(SingleResponse(fixture_from_trace(trace))).create(
                PAYMENT, "contractor-payment:milestone-42")

    def test_trace_sink_failure_before_request_prevents_remote_call(self):
        recorder = Recorder(NoCalls(), Path(self.tmp.name) / "traces", "shared-demo-id")
        with patch.object(recorder, "_write", side_effect=OSError(errno.ENOSPC, "trace disk full")):
            with self.assertRaises(OSError):
                pay(PAYMENT, self.ledger, StripeTransfers(recorder), 1_000)
        self.assertEqual(self.ledger.snapshot()["reserved"], 50_000)

    def test_trace_sink_failure_after_response_keeps_incomplete_evidence(self):
        playback = self.response()
        root = Path(self.tmp.name) / "traces"
        recorder = Recorder(playback, root, "shared-demo-id")
        original_write = recorder._write

        def fail_completion(directory, record):
            if record["metadata"]["complete"]:
                raise OSError(errno.ENOSPC, "trace disk full")
            original_write(directory, record)

        with patch.object(recorder, "_write", side_effect=fail_completion):
            with self.assertRaises(OSError):
                pay(PAYMENT, self.ledger, StripeTransfers(recorder), 1_000)
        playback.assert_consumed()
        self.assertEqual(self.ledger.snapshot()["reserved"], 50_000)
        self.assertEqual(self.ledger.posting_count(), 0)
        trace, = root.glob("trace-*/trace.json")
        with self.assertRaises(ValueError):
            fixture_from_trace(trace)

    def test_confirmation_transaction_rolls_back_partial_local_posting(self):
        self.ledger.prepare(PAYMENT, 1_000)
        # Fail after INSERT posting + UPDATE balances, at final receipt write.
        self.ledger.db.executescript("""CREATE TRIGGER reject_receipt
            BEFORE UPDATE OF transfer_id ON payments BEGIN
            SELECT RAISE(ABORT, 'injected persistence failure'); END;""")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            pay(PAYMENT, self.ledger, StripeTransfers(self.response()), 1_001)
        self.assertEqual(self.ledger.posting_count(), 0)
        self.assertEqual(self.ledger.snapshot(),
                         {"available": 50_000, "reserved": 50_000, "contractor": 0})

    def test_trace_failure_after_ledger_commit_does_not_resubmit_payment(self):
        recorder = LedgerRecorder(self.ledger, Path(self.tmp.name) / "traces", "shared-demo-id")
        original_write = recorder._write

        def fail_after_confirmation(directory, record):
            if record["operation"] == "confirm" and record["metadata"]["complete"]:
                raise OSError(errno.ENOSPC, "trace disk full after ledger commit")
            original_write(directory, record)

        with patch.object(recorder, "_write", side_effect=fail_after_confirmation):
            with self.assertRaises(OSError):
                pay(PAYMENT, recorder, StripeTransfers(self.response()), 1_000)
        self.restart()
        self.assertEqual(pay(PAYMENT, self.ledger, StripeTransfers(NoCalls()), 1_001), "tr_demo_500")
        self.assertEqual(self.ledger.posting_count(), 1)
        self.assertEqual(self.ledger.snapshot()["reserved"], 0)


if __name__ == "__main__":
    unittest.main()
