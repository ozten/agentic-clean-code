"""Load harness configuration from the repository .env file.

The OpenAI key is read from ``OPEN_AI_API_KEY`` (exactly that spelling) and handed
to the SDK explicitly. It is never exported into ``os.environ``; tool subprocesses
run with a minimal environment built elsewhere, so the key cannot leak into the
solving sandbox (design OA01, V08).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
KEY_VARIABLE = "OPEN_AI_API_KEY"


def parse_dotenv(text: str) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, optional quotes, # comments, export prefix."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def read_dotenv(path: Path | None = None) -> dict[str, str]:
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return {}
    return parse_dotenv(path.read_text())


def write_dotenv_value(key: str, value: str, path: Path | None = None) -> Path:
    """Set or replace one variable in .env, preserving other lines. Used only for .env."""
    path = path or REPO_ROOT / ".env"
    lines = path.read_text().splitlines() if path.exists() else []
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        name = stripped[len("export "):] if stripped.startswith("export ") else stripped
        if name.split("=", 1)[0].strip() == key and "=" in name:
            lines[index] = f"{key}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


@dataclass
class Settings:
    openai_api_key: str | None
    openai_project_id: str | None
    runs_dir: Path
    concurrency: int = 1
    max_usd_cap: Decimal | None = None
    source: str = ".env"
    warnings: list[str] = field(default_factory=list)

    @property
    def key_present(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    def key_fingerprint(self) -> str:
        """Non-reversible description for logs: never the key itself."""
        if not self.key_present:
            return "absent"
        return f"present (length {len(self.openai_api_key.strip())})"


def load_settings(path: Path | None = None, environ: dict[str, str] | None = None) -> Settings:
    """Read .env; values already in the process environment do NOT override it for the key.

    The key comes only from .env so that an inherited OPENAI_API_KEY from a shell
    cannot silently substitute for the experiment credential (design OA01).
    """
    values = read_dotenv(path)
    environ = os.environ if environ is None else environ
    warnings: list[str] = []
    key = values.get(KEY_VARIABLE)
    if key is not None:
        key = key.strip() or None
    project = (values.get("OPENAI_PROJECT_ID") or environ.get("OPENAI_PROJECT_ID") or "").strip() or None
    runs_dir = (values.get("HARNESS_RUNS_DIR") or environ.get("HARNESS_RUNS_DIR") or "").strip()
    runs_path = Path(runs_dir).expanduser() if runs_dir else REPO_ROOT / "runs"
    if not runs_path.is_absolute():
        runs_path = REPO_ROOT / runs_path
    concurrency_text = (values.get("HARNESS_CONCURRENCY") or environ.get("HARNESS_CONCURRENCY") or "1").strip()
    try:
        concurrency = max(1, int(concurrency_text))
    except ValueError:
        warnings.append(f"HARNESS_CONCURRENCY={concurrency_text!r} is not an integer; using 1")
        concurrency = 1
    cap_text = (values.get("HARNESS_MAX_USD_CAP") or environ.get("HARNESS_MAX_USD_CAP") or "").strip()
    max_cap: Decimal | None = None
    if cap_text:
        try:
            max_cap = Decimal(cap_text)
            if max_cap <= 0:
                raise InvalidOperation
        except InvalidOperation:
            warnings.append(f"HARNESS_MAX_USD_CAP={cap_text!r} is not a positive decimal; ignoring")
            max_cap = None
    if not project:
        warnings.append("OPENAI_PROJECT_ID is empty; design OA01 asks for a dedicated project ID in the manifest")
    return Settings(openai_api_key=key, openai_project_id=project, runs_dir=runs_path,
                    concurrency=concurrency, max_usd_cap=max_cap,
                    source=str(path or REPO_ROOT / ".env"), warnings=warnings)


def sandbox_environment(home: Path) -> dict[str, str]:
    """Minimal environment for tool subprocesses: no inherited variables at all."""
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(home),
        "TMPDIR": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "TERM": "dumb",
    }


def redact(text: str, secrets: list[str | None]) -> str:
    """Replace any occurrence of a secret with a fixed marker before persisting text."""
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    return text
