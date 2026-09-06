"""Command-line entry point: release one approved payment against a SQLite ledger.

The provider transport is a single selected fixture, chosen by ``--fixture`` or the
``PAYMENT_FIXTURE`` environment variable. Traces are recorded only when ``--traces``
names a directory; otherwise the same adapters run without recorders.
"""
import argparse
import os
import sys
import traceback
import uuid
from pathlib import Path

from adapters import SingleResponse, SqliteLedger, StripeTransfers
from core import Payment, pay
from tracing import LedgerRecorder, Recorder


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, required=True, help="SQLite ledger; created and funded if absent")
    parser.add_argument("--payment-id", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--cents", type=int, required=True)
    parser.add_argument("--now", type=int, required=True, help="current time as Unix seconds")
    parser.add_argument("--fixture", type=Path, default=os.environ.get("PAYMENT_FIXTURE"),
                        help="provider transport fixture (or PAYMENT_FIXTURE)")
    parser.add_argument("--traces", type=Path, default=None, help="record boundary traces here")
    parser.add_argument("--initial-cents", type=int, default=100_000,
                        help="platform funds when creating a new ledger")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.fixture:
        print("No provider transport configured: pass --fixture or set PAYMENT_FIXTURE", file=sys.stderr)
        return 2
    payment = Payment(args.payment_id, args.destination, args.cents)
    ledger = SqliteLedger(args.db)
    try:
        if not ledger.seeded():
            ledger.seed(args.initial_cents)
        selected_ledger = ledger
        transport = SingleResponse.load(args.fixture)
        if args.traces:
            global_id = str(uuid.uuid4())
            selected_ledger = LedgerRecorder(ledger, args.traces, global_id)
            transport = Recorder(transport, args.traces, global_id)
        try:
            receipt = pay(payment, selected_ledger, StripeTransfers(transport), args.now)
        except Exception as error:
            print(f"Payment {payment.payment_id} failed: {error}", file=sys.stderr)
            traceback.print_exc()
            return 1
        print(f"Payment {payment.payment_id} confirmed: {receipt}")
        return 0
    finally:
        ledger.close()


if __name__ == "__main__":
    sys.exit(main())
