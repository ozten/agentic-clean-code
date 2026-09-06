"""Run-level spend controls: cap, reservations, cancellation (design R58, accounting contract).

`budget.json` under the run directory is the single source of truth. Before each inference
POST the runner reserves a worst-case amount; if committed + reserved + new reserve would
exceed `batch_usd_cap`, admission fails and the runner stops with `budget_cap`, which pauses
the batch. After valid usage arrives the reserve is replaced with the observed rate-card cost.
An attempt without terminal usage keeps its reserve as *unresolved* until an operator
reconciles it. A `CANCEL` file in the run directory stops any further admission.

Scheduling is serial (concurrency 1), so this file needs no cross-process locking; that
assumption is recorded in the run manifest.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .ledger import now_iso

PURPOSES = ("solving", "preflight", "qualification", "grading", "replacement")


class BudgetExceeded(Exception):
    pass


class RunCancelled(Exception):
    pass


@dataclass
class BudgetState:
    cap_usd: Decimal
    committed_usd: Decimal = Decimal("0")
    reserved_usd: Decimal = Decimal("0")
    unresolved_usd: Decimal = Decimal("0")
    by_purpose: dict = field(default_factory=lambda: {p: "0" for p in PURPOSES})
    unresolved: list[dict] = field(default_factory=list)
    admissions: int = 0
    refusals: int = 0
    history: list[dict] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"cap_usd": str(self.cap_usd), "committed_usd": str(self.committed_usd),
                "reserved_usd": str(self.reserved_usd), "unresolved_usd": str(self.unresolved_usd),
                "by_purpose": self.by_purpose, "unresolved": self.unresolved, "admissions": self.admissions,
                "refusals": self.refusals, "history": self.history[-200:]}

    @classmethod
    def from_json(cls, data: dict) -> "BudgetState":
        return cls(Decimal(data["cap_usd"]), Decimal(data["committed_usd"]), Decimal(data["reserved_usd"]),
                   Decimal(data.get("unresolved_usd", "0")), data.get("by_purpose", {p: "0" for p in PURPOSES}),
                   data.get("unresolved", []), data.get("admissions", 0), data.get("refusals", 0),
                   data.get("history", []))


class BudgetGate:
    def __init__(self, run_dir: Path, cap_usd: Decimal | None = None):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "budget.json"
        self.cancel_path = self.run_dir / "CANCEL"
        if self.path.exists():
            self.state = BudgetState.from_json(json.loads(self.path.read_text()))
            if cap_usd is not None and cap_usd != self.state.cap_usd:
                raise ValueError("batch_usd_cap differs from the frozen budget file; create a new run instead")
        else:
            if cap_usd is None or cap_usd <= 0:
                raise ValueError("batch_usd_cap must be an explicit positive value")
            self.state = BudgetState(cap_usd)
            self._save()

    def _save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state.to_json(), indent=1))
        temporary.replace(self.path)

    @property
    def cancelled(self) -> bool:
        return self.cancel_path.exists()

    def cancel(self, reason: str) -> None:
        self.cancel_path.write_text(json.dumps({"reason": reason, "at": now_iso()}) + "\n")

    @property
    def exposure(self) -> Decimal:
        return self.state.committed_usd + self.state.reserved_usd + self.state.unresolved_usd

    @property
    def headroom(self) -> Decimal:
        return self.state.cap_usd - self.exposure

    def admit(self, reserve: Decimal, purpose: str, attempt_id: str) -> None:
        """Reserve worst-case cost or raise. Cancellation is checked first."""
        if self.cancelled:
            raise RunCancelled(self.cancel_path.read_text().strip())
        if reserve < 0:
            raise ValueError("reserve must be nonnegative")
        if self.exposure + reserve > self.state.cap_usd:
            self.state.refusals += 1
            self.state.history.append({"at": now_iso(), "event": "refused", "attempt_id": attempt_id,
                                       "reserve": str(reserve), "exposure": str(self.exposure)})
            self._save()
            raise BudgetExceeded(f"reserve {reserve} would exceed cap {self.state.cap_usd} "
                                 f"(exposure {self.exposure})")
        self.state.reserved_usd += reserve
        self.state.admissions += 1
        self.state.history.append({"at": now_iso(), "event": "admitted", "attempt_id": attempt_id,
                                   "purpose": purpose, "reserve": str(reserve)})
        self._save()

    def settle(self, reserve: Decimal, actual: Decimal, purpose: str, attempt_id: str) -> None:
        self.state.reserved_usd -= reserve
        self.state.committed_usd += actual
        self.state.by_purpose[purpose] = str(Decimal(self.state.by_purpose.get(purpose, "0")) + actual)
        self.state.history.append({"at": now_iso(), "event": "settled", "attempt_id": attempt_id,
                                   "purpose": purpose, "actual": str(actual)})
        self._save()

    def hold_unresolved(self, reserve: Decimal, purpose: str, attempt_id: str, reason: str) -> None:
        """Keep a reserve outstanding when no terminal usage exists (timeout/ambiguous)."""
        self.state.reserved_usd -= reserve
        self.state.unresolved_usd += reserve
        self.state.unresolved.append({"attempt_id": attempt_id, "purpose": purpose, "reserve": str(reserve),
                                      "reason": reason, "at": now_iso()})
        self._save()

    def release(self, reserve: Decimal, purpose: str, attempt_id: str, reason: str) -> None:
        """Release a reserve when the server definitively reported an error with no usage.

        Only used for HTTP error statuses that carry no usage object (nothing generated).
        Timeouts never release; they hold."""
        self.state.reserved_usd -= reserve
        self.state.history.append({"at": now_iso(), "event": "released", "attempt_id": attempt_id,
                                   "purpose": purpose, "reserve": str(reserve), "reason": reason})
        self._save()

    def summary(self) -> dict:
        data = self.state.to_json()
        data.pop("history", None)
        data["exposure_usd"] = str(self.exposure)
        data["headroom_usd"] = str(self.headroom)
        data["cancelled"] = self.cancelled
        return data
