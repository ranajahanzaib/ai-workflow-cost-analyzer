import json

import pytest
from fastapi.testclient import TestClient

from outcomemeter import database
from outcomemeter.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "api.duckdb")
    with TestClient(app) as test_client:
        yield test_client


def seed_api(client):
    project = client.post("/api/projects", json={"name": "Test project"}).json()
    workflow = client.post(
        "/api/workflows",
        json={
            "project_id": project["id"],
            "name": "Workflow",
            "baseline_hourly_rate": "30",
            "baseline_minutes": "8",
        },
    ).json()
    a = client.post(
        f"/api/workflows/{workflow['id']}/configurations", json={"name": "A", "model": "a-v1"}
    ).json()
    b = client.post(
        f"/api/workflows/{workflow['id']}/configurations", json={"name": "B", "model": "b-v1"}
    ).json()
    records = [
        {
            "event_type": "task_case",
            "id": "case-1",
            "workflow_id": workflow["id"],
            "baseline_cost_usd": "4.00",
            "expected_outcome": {"class": "billing"},
        }
    ]
    for cfg, status, cost in ((a, "unverified", "0.10"), (b, "verified_success", "0.20")):
        eid = f"exec-{cfg['id']}"
        records += [
            {
                "event_type": "execution",
                "id": eid,
                "workflow_id": workflow["id"],
                "configuration_id": cfg["id"],
                "task_case_id": "case-1",
                "outcome": status,
                "attempts": 2,
                "baseline_cost_usd": "4.00",
            },
            {
                "event_type": "attempt",
                "id": f"{eid}-attempt-1",
                "execution_id": eid,
                "attempt_number": 1,
                "status": "error",
            },
            {
                "event_type": "attempt",
                "id": f"{eid}-attempt-2",
                "execution_id": eid,
                "attempt_number": 2,
                "status": "finished",
            },
            {
                "event_type": "model_call",
                "id": f"{eid}-call",
                "execution_id": eid,
                "attempt_id": f"{eid}-attempt-2",
                "reported_cost_usd": cost,
            },
        ]
    response = client.post(
        "/api/imports",
        files={
            "file": (
                "fixture.json",
                json.dumps({"schema_version": "1.0", "records": records}),
                "application/json",
            )
        },
    )
    assert response.status_code == 200, response.text
    return workflow, a, b


def test_workflow_comparison_scenario_verification_and_report(client):
    workflow, a, b = seed_api(client)
    overview = client.get("/api/dashboard", params={"workflow_id": workflow["id"]}).json()
    assert overview["metrics"]["executions"] == 2
    assert overview["metrics"]["missing_model_costs"] == 0
    comparison = client.get(
        "/api/compare", params={"workflow_id": workflow["id"], "a": a["id"], "b": b["id"]}
    ).json()
    assert comparison["matched_cases"] == 1
    assert comparison["configurations"][b["id"]]["metrics"]["cost_per_verified_success"] == "0.20"
    result = client.post(
        "/api/scenario",
        json={
            "workflow_id": workflow["id"],
            "hourly_rate": "36",
            "baseline_minutes": "8",
            "review_minutes": "0",
            "model_cost_multiplier": "1",
        },
    )
    assert result.status_code == 200 and result.json()["historical_data_changed"] is False
    assert result.json()["maximum_viable_workflow_cost_per_task"] == "4.80"
    execution_id = f"exec-{a['id']}"
    verified = client.post(
        f"/api/verifications/{execution_id}",
        json={"status": "verified_success", "verified_by": "QA", "reference": "case-1"},
    )
    assert verified.status_code == 201
    detail = client.get(f"/api/executions/{execution_id}").json()
    assert detail["execution"]["outcome"] == "verified_success"
    assert detail["evidence"][0]["method"] == "manual_attestation"
    assert (
        client.get("/api/reports/workflow.csv", params={"workflow_id": workflow["id"]})
        .headers["content-type"]
        .startswith("text/csv")
    )


def test_otel_import_requires_mapping_then_persists_unknown_result(client):
    workflow, a, _ = seed_api(client)
    trace = "ab" * 16
    body = {
        "workflow_id": workflow["id"],
        "configuration_id": a["id"],
        "task_case_id_by_trace": {trace: "case-1"},
        "document": {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": trace,
                                    "spanId": "01",
                                    "attributes": [
                                        {
                                            "key": "gen_ai.request.model",
                                            "value": {"stringValue": "a-v1"},
                                        },
                                        {
                                            "key": "gen_ai.usage.input_tokens",
                                            "value": {"intValue": "9"},
                                        },
                                    ],
                                }
                            ]
                        }
                    ]
                }
            ]
        },
    }
    response = client.post("/api/imports/otel", json=body)
    assert response.status_code == 200, response.text
    execution = client.get(
        "/api/executions", params={"workflow_id": workflow["id"], "search": "otel-"}
    ).json()["items"][0]
    assert execution["outcome"] == "unverified"
    assert execution["missing_model_costs"] == 1


def test_csv_model_usage_import_is_validated_and_transactional(client):
    _workflow, a, _ = seed_api(client)
    execution_id = f"exec-{a['id']}"
    content = (
        "record_type,event_id,execution_id,provider,model,input_tokens,output_tokens,reported_cost_usd\n"
        f"model_call,csv-call,{execution_id},example,model-x,250,50,0.004\n"
    )
    dry = client.post(
        "/api/imports?dry_run=true", files={"file": ("usage.csv", content, "text/csv")}
    )
    assert dry.status_code == 200 and dry.json()["valid"]
    before = len(client.get(f"/api/executions/{execution_id}").json()["model_calls"])
    assert len(client.get(f"/api/executions/{execution_id}").json()["model_calls"]) == before
    saved = client.post("/api/imports", files={"file": ("usage.csv", content, "text/csv")})
    assert saved.status_code == 200 and saved.json()["accepted"] == 1
    calls = client.get(f"/api/executions/{execution_id}").json()["model_calls"]
    assert len(calls) == before + 1 and calls[-1]["reported_cost"] == "0.00400000"


def test_effective_dated_pricing_calculates_and_snapshots_call_cost(client):
    _workflow, a, _ = seed_api(client)
    execution_id = f"exec-{a['id']}"
    profile = client.post(
        "/api/pricing",
        json={
            "provider": "example",
            "model": "model-y",
            "effective_from": "2020-01-01T00:00:00Z",
            "input_price_per_million": "2",
            "output_price_per_million": "10",
        },
    )
    assert profile.status_code == 201
    records = {
        "schema_version": "1.0",
        "records": [
            {
                "event_type": "model_call",
                "id": "priced-call",
                "execution_id": execution_id,
                "provider": "example",
                "model": "model-y",
                "input_tokens": 1000000,
                "output_tokens": 100000,
            }
        ],
    }
    imported = client.post(
        "/api/imports", files={"file": ("priced.json", json.dumps(records), "application/json")}
    )
    assert imported.status_code == 200
    calls = client.get(f"/api/executions/{execution_id}").json()["model_calls"]
    call = next(x for x in calls if x["id"] == "priced-call")
    assert call["calculated_cost"] == "3.00000000"
    assert call["pricing_source"] == f"pricing_profile:{profile.json()['id']}"
