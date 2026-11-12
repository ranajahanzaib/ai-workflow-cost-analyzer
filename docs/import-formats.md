# Import formats

## Native JSON and JSONL

The stable envelope is UTF-8 JSON with `schema_version: "1.0"` and a `records` array. JSONL accepts one event object per line. Event IDs are stable strings and are primary keys. Completed identical files are deduplicated by SHA-256 checksum; stable event IDs also prevent duplicate rows across files. Every event is validated inside one transaction. On failure, writes roll back and the import receipt stores an error and record number where available.

Supported `event_type` values:

| Event              | Required references / fields                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| `project`          | `id`, `name`                                                                                                 |
| `workflow`         | `id`, `project_id`, `name`; optional baseline assumptions                                                    |
| `configuration`    | `id`, `workflow_id`, `name`, `model`                                                                         |
| `task_case`        | `id`, `workflow_id`; optional category, expected outcome, metadata, and per-case baseline                    |
| `experiment`       | `id`, `workflow_id`, `name`; optional dataset/evaluator versions                                             |
| `baseline_profile` | `id`, `workflow_id`, `name`, `hourly_rate_usd`, `typical_minutes`                                            |
| `pricing_profile`  | `id`, `provider`, `model`, `effective_from`, input/output prices per million, optional cache price; USD only |
| `execution`        | `id`, `workflow_id`, `configuration_id`, `task_case_id`; explicit runtime and outcome status                 |
| `attempt`          | `id`, `execution_id`, positive `attempt_number`, status                                                      |
| `model_call`       | `id`, `execution_id`, token usage and/or reported/calculated USD cost; optional `attempt_id`                 |
| `tool_call`        | `id`, `execution_id`, `name`; optional cost; optional `attempt_id`                                           |
| `human_work`       | `id`, `execution_id`, category, minutes, `hourly_rate_usd`                                                   |
| `outcome_evidence` | `id`, `execution_id`, method and status; optional reference and reasoning                                    |

Order parent records before children in a file. A task case must exist before its execution. Costs and durations must be nonnegative. Execution runtime statuses are `pending`, `running`, `finished`, `error`, or `cancelled`; business outcomes are `unverified`, `verified_success`, `verified_failure`, or `indeterminate`. Runtime completion never sets outcome success.

Monetary inputs use explicit USD field names. Provider-reported and calculated model costs are stored separately; a reported charge takes precedence for attribution. If a call has neither cost and an effective-dated pricing profile matches provider/model/time, cost is calculated from usage and the profile ID is retained. Otherwise the call appears as unpriced.

## CSV

CSV is UTF-8 with a header row. Use `record_type` for mixed event types. If omitted, rows are interpreted as `execution` records. Field names below map directly to the native event fields:

- `execution`: `execution_id`, `task_case_id`, `workflow_id`, `configuration_id`, `category`, `runtime_status`, `outcome`, `attempts`, `baseline_cost_usd`, `started_at`, `fallback_completed`. Workflow/configuration may use the first existing configuration as defaults, but a matching task case is still required.
- `model_call`: `event_id`, `execution_id`, optional `attempt_id`, provider/model, token counts, `reported_cost_usd`, `calculated_cost_usd`, pricing source.
- `tool_call`: `event_id`, `execution_id`, optional `attempt_id`, name, status, optional `cost_usd`.
- `human_work`: `event_id`, `execution_id`, category, minutes, `hourly_rate_usd`.
- `outcome_evidence`: `event_id`, `execution_id`, method, status, reference, reasoning.
- `task_case`: `case_id`, `workflow_id`, optional metadata, `expected_outcome_json`, `metadata_json`.
- `baseline_profile`: `event_id`, `workflow_id`, name, `hourly_rate_usd`, `typical_minutes`, optional other costs/source/confidence/notes.
- `pricing_profile`: `event_id`, provider/model/effective dates/currency, prices per million, optional source fields.

The upload screen previews columns and sample rows. Dry run executes the full relationship and value validation in a rolled-back transaction. Validation failures include CSV row numbers. Templates are under `examples/templates/`.

## OTLP/JSON

AI Workflow Cost Analyzer accepts a documented OTLP/JSON trace subset through `/api/v1/imports/otel/preview` and `/api/v1/imports/otel`. The request includes the document, workflow ID, configuration ID, and `task_case_id_by_trace` mapping. Unmapped traces are skipped in preview and rejected for import. See [OTLP compatibility](otel-compatibility.md).

## Safety and limits

Uploads are limited to 10 MB and 50,000 records/spans. Supported file extensions are `.json`, `.jsonl`, `.ndjson`, and `.csv`; upload MIME type is checked. Imported content is never executed, raw prompt/completion bodies are not required, and no arbitrary URL is fetched. Error messages retain validation context but not whole upload bodies.
