"""Record a transport boundary to a configurable directory; never trace the sink."""
import json
import os
import time
import uuid
from dataclasses import asdict
from pathlib import Path


class Recorder:
    def __init__(self, inner, root, global_trace_id):
        self.inner = inner
        self.root = Path(root)
        self.global_trace_id = global_trace_id

    def send(self, request):
        return self.record("http", "send", request, lambda: self.inner.send(request))

    def record(self, interface, operation, inputs, action, serialize=lambda value: value):
        trace_id = str(uuid.uuid4())
        directory = self.root / ("trace-" + trace_id)
        directory.mkdir(parents=True)
        record = {
            "schema_version": 1, "trace_id": trace_id,
            "global_trace_id": self.global_trace_id,
            "interface": interface, "operation": operation,
            "inputs": inputs, "outputs": None,
            "metadata": {"complete": False, "error_code": None,
                         "started_at_unix": time.time()},
        }
        self._write(directory, record)  # If this fails, do not start the remote action.
        try:
            result = action()
        except Exception as exc:
            record["metadata"].update(complete=True, error_code=type(exc).__name__,
                                      error_message=str(exc))
            self._write(directory, record)
            raise
        record["outputs"] = serialize(result)
        record["metadata"]["complete"] = True
        self._write(directory, record)
        return result

    @staticmethod
    def _write(directory, record):
        temporary = directory / "trace.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        os.replace(temporary, directory / "trace.json")


class LedgerRecorder(Recorder):
    def prepare(self, payment, now):
        return self.record("ledger", "prepare", {"payment": asdict(payment), "now": now},
                           lambda: self.inner.prepare(payment, now), asdict)

    def confirm(self, payment, transfer_id):
        return self.record("ledger", "confirm",
                           {"payment": asdict(payment), "transfer_id": transfer_id},
                           lambda: self.inner.confirm(payment, transfer_id))


def fixture_from_trace(path):
    """Explicitly select one record. No directory search or inferred matching."""
    record = json.loads(Path(path).read_text())
    if record["interface"] != "http" or record["operation"] != "send":
        raise ValueError("This playback converter accepts only HTTP send traces")
    if not record["metadata"]["complete"]:
        raise ValueError("Cannot play back an incomplete trace")
    error = record["metadata"]["error_code"]
    if error == "TimeoutError":
        outcome = {"kind": "timeout"}
    elif error is None and record["outputs"] is not None:
        outcome = {"kind": "response", "response": record["outputs"]}
    else:
        raise ValueError("This small playback adapter does not support that outcome")
    return {"provenance": "recorded local demo interaction", "request": record["inputs"],
            "outcome": outcome}
