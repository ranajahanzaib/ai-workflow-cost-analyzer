"""FastAPI delivery layer for AI Workflow Cost Analyzer."""

import csv
import hashlib
import io
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .database import WRITE_LOCK, connect, initialize
from .economics import aggregate, display, human_cost, inference_cost
from .otel import adapt_otlp


@asynccontextmanager
async def lifespan(_app):
    initialize()
    yield


app = FastAPI(
    title="AI Workflow Cost Analyzer API",
    version="0.1.0",
    description="Local-first AI workflow economics",
    lifespan=lifespan,
)
cors_origins = [
    x.strip()
    for x in os.environ.get(
        "AI_WORKFLOW_COST_ANALYZER_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if x.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
)


def rows(sql: str, params=()):
    with connect() as db:
        cur = db.execute(sql, list(params))
        names = [x[0] for x in cur.description]
        return [
            {
                key: str(value)
                if isinstance(value, Decimal)
                else value.isoformat()
                if isinstance(value, datetime)
                else value
                for key, value in zip(names, row)
            }
            for row in cur.fetchall()
        ]


def jsonable(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError


def execution_rows(where="", params=(), limit=None, offset=0):
    query = f"""SELECT e.id,e.workflow_id,e.configuration_id,c.name AS \"configuration\",e.task_case_id,e.category,
      e.runtime_status,e.outcome,e.attempts,e.fallback_completed,e.baseline_cost,
      e.experiment_id,
      COALESCE((SELECT SUM(COALESCE(reported_cost,calculated_cost)) FROM model_calls m WHERE m.execution_id=e.id),0) inference_cost,
      COALESCE((SELECT SUM(COALESCE(reported_cost,calculated_cost)) FROM model_calls m JOIN attempts a ON a.id=m.attempt_id WHERE m.execution_id=e.id AND a.attempt_number>1),0) retry_inference_cost,
      COALESCE((SELECT COUNT(*) FROM model_calls m WHERE m.execution_id=e.id AND m.reported_cost IS NULL AND m.calculated_cost IS NULL),0) missing_model_costs,
      COALESCE((SELECT COUNT(*) FROM model_calls m WHERE m.execution_id=e.id),0) model_call_count,
      COALESCE((SELECT SUM(cost) FROM tool_calls t WHERE t.execution_id=e.id),0) tool_cost,
      COALESCE((SELECT SUM(cost) FROM tool_calls t JOIN attempts a ON a.id=t.attempt_id WHERE t.execution_id=e.id AND a.attempt_number>1),0) retry_tool_cost,
      COALESCE((SELECT COUNT(*) FROM tool_calls t WHERE t.execution_id=e.id AND t.cost IS NULL),0) missing_tool_costs,
      COALESCE((SELECT COUNT(*) FROM tool_calls t WHERE t.execution_id=e.id),0) tool_call_count,
      COALESCE((SELECT COUNT(*) FROM human_work h WHERE h.execution_id=e.id),0) human_work_count,
      COALESCE((SELECT COUNT(*) FROM outcome_evidence o WHERE o.execution_id=e.id),0) evidence_count,
      (SELECT CASE WHEN COUNT(DISTINCT status)>1 THEN 1 ELSE 0 END FROM outcome_evidence o WHERE o.execution_id=e.id) conflicting_evidence,
      COALESCE((SELECT SUM(CASE WHEN h.cost IS NULL THEN h.minutes*h.hourly_rate/60 ELSE h.cost END) FROM human_work h WHERE h.execution_id=e.id AND h.category NOT IN ('fallback_completion')),0) human_cost,
      COALESCE((SELECT SUM(CASE WHEN h.cost IS NULL THEN h.minutes*h.hourly_rate/60 ELSE h.cost END) FROM human_work h WHERE h.execution_id=e.id AND h.category='fallback_completion'),0) fallback_cost,
      COALESCE((SELECT SUM(h.minutes) FROM human_work h WHERE h.execution_id=e.id AND h.category='fallback_completion'),0) fallback_minutes,
      (COALESCE((SELECT SUM(COALESCE(reported_cost,calculated_cost)) FROM model_calls m WHERE m.execution_id=e.id),0)
       + COALESCE((SELECT SUM(cost) FROM tool_calls t WHERE t.execution_id=e.id),0)
       + COALESCE((SELECT SUM(CASE WHEN h.cost IS NULL THEN h.minutes*h.hourly_rate/60 ELSE h.cost END) FROM human_work h WHERE h.execution_id=e.id),0)) total_cost,
      (e.outcome='verified_success' OR e.fallback_completed) resolved,e.started_at
      FROM executions e JOIN configurations c ON c.id=e.configuration_id {where} ORDER BY e.started_at DESC NULLS LAST"""
    query_params = list(params)
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        query_params += [limit, offset]
    return rows(query, query_params)


def clean_metric(agg):
    currency_metrics = {
        "total_cost",
        "cost_per_execution",
        "cost_per_verified_success",
        "cost_per_resolved_task",
        "baseline_cost",
        "net_savings_resolved",
        "retry_spending",
        "median_execution_cost",
        "p90_execution_cost",
        "p95_execution_cost",
    }
    return {
        k: (
            display(v)
            if isinstance(v, Decimal) and k in currency_metrics
            else format(v, "f")
            if isinstance(v, Decimal)
            else v
        )
        for k, v in agg.items()
    }


@app.get("/api/health")
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "storage": "DuckDB", "currency": "USD"}


@app.get("/api/workflows")
@app.get("/api/v1/workflows")
def workflows():
    return rows(
        "SELECT w.*,p.name project_name FROM workflows w JOIN projects p ON p.id=w.project_id ORDER BY w.name"
    )


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class WorkflowInput(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    task_type: str = Field(default="general", max_length=100)
    baseline_hourly_rate: Decimal = Field(default=Decimal(24), ge=0, le=100000)
    baseline_minutes: Decimal = Field(default=Decimal(12), ge=0, le=100000)


class ConfigurationInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=160)


@app.get("/api/projects")
@app.get("/api/v1/projects")
def projects():
    return rows("SELECT * FROM projects ORDER BY name")


@app.post("/api/projects", status_code=201)
@app.post("/api/v1/projects", status_code=201)
def create_project(data: ProjectInput):
    key = str(uuid4())
    with WRITE_LOCK, connect() as db:
        db.execute("INSERT INTO projects VALUES(?,?,?)", [key, data.name, data.description])
    return {"id": key, **data.model_dump()}


@app.post("/api/workflows", status_code=201)
@app.post("/api/v1/workflows", status_code=201)
def create_workflow(data: WorkflowInput):
    key = str(uuid4())
    with WRITE_LOCK, connect() as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", [data.project_id]).fetchone():
            raise HTTPException(404, "Project not found")
        db.execute(
            "INSERT INTO workflows(id,project_id,name,task_type,baseline_hourly_rate,baseline_minutes,description) VALUES(?,?,?,?,?,?,?)",
            [
                key,
                data.project_id,
                data.name,
                data.task_type,
                data.baseline_hourly_rate,
                data.baseline_minutes,
                data.description,
            ],
        )
    return {"id": key, **data.model_dump(mode="json")}


@app.get("/api/workflows/{workflow_id}/configurations")
@app.get("/api/v1/workflows/{workflow_id}/configurations")
def configurations(workflow_id: str):
    return rows("SELECT * FROM configurations WHERE workflow_id=? ORDER BY name", [workflow_id])


@app.get("/api/task-cases")
def task_cases(
    workflow_id: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)
):
    total = rows("SELECT COUNT(*) total FROM task_cases WHERE workflow_id=?", [workflow_id])[0][
        "total"
    ]
    return {
        "items": rows(
            "SELECT * FROM task_cases WHERE workflow_id=? ORDER BY id LIMIT ? OFFSET ?",
            [workflow_id, limit, offset],
        ),
        "total": total,
    }


@app.post("/api/workflows/{workflow_id}/configurations", status_code=201)
@app.post("/api/v1/workflows/{workflow_id}/configurations", status_code=201)
def create_configuration(workflow_id: str, data: ConfigurationInput):
    key = str(uuid4())
    with WRITE_LOCK, connect() as db:
        if not db.execute("SELECT 1 FROM workflows WHERE id=?", [workflow_id]).fetchone():
            raise HTTPException(404, "Workflow not found")
        db.execute(
            "INSERT INTO configurations VALUES(?,?,?,?)", [key, workflow_id, data.name, data.model]
        )
    return {"id": key, "workflow_id": workflow_id, **data.model_dump()}


@app.get("/api/executions")
@app.get("/api/v1/executions")
def executions(
    workflow_id: str | None = None,
    configuration_id: str | None = None,
    outcome: str | None = None,
    search: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    clauses = []
    params = []
    for col, val in [
        ("e.workflow_id", workflow_id),
        ("e.configuration_id", configuration_id),
        ("e.outcome", outcome),
    ]:
        if val:
            clauses.append(col + "=?")
            params.append(val)
    if search:
        clauses.append("(e.id ILIKE ? OR e.task_case_id ILIKE ? OR e.category ILIKE ?)")
        params += [f"%{search}%"] * 3
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    count = rows("SELECT COUNT(*) total FROM executions e " + where, params)[0]["total"]
    data = execution_rows(where, params, limit, offset)
    return {"items": data, "total": count, "limit": limit, "offset": offset}


@app.get("/api/executions/{execution_id}")
@app.get("/api/v1/executions/{execution_id}")
def execution_detail(execution_id: str):
    found = execution_rows("WHERE e.id=?", [execution_id])
    if not found:
        raise HTTPException(404, "Execution not found")
    return {
        "execution": found[0],
        "model_calls": rows("SELECT * FROM model_calls WHERE execution_id=?", [execution_id]),
        "tool_calls": rows("SELECT * FROM tool_calls WHERE execution_id=?", [execution_id]),
        "human_work": rows("SELECT * FROM human_work WHERE execution_id=?", [execution_id]),
        "attempts": rows(
            "SELECT * FROM attempts WHERE execution_id=? ORDER BY attempt_number", [execution_id]
        ),
        "evidence": rows(
            "SELECT * FROM outcome_evidence WHERE execution_id=? ORDER BY verified_at DESC",
            [execution_id],
        ),
    }


class VerificationInput(BaseModel):
    status: str
    verified_by: str = Field(min_length=1, max_length=160)
    reference: str | None = Field(default=None, max_length=1000)
    reasoning: str | None = Field(default=None, max_length=4000)


@app.post("/api/verifications/{execution_id}", status_code=201)
@app.post("/api/v1/verifications/{execution_id}", status_code=201)
def verify_execution(execution_id: str, data: VerificationInput):
    if data.status not in {"verified_success", "verified_failure", "indeterminate"}:
        raise HTTPException(
            422, "Status must be verified_success, verified_failure, or indeterminate"
        )
    evidence_id = str(uuid4())
    now = datetime.now(UTC).replace(tzinfo=None)
    with WRITE_LOCK, connect() as db:
        if not db.execute("SELECT 1 FROM executions WHERE id=?", [execution_id]).fetchone():
            raise HTTPException(404, "Execution not found")
        db.execute("BEGIN TRANSACTION")
        db.execute("UPDATE executions SET outcome=? WHERE id=?", [data.status, execution_id])
        db.execute(
            "INSERT INTO outcome_evidence(id,execution_id,method,status,reference,verified_at,reasoning) VALUES(?,?,?,?,?,?,?)",
            [
                evidence_id,
                execution_id,
                "manual_attestation",
                data.status,
                data.reference,
                now,
                f"Verified by {data.verified_by}. {data.reasoning or ''}".strip(),
            ],
        )
        db.execute("COMMIT")
    return {
        "id": evidence_id,
        "execution_id": execution_id,
        "status": data.status,
        "verified_at": now.isoformat(),
    }


@app.get("/api/baselines")
@app.get("/api/v1/baselines")
def baseline_profiles(workflow_id: str | None = None):
    if workflow_id:
        return rows(
            "SELECT * FROM baseline_profiles WHERE workflow_id=? ORDER BY version DESC",
            [workflow_id],
        )
    return rows("SELECT * FROM baseline_profiles ORDER BY workflow_id,version DESC")


class BaselineInput(BaseModel):
    workflow_id: str
    name: str = Field(min_length=1, max_length=160)
    hourly_rate: Decimal = Field(ge=0, le=100000)
    typical_minutes: Decimal = Field(ge=0, le=100000)
    other_costs: Decimal = Field(default=Decimal(0), ge=0, le=100000000)
    source: str = "user_provided"
    confidence: str = "assumption"
    notes: str | None = None


@app.post("/api/baselines", status_code=201)
@app.post("/api/v1/baselines", status_code=201)
def create_baseline(data: BaselineInput):
    key = str(uuid4())
    with WRITE_LOCK, connect() as db:
        if not db.execute("SELECT 1 FROM workflows WHERE id=?", [data.workflow_id]).fetchone():
            raise HTTPException(404, "Workflow not found")
        version = db.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM baseline_profiles WHERE workflow_id=?",
            [data.workflow_id],
        ).fetchone()[0]
        db.execute(
            "INSERT INTO baseline_profiles VALUES(?,?,?,?,?,?,?,?,?,?)",
            [
                key,
                data.workflow_id,
                data.name,
                data.hourly_rate,
                data.typical_minutes,
                data.other_costs,
                data.source,
                data.confidence,
                data.notes,
                version,
            ],
        )
    return {"id": key, "version": version, **data.model_dump(mode="json")}


@app.get("/api/pricing")
@app.get("/api/v1/pricing")
def pricing_profiles(provider: str | None = None, model: str | None = None):
    clauses = []
    params = []
    if provider:
        clauses.append("provider=?")
        params.append(provider)
    if model:
        clauses.append("model=?")
        params.append(model)
    return rows(
        "SELECT * FROM pricing_profiles"
        + (" WHERE " + " AND ".join(clauses) if clauses else "")
        + " ORDER BY provider,model,effective_from DESC",
        params,
    )


class PricingInput(BaseModel):
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    effective_from: datetime
    effective_until: datetime | None = None
    currency: str = "USD"
    input_price_per_million: Decimal = Field(ge=0)
    output_price_per_million: Decimal = Field(ge=0)
    cached_input_price_per_million: Decimal | None = Field(default=None, ge=0)
    source_type: str = "user_provided"
    source_reference: str | None = None


@app.post("/api/pricing", status_code=201)
@app.post("/api/v1/pricing", status_code=201)
def create_pricing(data: PricingInput):
    if data.currency != "USD":
        raise HTTPException(422, "MVP aggregation supports USD pricing only")
    if data.effective_until and data.effective_until <= data.effective_from:
        raise HTTPException(422, "effective_until must follow effective_from")
    key = str(uuid4())
    with WRITE_LOCK, connect() as db:
        db.execute(
            "INSERT INTO pricing_profiles(id,provider,model,effective_from,effective_until,currency,input_price_per_million,output_price_per_million,cached_input_price_per_million,source_type,source_reference) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            [
                key,
                data.provider,
                data.model,
                data.effective_from.astimezone(UTC).replace(tzinfo=None),
                data.effective_until.astimezone(UTC).replace(tzinfo=None)
                if data.effective_until
                else None,
                data.currency,
                data.input_price_per_million,
                data.output_price_per_million,
                data.cached_input_price_per_million,
                data.source_type,
                data.source_reference,
            ],
        )
    return {"id": key, **data.model_dump(mode="json")}


@app.get("/api/dashboard")
@app.get("/api/v1/analytics/overview")
def dashboard(workflow_id: str | None = None):
    ex = execution_rows(
        "WHERE e.workflow_id=?" if workflow_id else "", [workflow_id] if workflow_id else []
    )
    stats = clean_metric(aggregate(ex))
    config_ids = sorted({x["configuration_id"] for x in ex})
    configs = []
    for cid in config_ids:
        subset = [x for x in ex if x["configuration_id"] == cid]
        name = subset[0]["configuration"] if subset else cid
        configs.append({"id": cid, "name": name, "metrics": clean_metric(aggregate(subset))})
    breakdown = {
        k: display(sum((Decimal(str(x[k] or 0)) for x in ex), Decimal(0)))
        for k in ("inference_cost", "tool_cost", "human_cost", "fallback_cost")
    }
    quality = {
        "verified_success": stats["verified_successes"],
        "verified_failure": stats["verified_failures"],
        "unknown": stats["unknown_outcomes"],
    }
    categories = []
    for cat in sorted({x["category"] or "Uncategorized" for x in ex}):
        subset = [x for x in ex if (x["category"] or "Uncategorized") == cat]
        categories.append(
            {
                "category": cat,
                "executions": len(subset),
                "total_cost": display(
                    sum((Decimal(str(x["total_cost"])) for x in subset), Decimal(0))
                ),
            }
        )
    missing_baselines = sum(x["baseline_cost"] is None for x in ex)
    model_calls = sum(x["model_call_count"] for x in ex)
    unpriced = stats["missing_model_costs"] + stats["missing_tool_costs"]
    conflicts = sum(x["conflicting_evidence"] for x in ex)
    quality_data = {
        "unverified": stats["unknown_outcomes"],
        "missing_baselines": missing_baselines,
        "currency": "USD",
        "model_pricing_coverage": str(
            Decimal(model_calls - stats["missing_model_costs"]) / Decimal(model_calls)
            if model_calls
            else 0
        ),
        "verified_outcome_coverage": str(
            Decimal(stats["verified_successes"] + stats["verified_failures"]) / Decimal(len(ex))
            if ex
            else 0
        ),
        "baseline_coverage": str(
            Decimal(len(ex) - missing_baselines) / Decimal(len(ex)) if ex else 0
        ),
        "human_work_record_coverage": str(
            Decimal(sum(x["human_work_count"] > 0 for x in ex)) / Decimal(len(ex)) if ex else 0
        ),
        "evidence_coverage": str(
            Decimal(sum(x["evidence_count"] > 0 for x in ex)) / Decimal(len(ex)) if ex else 0
        ),
        "unpriced_operations": unpriced,
        "conflicting_evidence": conflicts,
        "unresolved_cases": stats["excluded_unresolved"],
    }
    quality_data["warnings"] = (
        stats["warnings"]
        + ([f"{unpriced} operations have unknown cost"] if unpriced else [])
        + ([f"{conflicts} executions have conflicting outcome evidence"] if conflicts else [])
        + ([f"{missing_baselines} executions lack baseline data"] if missing_baselines else [])
    )
    return {
        "metrics": stats,
        "cost_composition": breakdown,
        "outcomes": quality,
        "configurations": configs,
        "categories": categories,
        "workflows": workflows(),
        "data_quality": quality_data,
    }


@app.get("/api/v1/analytics/data-quality")
def data_quality(workflow_id: str | None = None):
    return dashboard(workflow_id)["data_quality"]


@app.get("/api/compare")
def compare(workflow_id: str, a: str, b: str):
    all_rows = execution_rows("WHERE e.workflow_id=?", [workflow_id])
    by = {c: [r for r in all_rows if r["configuration_id"] == c] for c in (a, b)}
    if not all(by.values()):
        raise HTTPException(404, "Both configurations need executions in this workflow")
    sets = [{r["task_case_id"] for r in rs} for rs in by.values()]
    matched = sets[0] & sets[1]
    paired = {}
    for cid, rs in by.items():
        selected = [r for r in rs if r["task_case_id"] in matched]
        paired[cid] = {
            "name": selected[0]["configuration"] if selected else cid,
            "metrics": clean_metric(aggregate(selected)),
            "cases": len({r["task_case_id"] for r in selected}),
        }
    return {
        "workflow_id": workflow_id,
        "matched_cases": len(matched),
        "unmatched_cases": {a: len(sets[0] - matched), b: len(sets[1] - matched)},
        "configurations": paired,
        "case_rows": [
            {
                "task_case_id": case,
                "a": next((r for r in by[a] if r["task_case_id"] == case), None),
                "b": next((r for r in by[b] if r["task_case_id"] == case), None),
            }
            for case in sorted(matched)
        ],
    }


class ComparisonInput(BaseModel):
    workflow_id: str
    configuration_a: str
    configuration_b: str


@app.post("/api/v1/comparisons")
def create_comparison(data: ComparisonInput):
    return compare(data.workflow_id, data.configuration_a, data.configuration_b)


class Scenario(BaseModel):
    workflow_id: str
    hourly_rate: Decimal = Field(ge=0, le=100000)
    baseline_minutes: Decimal = Field(ge=0, le=100000)
    review_minutes: Decimal = Field(ge=0, le=100000)
    correction_minutes: Decimal = Field(default=Decimal(0), ge=0, le=100000)
    model_cost_multiplier: Decimal = Field(default=Decimal(1), ge=0, le=1000)
    monthly_fixed_cost_usd: Decimal = Field(default=Decimal(0), ge=0, le=100000000)
    monthly_volume: int = Field(default=1000, ge=1, le=100000000)


@app.post("/api/scenario")
@app.post("/api/v1/scenarios/evaluate")
def scenario(s: Scenario):
    base = rows("SELECT * FROM workflows WHERE id=?", [s.workflow_id])
    if not base:
        raise HTTPException(404, "Workflow not found")
    ex = execution_rows("WHERE e.workflow_id=?", [s.workflow_id])
    overhead = s.monthly_fixed_cost_usd / Decimal(s.monthly_volume)
    adjusted = []
    for r in ex:
        r = dict(r)
        human = human_cost(
            s.review_minutes + s.correction_minutes + Decimal(str(r["fallback_minutes"])),
            s.hourly_rate,
        )
        r["human_cost"] = str(human_cost(s.review_minutes + s.correction_minutes, s.hourly_rate))
        r["fallback_cost"] = str(human_cost(Decimal(str(r["fallback_minutes"])), s.hourly_rate))
        r["total_cost"] = str(
            (Decimal(str(r["inference_cost"])) + Decimal(str(r["tool_cost"])))
            * s.model_cost_multiplier
            + human
            + overhead
        )
        r["baseline_cost"] = str(human_cost(s.baseline_minutes, s.hourly_rate))
        adjusted.append(r)
    metrics = aggregate(adjusted)
    baseline_hours = Decimal(len(ex)) * s.baseline_minutes / Decimal(60)
    assumed_ai_hours = Decimal(len(ex)) * (s.review_minutes + s.correction_minutes) / Decimal(
        60
    ) + sum((Decimal(str(r["fallback_minutes"])) for r in ex), Decimal(0)) / Decimal(60)
    fixed_ai_cost = sum(
        (
            (Decimal(str(r["inference_cost"])) + Decimal(str(r["tool_cost"])))
            * s.model_cost_multiplier
            + overhead
            for r in ex
        ),
        Decimal(0),
    )
    break_even = (
        fixed_ai_cost / (baseline_hours - assumed_ai_hours)
        if baseline_hours > assumed_ai_hours
        else None
    )
    sensitivity = []
    for rate in (Decimal(10), Decimal(20), Decimal(30), Decimal(40), Decimal(50), Decimal(60)):
        resolved_rows = [
            r for r in adjusted if r["outcome"] == "verified_success" or r.get("fallback_completed")
        ]
        savings = sum(
            (
                human_cost(s.baseline_minutes, rate)
                - Decimal(str(r["total_cost"]))
                + human_cost(
                    s.review_minutes + s.correction_minutes + Decimal(str(r["fallback_minutes"])),
                    s.hourly_rate,
                )
                for r in resolved_rows
            ),
            Decimal(0),
        )
        sensitivity.append({"hourly_rate": str(rate), "net_savings": display(savings)})
    return {
        "metrics": clean_metric(metrics),
        "assumptions": {
            "hourly_rate": str(s.hourly_rate),
            "baseline_minutes": str(s.baseline_minutes),
            "review_minutes": str(s.review_minutes),
            "correction_minutes": str(s.correction_minutes),
            "model_cost_multiplier": str(s.model_cost_multiplier),
            "monthly_fixed_cost_usd": str(s.monthly_fixed_cost_usd),
            "monthly_volume": s.monthly_volume,
            "allocated_infrastructure_per_execution": str(overhead),
        },
        "break_even_hourly_rate": str(break_even) if break_even is not None else None,
        "sensitivity": sensitivity,
        "maximum_viable_workflow_cost_per_task": display(
            human_cost(s.baseline_minutes - s.review_minutes - s.correction_minutes, s.hourly_rate)
            - overhead
        ),
        "historical_data_changed": False,
    }


class OTelImportInput(BaseModel):
    workflow_id: str
    configuration_id: str
    task_case_id_by_trace: dict[str, str] = Field(default_factory=dict)
    document: dict


def adapt_otel_request(data: OTelImportInput):
    if len(json.dumps(data.document, separators=(",", ":")).encode()) > 10_000_000:
        raise HTTPException(413, "Maximum OTLP import size is 10 MB")
    if not rows("SELECT id FROM workflows WHERE id=?", [data.workflow_id]):
        raise HTTPException(404, "Workflow not found")
    if not rows(
        "SELECT id FROM configurations WHERE id=? AND workflow_id=?",
        [data.configuration_id, data.workflow_id],
    ):
        raise HTTPException(404, "Configuration not found in workflow")
    span_count = (
        sum(
            len(scope.get("spans", []))
            for group in data.document.get("resourceSpans", [])
            if isinstance(group, dict)
            for scope in group.get("scopeSpans", group.get("instrumentationLibrarySpans", []))
        )
        if isinstance(data.document.get("resourceSpans"), list)
        else 0
    )
    if span_count > 50000:
        raise HTTPException(413, "Maximum OTLP import size is 50,000 spans")
    for trace, case_id in data.task_case_id_by_trace.items():
        if not rows(
            "SELECT id FROM task_cases WHERE id=? AND workflow_id=?", [case_id, data.workflow_id]
        ):
            raise HTTPException(422, f"Task case mapping for trace {trace} is not in this workflow")
    try:
        return adapt_otlp(
            data.document, data.workflow_id, data.configuration_id, data.task_case_id_by_trace
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/imports/otel/preview")
@app.post("/api/v1/imports/otel/preview")
def otel_preview(data: OTelImportInput):
    payload, summary = adapt_otel_request(data)
    return {
        **summary,
        "rows": len(payload["records"]),
        "sample": payload["records"][:10],
        "mapping_required": bool(
            summary["warnings"] and any("no task-case mapping" in w for w in summary["warnings"])
        ),
    }


@app.post("/api/imports/otel")
@app.post("/api/v1/imports/otel")
def otel_import(data: OTelImportInput, dry_run: bool = False):
    payload, summary = adapt_otel_request(data)
    missing = [w for w in summary["warnings"] if "no task-case mapping" in w]
    if missing:
        raise HTTPException(
            422, {"message": "Map every trace to a task case before importing", "warnings": missing}
        )
    checksum = hashlib.sha256(
        json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    result = import_records(payload, "otlp-json", checksum, dry_run=dry_run)
    return {**result, **summary}


def parse_native(data: bytes):
    text = data.decode("utf-8-sig")
    stripped = text.lstrip()
    if not stripped:
        raise ValueError("File is empty")
    if stripped.startswith("{"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
            return {"schema_version": "1.0", "records": records}
        if isinstance(obj, list):
            return {"schema_version": "1.0", "records": obj}
        if "records" not in obj:
            # One-record event shorthand
            return {"schema_version": obj.get("schema_version", "1.0"), "records": [obj]}
        return obj
    raise ValueError("Expected JSON or JSONL")


def validate_upload(file: UploadFile):
    if file.filename and ("/" in file.filename or "\\" in file.filename):
        raise HTTPException(400, "Unsafe filename")
    suffix = (
        file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    )
    if suffix and suffix not in {"json", "jsonl", "ndjson", "csv"}:
        raise HTTPException(415, "Supported file extensions are .json, .jsonl, .ndjson, and .csv")
    allowed = {
        "application/json",
        "application/x-ndjson",
        "application/ndjson",
        "text/plain",
        "text/csv",
        "application/vnd.ms-excel",
        "application/octet-stream",
    }
    if file.content_type and file.content_type.lower() not in allowed:
        raise HTTPException(415, "Unsupported upload MIME type")


def csv_records(data: bytes, default_workflow=None, default_configuration=None):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not reader.fieldnames:
        raise ValueError("CSV file requires a header row")
    records = []
    for line, row in enumerate(reader, 2):
        kind = (row.get("record_type") or "execution").strip()
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if kind == "execution":
            record = {
                "event_type": kind,
                "id": row.get("execution_id"),
                "workflow_id": row.get("workflow_id") or default_workflow,
                "configuration_id": row.get("configuration_id") or default_configuration,
                "task_case_id": row.get("task_case_id"),
                "category": row.get("category") or None,
                "runtime_status": row.get("runtime_status") or "finished",
                "outcome": row.get("outcome") or "unverified",
                "attempts": row.get("attempts") or 1,
                "baseline_cost_usd": row.get("baseline_cost_usd") or None,
                "started_at": row.get("started_at") or None,
                "fallback_completed": str(row.get("fallback_completed", "")).lower()
                in {"true", "1", "yes"},
            }
        elif kind == "model_call":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "execution_id": row.get("execution_id"),
                "attempt_id": row.get("attempt_id") or None,
                "provider": row.get("provider"),
                "model": row.get("model"),
                "input_tokens": row.get("input_tokens") or 0,
                "output_tokens": row.get("output_tokens") or 0,
                "cached_tokens": row.get("cached_tokens") or 0,
                "reported_cost_usd": row.get("reported_cost_usd") or None,
                "calculated_cost_usd": row.get("calculated_cost_usd") or None,
                "pricing_source": row.get("pricing_source"),
            }
        elif kind == "tool_call":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "execution_id": row.get("execution_id"),
                "attempt_id": row.get("attempt_id") or None,
                "name": row.get("name"),
                "status": row.get("status") or "success",
                "cost_usd": row.get("cost_usd") or None,
            }
        elif kind == "human_work":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "execution_id": row.get("execution_id"),
                "category": row.get("category"),
                "minutes": row.get("minutes"),
                "hourly_rate_usd": row.get("hourly_rate_usd"),
            }
        elif kind == "outcome_evidence":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "execution_id": row.get("execution_id"),
                "method": row.get("method"),
                "status": row.get("status"),
                "reference": row.get("reference"),
                "reasoning": row.get("reasoning"),
            }
        elif kind == "task_case":
            try:
                record = {
                    "event_type": kind,
                    "id": row.get("case_id"),
                    "workflow_id": row.get("workflow_id") or default_workflow,
                    "external_case_id": row.get("external_case_id"),
                    "category": row.get("category"),
                    "difficulty": row.get("difficulty"),
                    "description": row.get("description"),
                    "baseline_cost_usd": row.get("baseline_cost_usd") or None,
                    "baseline_minutes": row.get("baseline_minutes") or None,
                    "expected_outcome": json.loads(row["expected_outcome_json"])
                    if row.get("expected_outcome_json")
                    else None,
                    "metadata": json.loads(row["metadata_json"])
                    if row.get("metadata_json")
                    else {},
                }
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"CSV row {line}: invalid JSON in expected_outcome_json or metadata_json"
                ) from exc
        elif kind == "baseline_profile":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "workflow_id": row.get("workflow_id") or default_workflow,
                "name": row.get("name"),
                "hourly_rate_usd": row.get("hourly_rate_usd"),
                "typical_minutes": row.get("typical_minutes"),
                "other_costs_usd": row.get("other_costs_usd") or "0",
                "source": row.get("source") or "user_provided",
                "confidence": row.get("confidence") or "assumption",
                "notes": row.get("notes"),
                "version": row.get("version") or "1",
            }
        elif kind == "pricing_profile":
            record = {
                "event_type": kind,
                "id": row.get("event_id"),
                "provider": row.get("provider"),
                "model": row.get("model"),
                "effective_from": row.get("effective_from"),
                "effective_until": row.get("effective_until") or None,
                "currency": row.get("currency") or "USD",
                "input_price_per_million": row.get("input_price_per_million"),
                "output_price_per_million": row.get("output_price_per_million"),
                "cached_input_price_per_million": row.get("cached_input_price_per_million") or None,
                "source_type": row.get("source_type") or "user_provided",
                "source_reference": row.get("source_reference"),
            }
        else:
            raise ValueError(f"CSV row {line}: unsupported record_type '{kind}'")
        if not record.get("id"):
            raise ValueError(f"CSV row {line}: event_id/execution_id/case_id is required")
        records.append(record)
        if len(records) > 50000:
            raise ValueError("CSV is limited to 50,000 rows")
    return records


def import_records(payload: dict, filename: str, checksum: str, dry_run: bool = False):
    if payload.get("schema_version") not in ("1.0", "1"):
        raise ValueError("Unsupported schema_version; expected 1.0")
    records = payload.get("records")
    if not isinstance(records, list) or len(records) > 50000:
        raise ValueError("records must be a list of at most 50,000 events")
    accepted = 0
    with WRITE_LOCK, connect() as db:
        if db.execute(
            "SELECT 1 FROM imports WHERE checksum=? AND status='completed'", [checksum]
        ).fetchone():
            return {"duplicate": True, "accepted": 0, "rejected": 0}
        try:
            db.execute("BEGIN TRANSACTION")
            for i, r in enumerate(records, 1):
                try:
                    typ = r.get("event_type")
                    if typ == "project":
                        db.execute(
                            "INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO NOTHING",
                            [r["id"], r["name"], r.get("description")],
                        )
                    elif typ == "workflow":
                        if not db.execute(
                            "SELECT 1 FROM projects WHERE id=?", [r["project_id"]]
                        ).fetchone():
                            raise ValueError("project_id does not reference an imported project")
                        db.execute(
                            "INSERT INTO workflows(id,project_id,name,task_type,baseline_profile_id,baseline_hourly_rate,baseline_minutes,description) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["project_id"],
                                r["name"],
                                r.get("task_type"),
                                r.get("baseline_profile_id"),
                                Decimal(str(r.get("baseline_hourly_rate", 24))),
                                Decimal(str(r.get("baseline_minutes", 12))),
                                r.get("description"),
                            ],
                        )
                    elif typ == "configuration":
                        if not db.execute(
                            "SELECT 1 FROM workflows WHERE id=?", [r["workflow_id"]]
                        ).fetchone():
                            raise ValueError("workflow_id does not reference an imported workflow")
                        db.execute(
                            "INSERT INTO configurations VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [r["id"], r["workflow_id"], r["name"], r.get("model", "unknown")],
                        )
                    elif typ == "task_case":
                        if not db.execute(
                            "SELECT 1 FROM workflows WHERE id=?", [r["workflow_id"]]
                        ).fetchone():
                            raise ValueError("workflow_id does not reference an imported workflow")
                        baseline = (
                            Decimal(str(r["baseline_cost_usd"]))
                            if r.get("baseline_cost_usd") is not None
                            else None
                        )
                        minutes = (
                            Decimal(str(r["baseline_minutes"]))
                            if r.get("baseline_minutes") is not None
                            else None
                        )
                        if (
                            baseline is not None
                            and baseline < 0
                            or minutes is not None
                            and minutes < 0
                        ):
                            raise ValueError("case baseline values must be nonnegative")
                        db.execute(
                            "INSERT INTO task_cases VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["workflow_id"],
                                r.get("external_case_id"),
                                r.get("category"),
                                r.get("difficulty"),
                                r.get("description"),
                                baseline,
                                minutes,
                                json.dumps(r.get("expected_outcome"))
                                if r.get("expected_outcome") is not None
                                else None,
                                json.dumps(r.get("metadata", {})),
                            ],
                        )
                    elif typ == "experiment":
                        if not db.execute(
                            "SELECT 1 FROM workflows WHERE id=?", [r["workflow_id"]]
                        ).fetchone():
                            raise ValueError("workflow_id does not reference an imported workflow")
                        db.execute(
                            "INSERT INTO experiments(id,workflow_id,name,description,dataset_version,evaluator_version) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["workflow_id"],
                                r["name"],
                                r.get("description"),
                                r.get("dataset_version"),
                                r.get("evaluator_version"),
                            ],
                        )
                    elif typ == "baseline_profile":
                        if not db.execute(
                            "SELECT 1 FROM workflows WHERE id=?", [r["workflow_id"]]
                        ).fetchone():
                            raise ValueError("workflow_id does not reference an imported workflow")
                        rate = Decimal(str(r["hourly_rate_usd"]))
                        minutes = Decimal(str(r["typical_minutes"]))
                        other = Decimal(str(r.get("other_costs_usd", 0)))
                        if min(rate, minutes, other) < 0:
                            raise ValueError("baseline profile values must be nonnegative")
                        db.execute(
                            "INSERT INTO baseline_profiles VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["workflow_id"],
                                r["name"],
                                rate,
                                minutes,
                                other,
                                r.get("source"),
                                r.get("confidence"),
                                r.get("notes"),
                                int(r.get("version", 1)),
                            ],
                        )
                    elif typ == "pricing_profile":
                        if r.get("currency", "USD") != "USD":
                            raise ValueError("MVP aggregation supports USD pricing only")
                        prices = [
                            Decimal(str(r[k])) if r.get(k) is not None else None
                            for k in (
                                "input_price_per_million",
                                "output_price_per_million",
                                "cached_input_price_per_million",
                            )
                        ]
                        if any(v is not None and v < 0 for v in prices):
                            raise ValueError("pricing values must be nonnegative")
                        db.execute(
                            "INSERT INTO pricing_profiles VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["provider"],
                                r["model"],
                                datetime.fromisoformat(r["effective_from"])
                                .astimezone(UTC)
                                .replace(tzinfo=None),
                                datetime.fromisoformat(r["effective_until"])
                                .astimezone(UTC)
                                .replace(tzinfo=None)
                                if r.get("effective_until")
                                else None,
                                r.get("currency", "USD"),
                                *prices,
                                r.get("source_type"),
                                r.get("source_reference"),
                                datetime.now(UTC).replace(tzinfo=None),
                            ],
                        )
                    elif typ == "execution":
                        required = [
                            r[k] for k in ("id", "workflow_id", "configuration_id", "task_case_id")
                        ]
                        outcome = r.get("outcome", "unverified")
                        if outcome not in {
                            "unverified",
                            "verified_success",
                            "verified_failure",
                            "indeterminate",
                        }:
                            raise ValueError("invalid outcome")
                        if r.get("runtime_status", "finished") not in {
                            "pending",
                            "running",
                            "finished",
                            "error",
                            "cancelled",
                        }:
                            raise ValueError("invalid runtime_status")
                        if int(r.get("attempts", 1)) < 1:
                            raise ValueError("attempts must be at least one")
                        if not db.execute(
                            "SELECT 1 FROM workflows WHERE id=?", [r["workflow_id"]]
                        ).fetchone():
                            raise ValueError("workflow_id does not reference an imported workflow")
                        if not db.execute(
                            "SELECT 1 FROM configurations WHERE id=? AND workflow_id=?",
                            [r["configuration_id"], r["workflow_id"]],
                        ).fetchone():
                            raise ValueError("configuration_id does not belong to workflow_id")
                        if not db.execute(
                            "SELECT 1 FROM task_cases WHERE id=? AND workflow_id=?",
                            [r["task_case_id"], r["workflow_id"]],
                        ).fetchone():
                            raise ValueError(
                                "task_case_id does not reference an imported task case"
                            )
                        started = r.get("started_at")
                        if started:
                            started = (
                                datetime.fromisoformat(started).astimezone(UTC).replace(tzinfo=None)
                            )
                        baseline = (
                            Decimal(str(r["baseline_cost_usd"]))
                            if r.get("baseline_cost_usd") is not None
                            else None
                        )
                        if baseline is not None and baseline < 0:
                            raise ValueError("baseline cost must be nonnegative")
                        if (
                            r.get("experiment_id")
                            and not db.execute(
                                "SELECT 1 FROM experiments WHERE id=? AND workflow_id=?",
                                [r["experiment_id"], r["workflow_id"]],
                            ).fetchone()
                        ):
                            raise ValueError("experiment_id does not belong to workflow")
                        db.execute(
                            "INSERT INTO executions(id,workflow_id,configuration_id,task_case_id,category,runtime_status,outcome,attempts,fallback_completed,baseline_cost,started_at,external_trace_id,experiment_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            required
                            + [
                                r.get("category"),
                                r.get("runtime_status", "finished"),
                                outcome,
                                int(r.get("attempts", 1)),
                                bool(r.get("fallback_completed", False)),
                                baseline,
                                started,
                                r.get("external_trace_id"),
                                r.get("experiment_id"),
                            ],
                        )
                    elif typ == "attempt":
                        if not db.execute(
                            "SELECT 1 FROM executions WHERE id=?", [r["execution_id"]]
                        ).fetchone():
                            raise ValueError(
                                "execution_id does not reference an imported execution"
                            )
                        number = int(r["attempt_number"])
                        if number < 1:
                            raise ValueError("attempt_number must be positive")
                        start = (
                            datetime.fromisoformat(r["started_at"])
                            .astimezone(UTC)
                            .replace(tzinfo=None)
                            if r.get("started_at")
                            else None
                        )
                        end = (
                            datetime.fromisoformat(r["ended_at"])
                            .astimezone(UTC)
                            .replace(tzinfo=None)
                            if r.get("ended_at")
                            else None
                        )
                        if start and end and end < start:
                            raise ValueError("attempt end precedes start")
                        db.execute(
                            "INSERT INTO attempts VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["execution_id"],
                                number,
                                r.get("status", "finished"),
                                r.get("retry_reason"),
                                start,
                                end,
                            ],
                        )
                    elif typ == "model_call":
                        if not db.execute(
                            "SELECT 1 FROM executions WHERE id=?", [r["execution_id"]]
                        ).fetchone():
                            raise ValueError(
                                "execution_id does not reference an imported execution"
                            )
                        inp, out, cached = (
                            int(r.get("input_tokens", 0)),
                            int(r.get("output_tokens", 0)),
                            int(r.get("cached_tokens", 0)),
                        )
                        if min(inp, out, cached) < 0 or cached > inp:
                            raise ValueError("invalid token counts")
                        reported = (
                            Decimal(str(r["reported_cost_usd"]))
                            if r.get("reported_cost_usd") is not None
                            else None
                        )
                        calculated = (
                            Decimal(str(r["calculated_cost_usd"]))
                            if r.get("calculated_cost_usd") is not None
                            else None
                        )
                        if any(v is not None and v < 0 for v in (reported, calculated)):
                            raise ValueError("model cost must be nonnegative")
                        if (
                            r.get("attempt_id")
                            and not db.execute(
                                "SELECT 1 FROM attempts WHERE id=? AND execution_id=?",
                                [r["attempt_id"], r["execution_id"]],
                            ).fetchone()
                        ):
                            raise ValueError("attempt_id does not belong to execution")
                        pricing_source = r.get("pricing_source")
                        if (
                            calculated is None
                            and reported is None
                            and r.get("provider")
                            and r.get("model")
                        ):
                            execution_time = db.execute(
                                "SELECT started_at FROM executions WHERE id=?", [r["execution_id"]]
                            ).fetchone()[0] or datetime.now(UTC).replace(tzinfo=None)
                            price = db.execute(
                                "SELECT id,input_price_per_million,output_price_per_million,cached_input_price_per_million FROM pricing_profiles WHERE provider=? AND model=? AND currency='USD' AND effective_from<=? AND (effective_until IS NULL OR effective_until>?) ORDER BY effective_from DESC LIMIT 1",
                                [r["provider"], r["model"], execution_time, execution_time],
                            ).fetchone()
                            if price and price[1] is not None and price[2] is not None:
                                calculated = inference_cost(
                                    inp, out, price[1], price[2], cached, price[3]
                                )
                                pricing_source = f"pricing_profile:{price[0]}"
                        db.execute(
                            "INSERT INTO model_calls(id,execution_id,provider,model,input_tokens,output_tokens,cached_tokens,reported_cost,calculated_cost,pricing_source,attempt_id) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["execution_id"],
                                r.get("provider"),
                                r.get("model"),
                                inp,
                                out,
                                cached,
                                reported,
                                calculated,
                                pricing_source,
                                r.get("attempt_id"),
                            ],
                        )
                    elif typ == "tool_call":
                        if not db.execute(
                            "SELECT 1 FROM executions WHERE id=?", [r["execution_id"]]
                        ).fetchone():
                            raise ValueError(
                                "execution_id does not reference an imported execution"
                            )
                        cost = (
                            Decimal(str(r["cost_usd"])) if r.get("cost_usd") is not None else None
                        )
                        if cost is not None and cost < 0:
                            raise ValueError("negative tool cost")
                        if (
                            r.get("attempt_id")
                            and not db.execute(
                                "SELECT 1 FROM attempts WHERE id=? AND execution_id=?",
                                [r["attempt_id"], r["execution_id"]],
                            ).fetchone()
                        ):
                            raise ValueError("attempt_id does not belong to execution")
                        db.execute(
                            "INSERT INTO tool_calls(id,execution_id,name,status,cost,attempt_id) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["execution_id"],
                                r["name"],
                                r.get("status", "success"),
                                cost,
                                r.get("attempt_id"),
                            ],
                        )
                    elif typ == "human_work":
                        if not db.execute(
                            "SELECT 1 FROM executions WHERE id=?", [r["execution_id"]]
                        ).fetchone():
                            raise ValueError(
                                "execution_id does not reference an imported execution"
                            )
                        minutes = Decimal(str(r["minutes"]))
                        rate = Decimal(str(r["hourly_rate_usd"]))
                        if minutes < 0 or rate < 0:
                            raise ValueError("human time and rates must be nonnegative")
                        db.execute(
                            "INSERT INTO human_work VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["execution_id"],
                                r["category"],
                                minutes,
                                rate,
                                human_cost(minutes, rate),
                            ],
                        )
                    elif typ == "outcome_evidence":
                        if not db.execute(
                            "SELECT 1 FROM executions WHERE id=?", [r["execution_id"]]
                        ).fetchone():
                            raise ValueError(
                                "execution_id does not reference an imported execution"
                            )
                        db.execute(
                            "INSERT INTO outcome_evidence VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                            [
                                r["id"],
                                r["execution_id"],
                                r["method"],
                                r["status"],
                                r.get("reference"),
                                datetime.now(UTC).replace(tzinfo=None),
                                r.get("reasoning"),
                            ],
                        )
                    else:
                        raise ValueError(f"unsupported event_type: {typ}")
                    accepted += 1
                except Exception as exc:
                    raise ValueError(f"record {i}: {exc}") from exc
            if dry_run:
                db.execute("ROLLBACK")
                return {
                    "dry_run": True,
                    "valid": True,
                    "rows": len(records),
                    "accepted": accepted,
                    "rejected": 0,
                }
            fmt = (
                "otlp_json"
                if filename == "otlp-json"
                else filename.rsplit(".", 1)[-1].lower()
                if "." in filename
                else "json"
            )
            db.execute(
                "INSERT INTO imports(id,filename,checksum,status,rows_received,rows_accepted,rows_rejected,format,mapping_version) VALUES(?,?,?,?,?,?,?,?,?)",
                [checksum, filename, checksum, "completed", len(records), accepted, 0, fmt, "1.0"],
            )
            db.execute("COMMIT")
        except Exception as exc:
            db.execute("ROLLBACK")
            message = str(exc)[:2000]
            import_id = checksum
            db.execute(
                "INSERT INTO imports(id,filename,checksum,status,rows_received,rows_accepted,rows_rejected,format,mapping_version,error_message) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(checksum) DO UPDATE SET status=excluded.status,error_message=excluded.error_message,rows_received=excluded.rows_received,rows_accepted=0,rows_rejected=excluded.rows_received",
                [
                    import_id,
                    filename,
                    checksum,
                    "failed",
                    len(records),
                    0,
                    len(records),
                    "json",
                    "1.0",
                    message,
                ],
            )
            match = re.search(r"record (\d+):", message)
            db.execute(
                "INSERT INTO import_errors(import_id,row_number,message) VALUES(?,?,?)",
                [import_id, int(match.group(1)) if match else None, message],
            )
            raise
    return {"duplicate": False, "accepted": accepted, "rejected": 0}


@app.post("/api/imports/preview")
@app.post("/api/v1/imports/preview")
async def preview(file: UploadFile = File(...)):  # noqa: B008
    validate_upload(file)
    data = await file.read(10_000_001)
    if len(data) > 10_000_000:
        raise HTTPException(413, "Maximum import size is 10 MB")
    try:
        digest = hashlib.sha256(data).hexdigest()
        if file.filename and file.filename.lower().endswith(".csv"):
            reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
            columns = reader.fieldnames or []
            records = csv_records(data)
            return {
                "format": "csv",
                "rows": len(records),
                "columns": columns,
                "recognized_fields": columns,
                "sample": records[:5],
                "checksum": digest,
                "note": "CSV columns use stable field names. Add record_type for model_call, tool_call, human_work, outcome_evidence, task_case, or execution rows.",
            }
        payload = parse_native(data)
        return {
            "format": "jsonl" if b"\n" in data else "json",
            "schema_version": payload.get("schema_version"),
            "rows": len(payload.get("records", [])),
            "sample": payload.get("records", [])[:5],
            "checksum": digest,
        }
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/imports")
@app.post("/api/v1/imports")
async def import_file(file: UploadFile = File(...), dry_run: bool = False):  # noqa: B008
    validate_upload(file)
    data = await file.read(10_000_001)
    if len(data) > 10_000_000:
        raise HTTPException(413, "Maximum import size is 10 MB")
    digest = hashlib.sha256(data).hexdigest()
    try:
        if file.filename and file.filename.lower().endswith(".csv"):
            records = csv_records(data)
            needs_defaults = any(
                r["event_type"] == "execution"
                and (not r.get("workflow_id") or not r.get("configuration_id"))
                for r in records
            )
            if needs_defaults:
                with connect() as db:
                    config = db.execute(
                        "SELECT id,workflow_id FROM configurations ORDER BY name LIMIT 1"
                    ).fetchone()
                if not config:
                    raise ValueError(
                        "Execution CSV must provide workflow_id and configuration_id, or import a configuration first"
                    )
                records = csv_records(data, config[1], config[0])
            payload = {"schema_version": "1.0", "records": records}
        else:
            payload = parse_native(data)
        if dry_run:
            result = import_records(payload, file.filename or "upload", digest, dry_run=True)
            result["checksum"] = digest
            return result
        return import_records(payload, file.filename or "upload", digest)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as e:
        raise HTTPException(400, str(e))


@app.get("/api/reports/workflow.json")
def report(workflow_id: str):
    data = dashboard(workflow_id)
    return {
        "report_type": "workflow_economics",
        "generated_at": datetime.now(UTC).isoformat(),
        "application_version": "0.1.0",
        "currency": "USD",
        "dataset_checksums": [
            x["checksum"]
            for x in rows("SELECT checksum FROM imports WHERE status='completed' ORDER BY checksum")
        ],
        "baseline_versions": rows(
            "SELECT id,version FROM baseline_profiles WHERE workflow_id=? ORDER BY version",
            [workflow_id],
        ),
        "pricing_versions": rows(
            "SELECT id,provider,model,effective_from FROM pricing_profiles ORDER BY provider,model,effective_from"
        ),
        "verification_rule_versions": [
            x["evaluator_version"]
            for x in rows(
                "SELECT DISTINCT evaluator_version FROM experiments WHERE workflow_id=? AND evaluator_version IS NOT NULL ORDER BY evaluator_version",
                [workflow_id],
            )
        ],
        "data": data,
        "methodology": "Total attributed cost includes every attempt, tool charge, review, correction and recorded fallback. Cost per verified success divides cohort cost by verified successes; unresolved tasks are excluded from resolved-cohort savings.",
    }


@app.get("/api/reports/comparison.json")
def comparison_report(workflow_id: str, a: str, b: str):
    return {
        "report_type": "configuration_comparison",
        "generated_at": datetime.now(UTC).isoformat(),
        "application_version": "0.1.0",
        "comparison": compare(workflow_id, a, b),
        "interpretation": "Descriptive paired comparison by task-case ID. No universal winner or statistical significance is implied.",
    }


@app.get("/api/reports/workflow.html")
def report_html(workflow_id: str):
    from html import escape

    from fastapi.responses import HTMLResponse

    data = report(workflow_id)
    metrics = data["data"]["metrics"]
    fields = (
        ("Executions", metrics["executions"]),
        ("Verified successes", metrics["verified_successes"]),
        ("Verified failures", metrics["verified_failures"]),
        ("Cost per verified success", metrics["cost_per_verified_success"]),
        ("Total attributed cost", metrics["total_cost"]),
        ("Resolved-cohort net savings", metrics["net_savings_resolved"]),
        ("Unresolved excluded", metrics["excluded_unresolved"]),
    )
    body = "".join(
        f"<tr><th>{escape(str(label))}</th><td>{escape(str(value if value is not None else 'N/A'))}</td></tr>"
        for label, value in fields
    )
    warnings = "".join(f"<li>{escape(w)}</li>" for w in data["data"]["data_quality"]["warnings"])
    document = f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>AI Workflow Cost Analyzer workflow report</title><style>body{{font:15px system-ui;max-width:850px;margin:40px auto;padding:0 20px;color:#1d2923}}h1{{font-size:25px}}table{{width:100%;border-collapse:collapse;margin:24px 0}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #ddd}}td{{font-variant-numeric:tabular-nums}}.print{{float:right}}@media print{{.print{{display:none}}}}</style><button class='print' onclick='window.print()'>Print / Save PDF</button><h1>AI Workflow Cost Analyzer · Workflow economics</h1><p>Workflow {escape(workflow_id)} · generated {escape(data['generated_at'])} · USD</p><table>{body}</table><h2>Data quality and warnings</h2><ul>{warnings or '<li>No warnings reported.</li>'}</ul><p>Dataset checksums: {escape(', '.join(data['dataset_checksums']))}</p><p>Interpret results with recorded baselines, pricing versions and verification evidence. Synthetic rows are not business evidence.</p></html>"
    return HTMLResponse(document)


@app.get("/api/imports")
@app.get("/api/v1/imports")
def import_history(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    total = rows("SELECT COUNT(*) total FROM imports")[0]["total"]
    return {
        "items": rows(
            "SELECT * FROM imports ORDER BY imported_at DESC LIMIT ? OFFSET ?", [limit, offset]
        ),
        "total": total,
    }


@app.get("/api/reports/workflow.csv")
def report_csv(workflow_id: str):
    from fastapi.responses import Response

    data = execution_rows("WHERE e.workflow_id=?", [workflow_id])
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "task_case_id",
            "configuration",
            "runtime_status",
            "outcome",
            "attempts",
            "inference_cost",
            "tool_cost",
            "human_cost",
            "fallback_cost",
            "total_cost",
        ],
    )
    writer.writeheader()
    for item in data:
        writer.writerow({k: item.get(k) for k in writer.fieldnames})
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=outcomemeter-workflow.csv"},
    )
