"""Deterministic decisions and interface-driven orchestration; no concrete I/O."""
from dataclasses import dataclass
from typing import Protocol


class NeedsReconciliation(Exception):
    """The remote outcome is uncertain; do not release reserved money."""


@dataclass(frozen=True)
class Payment:
    payment_id: str
    destination: str
    cents: int

    def __post_init__(self):
        if type(self.cents) is not int or self.cents <= 0:
            raise ValueError("Use positive integer USD cents")
        if not self.payment_id or not self.destination:
            raise ValueError("Payment identity and destination are required")


@dataclass(frozen=True)
class Intent:
    payment: Payment
    created_at: int
    transfer_id: str | None = None


class Ledger(Protocol):
    def prepare(self, payment: Payment, now: int) -> Intent: ...
    def confirm(self, payment: Payment, transfer_id: str) -> None: ...


class Transfers(Protocol):
    def create(self, payment: Payment, key: str) -> str: ...


def retry_key(intent: Intent, now: int) -> str:
    # Conservative demo policy: stop before the provider's >=24h pruning horizon.
    # This is elapsed time since durable intent creation, not a sliding retry timer.
    if not 0 <= now - intent.created_at < 23 * 60 * 60:
        raise NeedsReconciliation("Payment is outside the automatic retry window")
    return "contractor-payment:" + intent.payment.payment_id


def pay(payment: Payment, ledger: Ledger, transfers: Transfers, now: int) -> str:
    intent = ledger.prepare(payment, now)  # Commit identity + reservation BEFORE I/O.
    if intent.transfer_id:
        return intent.transfer_id
    key = retry_key(intent, now)
    receipt = transfers.create(payment, key)
    ledger.confirm(payment, receipt)  # Local posting and receipt commit atomically.
    return receipt
