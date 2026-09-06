"""Frozen incident cases S1-S3 (design R13-R15). Evaluator-only; never copied into workspaces.

A case names the fixture the hidden environment wires and the fault it injects into the
application's SQLite ledger *outside* the agent-readable source (R22, R30). The trigger
text lives only in the vault database; sanitized exports drop it (R21).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

PAYMENT = {"payment_id": "milestone-42", "destination": "acct_demo_contractor", "cents": 50_000}
INCIDENT_NOW = 1_788_706_800  # 2026-09-05T19:40:00Z, fixed for every arm and case
INITIAL_CENTS = 100_000
DISK_FULL_MESSAGE = "database or disk is full"


@dataclass(frozen=True)
class Fault:
    kind: str                # "sqlite_trigger" | "none"
    sql: str = ""


@dataclass(frozen=True)
class Case:
    id: str
    slug: str
    version: int
    fixture: str                        # file name inside app/fixtures
    fault: Fault
    expected_error: str | None
    expected_exit: int
    expected_state: dict
    external_outcome: str               # no_request | transfer_returned | unknown
    provider_calls: int
    evaluator_summary: str
    smoke_test: bool = False
    rubric: dict = field(default_factory=dict)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


_NO_POSTING = {"available": 50_000, "reserved": 50_000, "contractor": 0, "postings": 0, "transfer_id": None,
               "payment_rows": 1}
_UNTOUCHED = {"available": 100_000, "reserved": 0, "contractor": 0, "postings": 0, "transfer_id": None,
              "payment_rows": 0}
HAPPY_STATE = {"available": 50_000, "reserved": 0, "contractor": 50_000, "postings": 1,
               "transfer_id": "tr_demo_500", "payment_rows": 1}

CASES: dict[str, Case] = {
    "S1": Case(
        id="S1", slug="preparation-failure", version=1, fixture="success.json",
        fault=Fault("sqlite_trigger",
                    "CREATE TRIGGER hidden_preparation_fault BEFORE INSERT ON payments BEGIN "
                    f"SELECT RAISE(ABORT, '{DISK_FULL_MESSAGE}'); END;"),
        expected_error=DISK_FULL_MESSAGE, expected_exit=1, expected_state=_UNTOUCHED,
        external_outcome="no_request", provider_calls=0,
        evaluator_summary="Durable preparation (payment row + reservation) fails inside its transaction "
                          "before any provider request; nothing committed; the success fixture was "
                          "never consumed.",
        rubric={"failed_boundary": "local durable preparation (ledger prepare / initial transaction)",
                "external_outcome": "no provider request was made",
                "local_state": "no payment row, no reservation, no posting; funds untouched (100000 available)"},
    ),
    "S2": Case(
        id="S2", slug="confirmation-failure", version=1, fixture="success.json",
        fault=Fault("sqlite_trigger",
                    "CREATE TRIGGER hidden_confirmation_fault BEFORE UPDATE OF transfer_id ON payments BEGIN "
                    f"SELECT RAISE(ABORT, '{DISK_FULL_MESSAGE}'); END;"),
        expected_error=DISK_FULL_MESSAGE, expected_exit=1, expected_state=_NO_POSTING,
        external_outcome="transfer_returned", provider_calls=1, smoke_test=True,
        evaluator_summary="Provider returned transfer tr_demo_500; the local confirmation transaction "
                          "failed and rolled back; reservation retained; no posting; no receipt saved.",
        rubric={"failed_boundary": "local confirmation write (ledger confirm transaction) after the provider response",
                "external_outcome": "a transfer response with id tr_demo_500 was received; settlement unproven",
                "local_state": "payment row present, 50000 reserved, no posting, transfer_id NULL"},
    ),
    "S3": Case(
        id="S3", slug="response-lost", version=1, fixture="timeout.json",
        fault=Fault("none"),
        expected_error="Response lost; remote transfer outcome is unknown", expected_exit=1,
        expected_state=_NO_POSTING, external_outcome="unknown", provider_calls=1,
        evaluator_summary="Submission timed out with no response; remote outcome unknown; reservation "
                          "and retry identity retained.",
        rubric={"failed_boundary": "provider transport (request sent, response lost / timeout)",
                "external_outcome": "unknown: the transfer may or may not exist at the provider",
                "local_state": "payment row present, 50000 reserved, no posting, transfer_id NULL"},
    ),
}

ARM_IDS = ("simple", "clean", "clean-no-traces")


def case_manifest() -> dict:
    return {case.id: {"slug": case.slug, "version": case.version, "digest": case.digest()}
            for case in CASES.values()}
