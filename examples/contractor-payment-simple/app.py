"""Straightforward Python payment script; direct SQLite and fixture calls.

This is a handwritten comparison baseline, not a sample of any harness's output.
Provider traffic is offline. No interfaces, constructor injection, or type hints.
"""
import json
import sqlite3
from urllib.parse import urlencode


def initialize(path, cents=100_000):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE balances (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                available INTEGER NOT NULL CHECK (available >= 0),
                reserved INTEGER NOT NULL CHECK (reserved >= 0),
                contractor INTEGER NOT NULL CHECK (contractor >= 0)
            );
            CREATE TABLE payments (
                id TEXT PRIMARY KEY, destination TEXT NOT NULL,
                cents INTEGER NOT NULL CHECK (cents > 0),
                created_at INTEGER NOT NULL, transfer_id TEXT UNIQUE
            );
            CREATE TABLE postings (
                payment_id TEXT PRIMARY KEY REFERENCES payments(id),
                cents INTEGER NOT NULL CHECK (cents > 0)
            );
        """)
        db.execute("INSERT INTO balances VALUES (1, ?, 0, 0)", (cents,))


def pay(path, fixture_path, payment_id, destination, cents, now):
    if type(cents) is not int or cents <= 0 or not payment_id or not destination:
        raise ValueError("Use a payment identity, destination, and positive integer USD cents")
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
            if row:
                if (row["destination"], row["cents"]) != (destination, cents):
                    raise ValueError("An existing payment cannot change amount or destination")
                if row["transfer_id"]:
                    return row["transfer_id"]
                created_at = row["created_at"]
            else:
                count = db.execute("""UPDATE balances
                    SET available = available - ?, reserved = reserved + ?
                    WHERE id = 1 AND available >= ?""", (cents, cents, cents)).rowcount
                if count != 1:
                    raise ValueError("Insufficient unreserved funds")
                created_at = now
                db.execute("INSERT INTO payments VALUES (?, ?, ?, ?, NULL)",
                           (payment_id, destination, cents, now))

        if not 0 <= now - created_at < 23 * 3600:
            raise RuntimeError("Payment is outside the automatic retry window; reconcile")
        request = {
            "method": "POST", "url": "https://api.stripe.com/v1/transfers",
            "headers": {"Content-Type": "application/x-www-form-urlencoded",
                        "Idempotency-Key": "contractor-payment:" + payment_id},
            "body": urlencode({"amount": cents, "currency": "usd",
                               "destination": destination, "transfer_group": payment_id}),
        }
        # Direct fixture I/O stands in for a direct API call, keeping this demo offline.
        with open(fixture_path) as file:
            fixture = json.load(file)
        if request != fixture["request"]:
            raise AssertionError("Request differs from the explicitly wired fixture")
        if fixture["outcome"]["kind"] == "timeout":
            raise TimeoutError("Response lost; remote transfer outcome is unknown")
        response = fixture["outcome"]["response"]
        body = response["body"]
        if response["status"] != 200 or (
            body.get("object"), body.get("amount"), body.get("currency"),
            body.get("destination"), body.get("transfer_group")) != (
                "transfer", cents, "usd", destination, payment_id):
            raise RuntimeError("Unconfirmed payment response; reconcile")
        receipt = body.get("id")
        if not isinstance(receipt, str) or not receipt.startswith("tr_"):
            raise RuntimeError("Missing transfer identity; reconcile")

        with db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT transfer_id FROM payments WHERE id = ?", (payment_id,)).fetchone()
            if row["transfer_id"]:
                if row["transfer_id"] != receipt:
                    raise RuntimeError("Conflicting provider receipts; reconcile")
                return receipt
            db.execute("INSERT INTO postings VALUES (?, ?)", (payment_id, cents))
            db.execute("""UPDATE balances SET reserved = reserved - ?,
                contractor = contractor + ? WHERE id = 1""", (cents, cents))
            db.execute("UPDATE payments SET transfer_id = ? WHERE id = ?", (receipt, payment_id))
        return receipt
    finally:
        db.close()


def main(argv=None):
    import argparse
    import os
    import sys
    import traceback
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Release one approved payment against a SQLite ledger.")
    parser.add_argument("--db", type=Path, required=True, help="SQLite ledger; created and funded if absent")
    parser.add_argument("--payment-id", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--cents", type=int, required=True)
    parser.add_argument("--now", type=int, required=True, help="current time as Unix seconds")
    parser.add_argument("--fixture", type=Path, default=os.environ.get("PAYMENT_FIXTURE"),
                        help="provider transport fixture (or PAYMENT_FIXTURE)")
    parser.add_argument("--initial-cents", type=int, default=100_000,
                        help="platform funds when creating a new ledger")
    args = parser.parse_args(argv)
    if not args.fixture:
        print("No provider transport configured: pass --fixture or set PAYMENT_FIXTURE", file=sys.stderr)
        return 2
    if not args.db.exists():
        initialize(args.db, args.initial_cents)
    try:
        receipt = pay(args.db, args.fixture, args.payment_id, args.destination, args.cents, args.now)
    except Exception as error:
        print(f"Payment {args.payment_id} failed: {error}", file=sys.stderr)
        traceback.print_exc()
        return 1
    print(f"Payment {args.payment_id} confirmed: {receipt}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
