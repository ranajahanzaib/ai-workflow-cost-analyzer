"""Idempotently load the generated synthetic demo."""

import hashlib
import json
from pathlib import Path

from outcomemeter.database import initialize
from outcomemeter.main import import_records

initialize()
for path in (
    Path(__file__).resolve().parent.parent / "examples/support-triage/demo.json",
    Path(__file__).resolve().parent.parent / "examples/invoice-processing/demo.json",
):
    data = path.read_bytes()
    print(path.name, import_records(json.loads(data), path.name, hashlib.sha256(data).hexdigest()))
