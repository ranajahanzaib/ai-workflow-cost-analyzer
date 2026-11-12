"""Single-process DuckDB repository. Callers serialize writes with the lock."""

import os
import threading
from pathlib import Path

import duckdb

DB_PATH = Path(
    os.environ.get("AI_WORKFLOW_COST_ANALYZER_DB", "./data/ai-workflow-cost-analyzer.duckdb")
)
WRITE_LOCK = threading.RLock()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def initialize():
    with WRITE_LOCK, connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS projects(id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, description VARCHAR)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS workflows(id VARCHAR PRIMARY KEY, project_id VARCHAR NOT NULL, name VARCHAR NOT NULL, task_type VARCHAR, baseline_profile_id VARCHAR, baseline_hourly_rate DECIMAL(20,8) DEFAULT 24, baseline_minutes DECIMAL(20,8) DEFAULT 12)"""
        )
        db.execute("ALTER TABLE workflows ADD COLUMN IF NOT EXISTS description VARCHAR")
        db.execute(
            """CREATE TABLE IF NOT EXISTS configurations(id VARCHAR PRIMARY KEY, workflow_id VARCHAR NOT NULL, name VARCHAR NOT NULL, model VARCHAR NOT NULL)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS task_cases(id VARCHAR PRIMARY KEY, workflow_id VARCHAR NOT NULL, external_case_id VARCHAR, category VARCHAR, difficulty VARCHAR, description VARCHAR, baseline_cost DECIMAL(20,8), baseline_minutes DECIMAL(20,8), expected_outcome JSON, metadata JSON)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS attempts(id VARCHAR PRIMARY KEY, execution_id VARCHAR NOT NULL, attempt_number INTEGER NOT NULL, status VARCHAR NOT NULL, retry_reason VARCHAR, started_at TIMESTAMP, ended_at TIMESTAMP)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS experiments(id VARCHAR PRIMARY KEY, workflow_id VARCHAR NOT NULL, name VARCHAR NOT NULL, description VARCHAR, dataset_version VARCHAR, evaluator_version VARCHAR, created_at TIMESTAMP DEFAULT current_timestamp)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS baseline_profiles(id VARCHAR PRIMARY KEY, workflow_id VARCHAR NOT NULL, name VARCHAR NOT NULL, hourly_rate DECIMAL(20,8) NOT NULL, typical_minutes DECIMAL(20,8) NOT NULL, other_costs DECIMAL(20,8) DEFAULT 0, source VARCHAR, confidence VARCHAR, notes VARCHAR, version INTEGER DEFAULT 1)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS pricing_profiles(id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, model VARCHAR NOT NULL, effective_from TIMESTAMP NOT NULL, effective_until TIMESTAMP, currency VARCHAR NOT NULL DEFAULT 'USD', input_price_per_million DECIMAL(20,8), output_price_per_million DECIMAL(20,8), cached_input_price_per_million DECIMAL(20,8), source_type VARCHAR, source_reference VARCHAR, created_at TIMESTAMP DEFAULT current_timestamp)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS executions(id VARCHAR PRIMARY KEY, workflow_id VARCHAR NOT NULL, configuration_id VARCHAR NOT NULL, task_case_id VARCHAR NOT NULL, category VARCHAR, runtime_status VARCHAR NOT NULL, outcome VARCHAR NOT NULL, attempts INTEGER NOT NULL, fallback_completed BOOLEAN DEFAULT FALSE, baseline_cost DECIMAL(20,8), started_at TIMESTAMP, external_trace_id VARCHAR, experiment_id VARCHAR)"""
        )
        db.execute("ALTER TABLE executions ADD COLUMN IF NOT EXISTS experiment_id VARCHAR")
        db.execute(
            """CREATE TABLE IF NOT EXISTS model_calls(id VARCHAR PRIMARY KEY, execution_id VARCHAR NOT NULL, provider VARCHAR, model VARCHAR, input_tokens BIGINT, output_tokens BIGINT, cached_tokens BIGINT DEFAULT 0, reported_cost DECIMAL(20,8), calculated_cost DECIMAL(20,8), pricing_source VARCHAR, attempt_id VARCHAR)"""
        )
        db.execute("ALTER TABLE model_calls ADD COLUMN IF NOT EXISTS attempt_id VARCHAR")
        db.execute(
            """CREATE TABLE IF NOT EXISTS tool_calls(id VARCHAR PRIMARY KEY, execution_id VARCHAR NOT NULL, name VARCHAR, status VARCHAR, cost DECIMAL(20,8), attempt_id VARCHAR)"""
        )
        db.execute("ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS attempt_id VARCHAR")
        db.execute(
            """CREATE TABLE IF NOT EXISTS human_work(id VARCHAR PRIMARY KEY, execution_id VARCHAR NOT NULL, category VARCHAR, minutes DECIMAL(20,8), hourly_rate DECIMAL(20,8), cost DECIMAL(20,8))"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS outcome_evidence(id VARCHAR PRIMARY KEY, execution_id VARCHAR NOT NULL, method VARCHAR, status VARCHAR, reference VARCHAR, verified_at TIMESTAMP, reasoning VARCHAR)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS imports(id VARCHAR PRIMARY KEY, filename VARCHAR, checksum VARCHAR UNIQUE, status VARCHAR, rows_received INTEGER, rows_accepted INTEGER, rows_rejected INTEGER, imported_at TIMESTAMP DEFAULT current_timestamp)"""
        )
        db.execute("ALTER TABLE imports ADD COLUMN IF NOT EXISTS format VARCHAR")
        db.execute("ALTER TABLE imports ADD COLUMN IF NOT EXISTS mapping_version VARCHAR")
        db.execute("ALTER TABLE imports ADD COLUMN IF NOT EXISTS error_message VARCHAR")
        db.execute(
            """CREATE TABLE IF NOT EXISTS import_errors(import_id VARCHAR NOT NULL, row_number INTEGER, message VARCHAR NOT NULL, created_at TIMESTAMP DEFAULT current_timestamp)"""
        )
        db.execute("CREATE INDEX IF NOT EXISTS executions_workflow_idx ON executions(workflow_id)")
        db.execute("CREATE INDEX IF NOT EXISTS calls_execution_idx ON model_calls(execution_id)")


def execute(sql, params=None):
    with connect() as db:
        return db.execute(sql, params or [])
