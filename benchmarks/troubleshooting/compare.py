"""Generate matched local examples; does not run agents or measure their tokens."""
import argparse
import importlib.util
import json
import sqlite3
import sys
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "examples/contractor-payment"))
from adapters import SingleResponse, SqliteLedger, StripeTransfers
from core import Payment, pay
from tracing import LedgerRecorder, Recorder

spec = importlib.util.spec_from_file_location("simple_payment", ROOT / "examples/contractor-payment-simple/app.py")
simple = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simple)

PAYMENT = Payment("milestone-42", "acct_demo_contractor", 50_000)
FIXTURE = ROOT / "examples/contractor-payment/fixtures/success.json"


def inject_confirmation_failure(path):
    # Same persistence failure point for both variants. Does not fill a real disk.
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TRIGGER fail_confirmation
            BEFORE UPDATE OF transfer_id ON payments BEGIN
            SELECT RAISE(ABORT, 'database or disk is full'); END;""")


def snapshot(path):
    with sqlite3.connect(path) as db:
        available, reserved, contractor = db.execute(
            "SELECT available, reserved, contractor FROM balances").fetchone()
        count, = db.execute("SELECT count(*) FROM postings").fetchone()
        receipt, = db.execute("SELECT transfer_id FROM payments").fetchone()
    return {"available": available, "reserved": reserved, "contractor": contractor,
            "postings": count, "transfer_id": receipt}


def run_variant(variant, scenario, directory):
    directory.mkdir(parents=True, exist_ok=False)
    database = directory / "ledger.db"
    traces = directory / "traces"
    global_id = str(uuid.uuid4())
    if variant == "simple":
        simple.initialize(database)
        ledger = None
    else:
        ledger = SqliteLedger(database)
        ledger.seed()
    if scenario == "confirmation-failure":
        inject_confirmation_failure(database)
    result = {"variant": variant, "scenario": scenario, "error": None, "receipt": None}
    try:
        if variant == "simple":
            receipt = simple.pay(database, FIXTURE, PAYMENT.payment_id, PAYMENT.destination,
                                 PAYMENT.cents, 1_000)
        else:
            selected_ledger = ledger
            transport = SingleResponse.load(FIXTURE)
            if variant == "clean":
                selected_ledger = LedgerRecorder(ledger, traces, global_id)
                transport = Recorder(transport, traces, global_id)
            receipt = pay(PAYMENT, selected_ledger, StripeTransfers(transport), 1_000)
        result["receipt"] = receipt
        output = f"Payment milestone-42 confirmed: {receipt}\n"
        (directory / "stdout.txt").write_text(output)
        (directory / "stderr.txt").write_text("")
    except sqlite3.IntegrityError as error:
        result["error"] = str(error)
        output = f"Payment milestone-42 failed: {error}\n"
        (directory / "stdout.txt").write_text("")
        # Preserve full ordinary traceback for BOTH versions; do not cripple the baseline.
        (directory / "stderr.txt").write_text(output + traceback.format_exc())
    finally:
        if ledger:
            ledger.close()
    result["state"] = snapshot(database)
    result["trace_count"] = len(list(traces.glob("trace-*/trace.json")))
    (directory / "evaluator-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def compare(output):
    results = []
    for scenario in ("happy", "confirmation-failure"):
        for variant in ("simple", "clean", "clean-no-traces"):
            result = run_variant(variant, scenario, output / scenario / variant)
            results.append(result)
            print(f"{scenario:22} {variant:16} "
                  f"{result['error'] or result['receipt']} | {result['trace_count']} traces")
        states = [r["state"] for r in results if r["scenario"] == scenario]
        assert states[0] == states[1] == states[2], "Comparison state differs"
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmark-artifacts" / str(uuid.uuid4()))
    args = parser.parse_args()
    compare(args.output)
    print(f"Evidence written to {args.output}")
    print("No coding-agent runs performed; token measurements remain uncollected.")
