"""Key validation preflight: the cheapest authenticated OpenAI request, no completions.

Outcomes (also the process exit codes of ``harness preflight``):

  0  ok        key accepted by ``GET /v1/models``
  2  missing   OPEN_AI_API_KEY absent or empty in .env
  3  auth      401/403 or another authentication-shaped error -> escalate for a new key
  4  network   connection/timeout/5xx/429 persisted after bounded retries -> escalate,
              do not assume the key is bad
  5  other     unexpected API error

Retries with backoff apply only here; measured trials never retry (design OA05).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .env import Settings, load_settings, redact

REQUEST_DESCRIPTION = "GET /v1/models (list models; no completion, no tokens billed)"
DEFAULT_BACKOFF = (1.0, 2.0, 4.0)
EXIT_CODES = {"ok": 0, "missing": 2, "auth": 3, "network": 4, "other": 5}


@dataclass
class PreflightResult:
    kind: str                      # ok | missing | auth | network | other
    request: str = REQUEST_DESCRIPTION
    detail: str = ""
    attempts: int = 0
    status_code: int | None = None
    request_id: str | None = None
    model_count: int | None = None
    project_id: str | None = None
    key: str = "absent"            # fingerprint only, never the key
    checked_at: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind == "ok"

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.kind]

    def escalation_message(self) -> str:
        if self.kind == "ok":
            return "OpenAI key accepted."
        if self.kind == "missing":
            return ("OPEN_AI_API_KEY is missing or empty in .env. No paid call was attempted. "
                    "Supply a key; it will be written to .env only.")
        if self.kind == "auth":
            return (f"OpenAI rejected the key: {self.request} returned "
                    f"{self.status_code or 'an authentication error'} ({self.detail}). "
                    "Supply a new key; nothing else will be retried or substituted.")
        if self.kind == "network":
            return (f"Could not reach OpenAI after {self.attempts} attempts: {self.detail}. "
                    "This does not establish that the key is bad. Check connectivity, then rerun.")
        return f"Unexpected error from {self.request}: {self.detail}"


def classify_exception(exc: BaseException) -> tuple[str, int | None]:
    """Map SDK exceptions to preflight kinds without importing the SDK at module import."""
    import openai

    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "auth", exc.status_code
    if isinstance(exc, openai.APIConnectionError):  # includes APITimeoutError
        return "network", None
    if isinstance(exc, openai.RateLimitError):
        return "network", exc.status_code
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return "network", exc.status_code
        if exc.status_code in (401, 403):
            return "auth", exc.status_code
        return "other", exc.status_code
    return "other", None


def make_client(settings: Settings, timeout: float = 20.0):
    """Explicit key mapping: the SDK never consults OPENAI_API_KEY from the environment."""
    import openai

    if not settings.key_present:
        raise ValueError("no key")
    return openai.OpenAI(api_key=settings.openai_api_key.strip(), project=settings.openai_project_id,
                         max_retries=0, timeout=timeout)


def check_openai_key(settings: Settings, backoff=DEFAULT_BACKOFF, sleep=time.sleep,
                     client_factory=make_client) -> PreflightResult:
    result = PreflightResult(kind="missing", key=settings.key_fingerprint(),
                             project_id=settings.openai_project_id,
                             checked_at=datetime.now(timezone.utc).isoformat(),
                             warnings=list(settings.warnings))
    if not settings.key_present:
        result.detail = "OPEN_AI_API_KEY absent or empty"
        return result
    client = client_factory(settings)
    delays = list(backoff)
    attempt = 0
    while True:
        attempt += 1
        result.attempts = attempt
        try:
            raw = client.models.with_raw_response.list()
            page = raw.parse()
            result.kind = "ok"
            result.status_code = raw.http_response.status_code
            result.request_id = raw.http_response.headers.get("x-request-id")
            result.model_count = len(list(page.data))
            result.detail = f"{result.model_count} models visible"
            return result
        except Exception as exc:  # noqa: BLE001 - classified below
            kind, status = classify_exception(exc)
            result.kind = kind
            result.status_code = status
            result.detail = redact(f"{type(exc).__name__}: {exc}", [settings.openai_api_key])[:500]
            request_id = getattr(exc, "request_id", None)
            if request_id:
                result.request_id = request_id
            if kind == "network" and delays:
                sleep(delays.pop(0))
                continue
            return result


def record_preflight(result: PreflightResult, runs_dir: Path) -> Path:
    """Append a key-free record; these checks are not inference and stay out of request ledgers."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / "key-checks.jsonl"
    with path.open("a") as handle:
        handle.write(json.dumps(asdict(result)) + "\n")
    return path


def run_preflight(env_path: Path | None = None, record: bool = True) -> PreflightResult:
    settings = load_settings(env_path)
    result = check_openai_key(settings)
    if record:
        record_preflight(result, settings.runs_dir)
    return result


def format_report(result: PreflightResult) -> str:
    lines = [f"preflight: {result.kind.upper()}", f"  request: {result.request}",
             f"  key: {result.key}", f"  attempts: {result.attempts}"]
    if result.status_code is not None:
        lines.append(f"  status: {result.status_code}")
    if result.request_id:
        lines.append(f"  x-request-id: {result.request_id}")
    if result.model_count is not None:
        lines.append(f"  models visible: {result.model_count}")
    lines.append(f"  project: {result.project_id or '(not set)'}")
    for warning in result.warnings:
        lines.append(f"  warning: {warning}")
    if not result.ok:
        lines.append(f"  ESCALATE: {result.escalation_message()}")
    return "\n".join(lines)
