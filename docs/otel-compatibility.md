# OTLP/JSON compatibility

AI Workflow Cost Analyzer imports a deliberately small subset of the OpenTelemetry Protocol JSON trace export shape. This is an adapter for cost analysis, not a general OTLP collector. It accepts `resourceSpans` with `scopeSpans` (or the older `instrumentationLibrarySpans`) and spans with string, boolean, integer, or double attributes.

## Mapping

Each supported span becomes one normalized call event. Resource and span attributes are combined, with span attributes taking precedence. The adapter recognizes:

| AI Workflow Cost Analyzer field | Recognized attribute keys                                           |
| ------------------------------- | ------------------------------------------------------------------- |
| model call                      | A model identifier or `gen_ai.operation.name` is present            |
| tool call                       | `gen_ai.tool.name` is present and no model/operation was recognized |
| provider                        | `gen_ai.provider.name`, then `gen_ai.system`                        |
| model                           | `gen_ai.request.model`, then `gen_ai.response.model`                |
| input tokens                    | `gen_ai.usage.input_tokens`, `gen_ai.usage.prompt_tokens`           |
| output tokens                   | `gen_ai.usage.output_tokens`, `gen_ai.usage.completion_tokens`      |
| tool name                       | `gen_ai.tool.name`                                                  |
| reported cost                   | `outcomemeter.cost_usd`                                             |

Span ID and trace ID form stable event identifiers. Start time is used for pricing lookup; start/end timestamps are carried into normalized model-call records. An error status marks the execution as errored and tool call as failed. Parent span IDs are not currently retained. Token usage is priced using the AI Workflow Cost Analyzer profile effective at the span start time. Raw prompt and completion bodies are ignored.

## Import procedure

Send the document with `workflow_id`, `configuration_id`, and a `task_case_id_by_trace` mapping from each trace ID to an existing task case in that workflow. Preview and import routes are documented in the API schema. Unmapped traces are rejected for commit. A mapped trace creates an execution with outcome `unverified`; runtime span status is not business outcome evidence. Verification must be recorded separately.

## Limits and unsupported data

Imports are limited to 10 MB and 50,000 spans. This adapter does not claim full semantic-convention version coverage, metrics/log ingestion, OTLP protobuf, baggage propagation, events/links, histogram usage, framework-specific span parsing, or nested parent/child cost attribution. It does not infer task success or deduplicate calls based on model response content. Review the normalized preview before import and consult the `OTLP/JSON` section in [import formats](import-formats.md).
