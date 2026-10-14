"""Append-only audit trail at output/audit_trail.json (a JSON array)."""

import json
import os
import threading
from pathlib import Path

from backend.config import AUDIT_PATH
from backend.models import AuditRecord

_lock = threading.Lock()


def append_record(record: AuditRecord, path: Path = AUDIT_PATH) -> None:
    """Add one record to the end of the trail, keeping every earlier record.

    The file is rewritten through a temp file + atomic rename so a crash can't
    leave half a file. If the existing file isn't a valid JSON array we stop
    rather than risk overwriting history.
    """
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        if path.exists() and path.stat().st_size:
            records = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(records, list):
                raise ValueError(f"{path} is not a JSON array; refusing to overwrite it.")
        records.append(record.model_dump(mode="json"))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)


def read_records(path: Path = AUDIT_PATH) -> list[dict]:
    """Every record in the trail, oldest first (empty if no run has happened yet)."""
    with _lock:  # never read while a write is mid-replace
        if not path.exists() or not path.stat().st_size:
            return []
        return json.loads(path.read_text(encoding="utf-8"))
