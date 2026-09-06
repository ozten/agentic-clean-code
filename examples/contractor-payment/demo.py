"""Run a reproducible payment recovery story without accounts or network access."""
import argparse
import tempfile
from pathlib import Path

from adapters import NoCalls, SingleResponse, SqliteLedger, StripeTransfers
from faults import DiskFullOnConfirmation
from core import Payment, pay
from tracing import LedgerRecorder, Recorder

FIXTURES = Path(__file__).parent / "fixtures"
PAYMENT = Payment("milestone-42", "acct_demo_contractor", 50_000)
GLOBAL_ID = "0c366885-a969-46a9-a0cb-0353489d021c"


def run(trace_root):
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "ledger.db"
        ledger = SqliteLedger(database)
        ledger.seed()
        print("Release $500 to a contractor. All provider responses are synthetic fixtures.")
        stages = [("timeout.json", "lost response"), ("success.json", "disk full"),
                  ("success.json", "recovered")]
        requests = []
        for attempt, (fixture, label) in enumerate(stages, 1):
            # Each invocation gets exactly one selected response, directly wired.
            playback = SingleResponse.load(FIXTURES / fixture)
            gateway = StripeTransfers(Recorder(playback, trace_root, GLOBAL_ID))
            selected_ledger = DiskFullOnConfirmation(ledger) if attempt == 2 else ledger
            selected_ledger = LedgerRecorder(selected_ledger, trace_root, GLOBAL_ID)
            try:
                pay(PAYMENT, selected_ledger, gateway, now=1_000 + attempt)
            except (TimeoutError, OSError) as exc:
                print(f"Attempt {attempt}: {label}: {exc}")
            else:
                print(f"Attempt {attempt}: {label}")
            playback.assert_consumed()
            requests.extend(playback.calls)
            print("  Local ledger (cents):", ledger.snapshot())
            ledger.close()
            ledger = SqliteLedger(database)  # Fresh connection; durable state survives.
        pay(PAYMENT, ledger, StripeTransfers(NoCalls()), now=1_010)
        assert requests[0] == requests[1] == requests[2]
        assert ledger.snapshot() == {"available": 50_000, "reserved": 0, "contractor": 50_000}
        assert ledger.posting_count() == 1
        ledger.close()
        print("PASS: unchanged retry request, one local posting, duplicate click makes no API call.")
        print("Remote deduplication relies on Stripe's contract; this run does not test Stripe.")
        print(f"Boundary traces: {trace_root} (global trace ID: {GLOBAL_ID})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces", type=Path, default=Path("traces"))
    run(parser.parse_args().traces)
