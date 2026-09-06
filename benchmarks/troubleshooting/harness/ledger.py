"""Append-only request ledger and tool-event log for one trial (design OA06, R37, R42, V11).

`requests.jsonl` receives one row when an attempt is opened (status `sent`, written *before*
the POST) and one terminal row when it closes. Readers reduce rows by `attempt_id`, last row
wins. An attempt with only a `sent` row after a crash has unknown telemetry; it is never
resent automatically and never counted as zero.

Immutable request/response JSON files live under `responses/` and are written before any tool
call from that response executes.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .env import redact


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class RequestLedger:
    def __init__(self, trial_dir: Path, trial_id: str, secrets: list[str | None] | None = None):
        self.trial_dir = Path(trial_dir)
        self.trial_id = trial_id
        self.path = self.trial_dir / "requests.jsonl"
        self.responses_dir = self.trial_dir / "responses"
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.secrets = secrets or []
        self._sequence = self._last_sequence()

    def _last_sequence(self) -> int:
        return max((row.get("sequence", 0) for row in self.rows_raw()), default=0)

    def rows_raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def attempts(self) -> dict[str, dict]:
        """Reduce rows to the latest state per attempt_id, in first-seen order."""
        reduced: dict[str, dict] = {}
        for row in self.rows_raw():
            key = row["attempt_id"]
            if key in reduced:
                reduced[key] = {**reduced[key], **row}
            else:
                reduced[key] = dict(row)
        return reduced

    def _append(self, row: dict) -> None:
        text = redact(json.dumps(row, default=str), self.secrets)
        with self.path.open("a") as handle:
            handle.write(text + "\n")
            handle.flush()

    def open_attempt(self, purpose: str, payload: dict, model: str, client_request_id: str | None = None,
                     reserve_usd=None, pricing_profile_id: str | None = None, extra: dict | None = None) -> dict:
        self._sequence += 1
        attempt_id = str(uuid.uuid4())
        client_request_id = client_request_id or str(uuid.uuid4())
        request_path = self.responses_dir / f"{self._sequence:04d}-{purpose}-request.json"
        request_path.write_text(redact(json.dumps(payload, indent=1, default=str), self.secrets))
        row = {"trial_id": self.trial_id, "attempt_id": attempt_id, "sequence": self._sequence, "purpose": purpose,
               "status": "sent", "opened_at": now_iso(), "opened_monotonic": time.monotonic(),
               "client_request_id": client_request_id, "requested_model": model,
               "payload_hash": payload_hash(payload), "payload_path": str(request_path.relative_to(self.trial_dir)),
               "reserve_usd": None if reserve_usd is None else str(reserve_usd),
               "pricing_profile_id": pricing_profile_id, "telemetry": "pending", **(extra or {})}
        self._append(row)
        return row

    def close_attempt(self, row: dict, *, status: str, response_json: dict | None = None, http_status=None,
                      server_request_id=None, response_id=None, returned_model=None, returned_tier=None,
                      raw_usage=None, derived=None, cost_usd=None, telemetry="complete", failure_reason=None,
                      incomplete_reason=None, elapsed_seconds=None, extra: dict | None = None) -> dict:
        response_path = None
        if response_json is not None:
            path = self.responses_dir / f"{row['sequence']:04d}-{row['purpose']}-response.json"
            path.write_text(redact(json.dumps(response_json, indent=1, default=str), self.secrets))
            response_path = str(path.relative_to(self.trial_dir))
        closing = {"trial_id": self.trial_id, "attempt_id": row["attempt_id"], "sequence": row["sequence"],
                   "purpose": row["purpose"], "status": status, "closed_at": now_iso(), "http_status": http_status,
                   "server_request_id": server_request_id, "response_id": response_id,
                   "returned_model": returned_model, "returned_service_tier": returned_tier,
                   "response_path": response_path, "raw_usage": raw_usage, "derived": derived,
                   "cost_usd": None if cost_usd is None else str(cost_usd), "telemetry": telemetry,
                   "failure_reason": failure_reason, "incomplete_reason": incomplete_reason,
                   "elapsed_seconds": elapsed_seconds, **(extra or {})}
        self._append(closing)
        return {**row, **closing}


class ToolEventLog:
    def __init__(self, trial_dir: Path, secrets: list[str | None] | None = None):
        self.trial_dir = Path(trial_dir)
        self.path = self.trial_dir / "tool-events.jsonl"
        self.outputs_dir = self.trial_dir / "tool-outputs"
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.secrets = secrets or []
        self.count = len(self.events())

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def record(self, event: dict, raw_output: str | None = None) -> dict:
        self.count += 1
        event = {"sequence": self.count, "recorded_at": now_iso(), **event}
        if raw_output is not None:
            path = self.outputs_dir / f"{self.count:04d}-{event.get('tool', 'tool')}.txt"
            path.write_text(redact(raw_output, self.secrets))
            event["raw_output_path"] = str(path.relative_to(self.trial_dir))
            event["raw_output_bytes"] = len(raw_output.encode())
        with self.path.open("a") as handle:
            handle.write(redact(json.dumps(event, default=str), self.secrets) + "\n")
            handle.flush()
        return event
