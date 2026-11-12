"""Adapter for a documented OTLP/JSON trace subset; outcomes are never inferred."""

from datetime import UTC, datetime

GEN_AI_KEYS = {
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cached_input_tokens",
    "gen_ai.provider.name",
    "gen_ai.system",
    "gen_ai.tool.name",
    "gen_ai.tool.call.id",
    "outcomemeter.execution_id",
    "outcomemeter.task_case_id",
    "outcomemeter.category",
    "outcomemeter.cost_usd",
}


def _value(value):
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in value:
            return value[key]
    return None


def _time(nanos):
    if not nanos:
        return None
    return datetime.fromtimestamp(int(nanos) / 1_000_000_000, UTC).isoformat()


def adapt_otlp(payload, workflow_id, configuration_id, task_case_id_by_trace):
    """Return native events, mapping warnings, and unsupported span count."""
    if not isinstance(payload, dict) or not isinstance(payload.get("resourceSpans"), list):
        raise ValueError("Expected OTLP/JSON object with resourceSpans array")  # noqa: TRY004
    grouped = {}
    unsupported = 0
    for resource_group in payload["resourceSpans"]:
        resource_attrs = {
            a.get("key"): _value(a.get("value"))
            for a in resource_group.get("resource", {}).get("attributes", [])
        }
        for scope_group in resource_group.get(
            "scopeSpans", resource_group.get("instrumentationLibrarySpans", [])
        ):
            for span in scope_group.get("spans", []):
                attrs = dict(resource_attrs)
                attrs.update(
                    {a.get("key"): _value(a.get("value")) for a in span.get("attributes", [])}
                )
                operation = attrs.get("gen_ai.operation.name")
                model = attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model")
                tool = attrs.get("gen_ai.tool.name")
                if not operation and not model and not tool:
                    unsupported += 1
                    continue
                trace_id = span.get("traceId")
                span_id = span.get("spanId")
                if not trace_id or not span_id:
                    unsupported += 1
                    continue
                item = grouped.setdefault(trace_id, {"spans": [], "attrs": attrs})
                item["spans"].append((span, attrs, operation, model, tool))
    records = []
    warnings = []
    mapped = 0
    for trace_id, item in grouped.items():
        case_id = task_case_id_by_trace.get(trace_id)
        if not case_id:
            warnings.append(f"Trace {trace_id} has no task-case mapping and was skipped")
            continue
        spans = item["spans"]
        eid = "otel-" + trace_id
        first = min((s.get("startTimeUnixNano", "0") for s, *_ in spans), key=lambda x: int(x or 0))
        has_error = any(
            str(s.get("status", {}).get("code", "")).upper() in {"2", "ERROR"} for s, *_ in spans
        )
        records.append(
            {
                "event_type": "execution",
                "id": eid,
                "workflow_id": workflow_id,
                "configuration_id": configuration_id,
                "task_case_id": case_id,
                "category": item["attrs"].get("outcomemeter.category"),
                "runtime_status": "error" if has_error else "finished",
                "outcome": "unverified",
                "attempts": 1,
                "external_trace_id": trace_id,
                "started_at": _time(first),
            }
        )
        for span, attrs, operation, model, tool in spans:
            sid = span["spanId"]
            if model or operation:
                records.append(
                    {
                        "event_type": "model_call",
                        "id": f"otel-{trace_id}-{sid}",
                        "execution_id": eid,
                        "provider": attrs.get("gen_ai.provider.name") or attrs.get("gen_ai.system"),
                        "model": model,
                        "input_tokens": int(attrs.get("gen_ai.usage.input_tokens", 0) or 0),
                        "output_tokens": int(attrs.get("gen_ai.usage.output_tokens", 0) or 0),
                        "cached_tokens": int(attrs.get("gen_ai.usage.cached_input_tokens", 0) or 0),
                        "started_at": _time(span.get("startTimeUnixNano")),
                        "ended_at": _time(span.get("endTimeUnixNano")),
                        "pricing_source": "unknown",
                    }
                )
            elif tool:
                record = {
                    "event_type": "tool_call",
                    "id": f"otel-{trace_id}-{sid}",
                    "execution_id": eid,
                    "name": tool,
                    "status": "error"
                    if str(span.get("status", {}).get("code", "")).upper() in {"2", "ERROR"}
                    else "success",
                }
                if attrs.get("outcomemeter.cost_usd") is not None:
                    record["cost_usd"] = str(attrs["outcomemeter.cost_usd"])
                records.append(record)
        mapped += 1
    if unsupported:
        warnings.append(f"{unsupported} span(s) were unsupported or lacked trace/span identifiers")
    warnings.append(
        "OTel telemetry does not verify business outcomes; imported executions remain unverified"
    )
    return {"schema_version": "1.0", "records": records}, {
        "mapped_traces": mapped,
        "skipped_spans": unsupported,
        "warnings": warnings,
    }
