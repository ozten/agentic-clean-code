"""SQLite ledger, Stripe request mapping, and deliberately small playback adapters."""
import copy
import json
import sqlite3
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from core import Intent, NeedsReconciliation, Payment


class SqliteLedger:
    """One platform pool and one contractor; amounts are local bookkeeping."""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS balances (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                available INTEGER NOT NULL CHECK (available >= 0),
                reserved INTEGER NOT NULL CHECK (reserved >= 0),
                contractor INTEGER NOT NULL CHECK (contractor >= 0)
            );
            CREATE TABLE IF NOT EXISTS payments (
                id TEXT PRIMARY KEY, destination TEXT NOT NULL,
                cents INTEGER NOT NULL CHECK (cents > 0),
                created_at INTEGER NOT NULL, transfer_id TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS postings (
                payment_id TEXT PRIMARY KEY REFERENCES payments(id),
                cents INTEGER NOT NULL CHECK (cents > 0)
            );
        """)

    def seeded(self):
        return self.db.execute("SELECT COUNT(*) FROM balances").fetchone()[0] > 0

    def seed(self, cents=100_000):
        with self.db:
            self.db.execute("INSERT INTO balances VALUES (1, ?, 0, 0)", (cents,))

    def prepare(self, payment, now):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM payments WHERE id = ?",
                                  (payment.payment_id,)).fetchone()
            if row:
                if (row["destination"], row["cents"]) != (payment.destination, payment.cents):
                    raise ValueError("An existing payment cannot change amount or destination")
                return Intent(payment, row["created_at"], row["transfer_id"])
            count = self.db.execute("""UPDATE balances
                SET available = available - ?, reserved = reserved + ?
                WHERE id = 1 AND available >= ?""",
                (payment.cents, payment.cents, payment.cents)).rowcount
            if count != 1:
                raise ValueError("Insufficient unreserved funds")
            self.db.execute("INSERT INTO payments VALUES (?, ?, ?, ?, NULL)",
                            (payment.payment_id, payment.destination, payment.cents, now))
        return Intent(payment, now)

    def confirm(self, payment, transfer_id):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM payments WHERE id = ?",
                                  (payment.payment_id,)).fetchone()
            if row is None or (row["destination"], row["cents"]) != (payment.destination, payment.cents):
                raise ValueError("Confirmation does not match durable intent")
            if row["transfer_id"]:
                if row["transfer_id"] != transfer_id:
                    raise NeedsReconciliation("Conflicting provider receipts")
                return
            self.db.execute("INSERT INTO postings VALUES (?, ?)",
                            (payment.payment_id, payment.cents))
            self.db.execute("""UPDATE balances SET reserved = reserved - ?,
                contractor = contractor + ? WHERE id = 1""", (payment.cents, payment.cents))
            self.db.execute("UPDATE payments SET transfer_id = ? WHERE id = ?",
                            (transfer_id, payment.payment_id))

    def snapshot(self):
        row = self.db.execute("SELECT * FROM balances WHERE id = 1").fetchone()
        return {name: row[name] for name in ("available", "reserved", "contractor")}

    def posting_count(self):
        return self.db.execute("SELECT COUNT(*) FROM postings").fetchone()[0]

    def close(self):
        self.db.close()


class HttpTransport(Protocol):
    def send(self, request: dict) -> dict: ...


class StripeTransfers:
    """Real request encoding/response validation; transport is supplied externally.

    No authentication or live HTTP implementation is shipped in this offline demo.
    """

    def __init__(self, transport: HttpTransport):
        self.transport = transport

    def create(self, payment, key):
        request = {
            "method": "POST",
            "url": "https://api.stripe.com/v1/transfers",
            "headers": {"Content-Type": "application/x-www-form-urlencoded",
                        "Idempotency-Key": key},
            "body": urlencode({"amount": payment.cents, "currency": "usd",
                               "destination": payment.destination,
                               "transfer_group": payment.payment_id}),
        }
        response = self.transport.send(request)
        if response["status"] != 200:
            raise NeedsReconciliation("Non-success response: retain reservation for review")
        body = response["body"]
        if (body.get("object"), body.get("amount"), body.get("currency"),
            body.get("destination"), body.get("transfer_group")) != (
                "transfer", payment.cents, "usd", payment.destination, payment.payment_id):
            raise NeedsReconciliation("Response does not match the payment")
        if not isinstance(body.get("id"), str) or not body["id"].startswith("tr_"):
            raise NeedsReconciliation("Missing transfer identity")
        return body["id"]


class SingleResponse:
    """One exact request -> one outcome. Fresh instance per test invocation."""

    def __init__(self, fixture):
        self.fixture = copy.deepcopy(fixture)
        self.calls = []

    @classmethod
    def load(cls, filename):
        return cls(json.loads(Path(filename).read_text()))

    def send(self, request):
        if self.calls:
            raise AssertionError("Unexpected second request to single-response playback")
        if request != self.fixture["request"]:
            raise AssertionError("Request differs from the explicitly wired fixture")
        self.calls.append(copy.deepcopy(request))
        if self.fixture["outcome"]["kind"] == "timeout":
            raise TimeoutError("Response lost; remote transfer outcome is unknown")
        return copy.deepcopy(self.fixture["outcome"]["response"])

    def assert_consumed(self):
        if len(self.calls) != 1:
            raise AssertionError("Expected one boundary call")


class NoCalls:
    def send(self, request):
        raise AssertionError("This scenario must not contact the payment interface")
