# Data model

## Core entities

- **Project** groups workflows.
- **Workflow** defines a business task family and default baseline assumptions.
- **Configuration** names a workflow implementation/model setup.
- **Task case** is the stable business input/case used to match runs across configurations.
- **Experiment** can label a dataset/evaluator comparison set.
- **Execution** is one configuration run on a task case. Runtime state and business outcome are separate fields.
- **Attempt** represents a logical retry. Model and tool calls may link to an attempt and always link to an execution.
- **Model call / tool call / human work** are cost-bearing records attached to executions.
- **Outcome evidence** stores the basis for a label. Evidence import does not itself certify the execution.
- **Baseline profile / pricing profile** are versioned assumptions. Pricing profiles use provider/model and effective dates.
- **Import receipt / import error** records checksum, status, accepted/rejected counts, and validation errors.

IDs are stable strings and primary keys. Imports require referenced parents to exist and validate workflow ownership. Files are applied transactionally; a rejected file cannot leave a partial dataset. A successful exact-file repeat is skipped by checksum, and stable event IDs prevent duplicate records across different files.

## Storage and attribution

DuckDB is used as a local analytical store by one backend process. Application writes are serialized. Do not point multiple API workers at the same database file. Cost columns use `DECIMAL(20,8)` and the economics layer uses Python `Decimal`.

Provider-reported and profile-calculated model charges are retained separately. Reported cost is selected for attribution when available; otherwise calculated cost is selected. Missing both is unknown, not zero, and warnings/coverage expose it. Tool cost can also be absent. Human-work cost is minutes × recorded hourly rate ÷ 60. Runtime retries are drilldown information; the underlying model/tool events are already included in cost.

All aggregation is USD. Foreign currency records are not converted. See [economics methodology](economics-methodology.md) for the exact denominators and unresolved/missing-baseline behavior.
