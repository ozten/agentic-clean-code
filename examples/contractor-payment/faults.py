"""Fault adapters for tests and the demo; not part of the application wiring."""
import errno


class DiskFullOnConfirmation:
    """An injected boundary failure, not an actual full disk or SQLite fault."""

    def __init__(self, inner):
        self.inner = inner

    def prepare(self, payment, now):
        return self.inner.prepare(payment, now)

    def confirm(self, payment, transfer_id):
        raise OSError(errno.ENOSPC, "Disk full while saving transfer confirmation")
