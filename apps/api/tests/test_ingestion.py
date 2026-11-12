import hashlib
import json

import pytest

from outcomemeter import database
from outcomemeter.main import import_records


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.duckdb")
    database.initialize()
    return database.DB_PATH


def test_native_import_and_checksum_idempotency(isolated_db):
    records = [
        {"event_type": "project", "id": "p", "name": "Project"},
        {"event_type": "workflow", "id": "w", "project_id": "p", "name": "Workflow"},
        {"event_type": "configuration", "id": "c", "workflow_id": "w", "name": "Config"},
        {"event_type": "task_case", "id": "case-1", "workflow_id": "w"},
        {
            "event_type": "execution",
            "id": "e",
            "workflow_id": "w",
            "configuration_id": "c",
            "task_case_id": "case-1",
            "outcome": "verified_success",
        },
        {"event_type": "model_call", "id": "m", "execution_id": "e", "reported_cost_usd": "0.25"},
    ]
    payload = {"schema_version": "1.0", "records": records}
    checksum = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    assert import_records(payload, "sample.json", checksum)["accepted"] == len(records)
    assert import_records(payload, "sample.json", checksum)["duplicate"] is True
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 1


def test_broken_relationship_rolls_back_whole_import(isolated_db):
    payload = {
        "schema_version": "1.0",
        "records": [
            {"event_type": "project", "id": "p", "name": "Project"},
            {"event_type": "workflow", "id": "w", "project_id": "missing", "name": "Workflow"},
        ],
    }
    with pytest.raises(ValueError, match="record 2"):
        import_records(payload, "broken.json", "a" * 64)
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        assert db.execute("SELECT status FROM imports").fetchone()[0] == "failed"
        assert db.execute("SELECT row_number FROM import_errors").fetchone()[0] == 2


def test_dry_run_validates_without_persisting(isolated_db):
    payload = {
        "schema_version": "1.0",
        "records": [
            {"event_type": "project", "id": "p", "name": "Project"},
            {"event_type": "workflow", "id": "w", "project_id": "p", "name": "Workflow"},
        ],
    }
    result = import_records(payload, "preview.json", "c" * 64, dry_run=True)
    assert result["valid"] is True and result["accepted"] == 2
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 0


def test_negative_cost_and_cached_token_overflow_are_rejected(isolated_db):
    base = [
        {"event_type": "project", "id": "p", "name": "Project"},
        {"event_type": "workflow", "id": "w", "project_id": "p", "name": "Workflow"},
        {"event_type": "configuration", "id": "c", "workflow_id": "w", "name": "Config"},
        {"event_type": "task_case", "id": "case", "workflow_id": "w"},
        {
            "event_type": "execution",
            "id": "e",
            "workflow_id": "w",
            "configuration_id": "c",
            "task_case_id": "case",
        },
        {
            "event_type": "model_call",
            "id": "m",
            "execution_id": "e",
            "input_tokens": 1,
            "cached_tokens": 2,
            "reported_cost_usd": "-1",
        },
    ]
    with pytest.raises(ValueError, match="invalid token counts"):
        import_records({"schema_version": "1.0", "records": base}, "bad.json", "b" * 64)
