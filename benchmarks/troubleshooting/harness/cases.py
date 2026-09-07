"""Frozen incident cases (design R13-R15, plus v2 cases S4-S5). Evaluator-only; never copied into workspaces.

A case names the provider outcome the hidden environment wires, the fault it injects into the
application's SQLite ledger *outside* agent-readable source (R22, R30), and an optional
precursor run that leaves state behind before the operator's command. Trigger text lives only
in the vault database; sanitized exports drop it (R21).

Version 2 (2026-09-06): expected state is expressed as the balance *delta* of the incident run
plus the incident payment's row, so a pre-incident payment history can exist; error text is
matched per arm because each application's ordinary wording is part of its diagnostics (R02).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

PAYMENT = {"payment_id": "milestone-42", "destination": "acct_demo_contractor", "cents": 50_000}
INCIDENT_NOW = 1_788_706_800  # 2026-09-05T19:40:00Z, fixed for every arm and case
INITIAL_CENTS = 100_000        # platform funds available to the incident payment after any history
DISK_FULL_MESSAGE = "database or disk is full"
TIMEOUT_MESSAGE = "Response lost; remote transfer outcome is unknown"
DAY = 24 * 3600


@dataclass(frozen=True)
class Fault:
    kind: str                # "sqlite_trigger" | "none"
    sql: str = ""


@dataclass(frozen=True)
class Precursor:
    """An earlier run of the same payment that the hidden environment performs before the incident."""
    outcome: str             # "timeout" | "success"
    age_seconds: int         # how long before INCIDENT_NOW it ran


@dataclass(frozen=True)
class Case:
    id: str
    slug: str
    version: int
    outcome: str                        # provider outcome wired for the incident run: success | timeout | mismatch
    fault: Fault
    expected_error: dict                # arm id -> substring expected in stderr
    expected_exit: int
    expected_delta: dict                # balance change caused by the incident run
    expected_incident: dict             # {"row": bool, "transfer_id": str|None, "posting": bool}
    expected_traces: int                # trace records the clean arm writes during the incident run
    external_outcome: str               # no_request | transfer_returned | unknown | mismatched_response
    provider_calls: int
    evaluator_summary: str
    precursor: Precursor | None = None
    smoke_test: bool = False
    rubric: dict = field(default_factory=dict)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]

    def error_for(self, arm_id: str) -> str | None:
        return self.expected_error.get(arm_id, self.expected_error.get("*"))


_RESERVED = {"available": -50_000, "reserved": 50_000, "contractor": 0}
_UNCHANGED = {"available": 0, "reserved": 0, "contractor": 0}
_NO_POSTING = {"row": True, "transfer_id": None, "posting": False}

HAPPY_DELTA = {"available": -50_000, "reserved": 0, "contractor": 50_000}
HAPPY_INCIDENT = {"row": True, "transfer_id": "tr_demo_500", "posting": True}

CASES: dict[str, Case] = {
    "S1": Case(
        id="S1", slug="preparation-failure", version=2, outcome="success",
        fault=Fault("sqlite_trigger",
                    "CREATE TRIGGER hidden_preparation_fault BEFORE INSERT ON payments BEGIN "
                    f"SELECT RAISE(ABORT, '{DISK_FULL_MESSAGE}'); END;"),
        expected_error={"*": DISK_FULL_MESSAGE}, expected_exit=1, expected_delta=_UNCHANGED,
        expected_incident={"row": False, "transfer_id": None, "posting": False}, expected_traces=1,
        external_outcome="no_request", provider_calls=0,
        evaluator_summary="Durable preparation (payment row + reservation) fails inside its transaction "
                          "before any provider request; nothing committed; the success response was never consumed.",
        rubric={"failed_boundary": "local durable preparation (ledger prepare / initial transaction)",
                "external_outcome": "no provider request was made",
                "local_state": "no payment row, no reservation, no posting; funds untouched"},
    ),
    "S2": Case(
        id="S2", slug="confirmation-failure", version=2, outcome="success",
        fault=Fault("sqlite_trigger",
                    "CREATE TRIGGER hidden_confirmation_fault BEFORE UPDATE OF transfer_id ON payments BEGIN "
                    f"SELECT RAISE(ABORT, '{DISK_FULL_MESSAGE}'); END;"),
        expected_error={"*": DISK_FULL_MESSAGE}, expected_exit=1, expected_delta=_RESERVED,
        expected_incident=_NO_POSTING, expected_traces=3, external_outcome="transfer_returned", provider_calls=1,
        smoke_test=True,
        evaluator_summary="Provider returned transfer tr_demo_500; the local confirmation transaction "
                          "failed and rolled back; reservation retained; no posting; no receipt saved.",
        rubric={"failed_boundary": "local confirmation write (ledger confirm transaction) after the provider response",
                "external_outcome": "a transfer response with id tr_demo_500 was received; settlement unproven",
                "local_state": "payment row present, 50000 reserved, no posting, transfer_id NULL"},
    ),
    "S3": Case(
        id="S3", slug="response-lost", version=2, outcome="timeout", fault=Fault("none"),
        expected_error={"*": TIMEOUT_MESSAGE}, expected_exit=1, expected_delta=_RESERVED,
        expected_incident=_NO_POSTING, expected_traces=2, external_outcome="unknown", provider_calls=1,
        evaluator_summary="Submission timed out with no response; remote outcome unknown; reservation "
                          "and retry identity retained.",
        rubric={"failed_boundary": "provider transport (request sent, response lost / timeout)",
                "external_outcome": "unknown: the transfer may or may not exist at the provider",
                "local_state": "payment row present, 50000 reserved, no posting, transfer_id NULL"},
    ),
    "S4": Case(
        id="S4", slug="response-mismatch", version=2, outcome="mismatch", fault=Fault("none"),
        expected_error={"simple": "Unconfirmed payment response; reconcile",
                        "clean": "Response does not match the payment",
                        "clean-no-traces": "Response does not match the payment"},
        expected_exit=1, expected_delta=_RESERVED, expected_incident=_NO_POSTING, expected_traces=2,
        external_outcome="mismatched_response", provider_calls=1,
        evaluator_summary="Provider returned a 200 transfer response (id tr_demo_500) whose amount (49500) does "
                          "not match the requested 50000; the application rejected it before confirmation. A "
                          "transfer may exist at the provider with a different amount; reservation retained; no posting. "
                          "Only the traces arm can see the response body; other arms can only establish that "
                          "validation rejected a received response.",
        rubric={"failed_boundary": "provider response validation: a response was received and rejected as not matching the payment",
                "external_outcome": "a transfer response was returned but did not match (amount); provider state must be reconciled, not assumed failed",
                "local_state": "payment row present, 50000 reserved, no posting, transfer_id NULL"},
    ),
    "S5": Case(
        id="S5", slug="stale-retry", version=2, outcome="success", fault=Fault("none"),
        expected_error={"simple": "Payment is outside the automatic retry window; reconcile",
                        "clean": "Payment is outside the automatic retry window",
                        "clean-no-traces": "Payment is outside the automatic retry window"},
        expected_exit=1, expected_delta=_UNCHANGED, expected_incident=_NO_POSTING, expected_traces=1,
        external_outcome="unknown", provider_calls=0, precursor=Precursor("timeout", DAY),
        evaluator_summary="An earlier attempt 24 hours before the incident timed out and left the intent and "
                          "reservation behind. The operator's retry hit the 23-hour automatic-retry rule before any "
                          "provider request in this run. The earlier attempt's remote outcome is unknown.",
        rubric={"failed_boundary": "local retry-window policy (intent older than 23h) before any provider request in this run",
                "external_outcome": "no request in this run; the earlier attempt's outcome is unknown (its response was lost)",
                "local_state": "pre-existing payment row from the earlier attempt, 50000 reserved since then, no posting, transfer_id NULL"},
    ),
}

ARM_IDS = ("simple", "clean", "clean-no-traces")


def case_manifest() -> dict:
    return {case.id: {"slug": case.slug, "version": case.version, "digest": case.digest()}
            for case in CASES.values()}
