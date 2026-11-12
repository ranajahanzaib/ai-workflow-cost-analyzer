from outcomemeter.otel import adapt_otlp


def test_otlp_adapter_maps_trace_and_never_fabricates_outcome():
    trace = "ab" * 16
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace,
                                "spanId": "01",
                                "startTimeUnixNano": "1790000000000000000",
                                "endTimeUnixNano": "1790000001000000000",
                                "status": {"code": 1},
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "chat"},
                                    },
                                    {
                                        "key": "gen_ai.request.model",
                                        "value": {"stringValue": "model-x"},
                                    },
                                    {
                                        "key": "gen_ai.usage.input_tokens",
                                        "value": {"intValue": "42"},
                                    },
                                    {
                                        "key": "gen_ai.usage.output_tokens",
                                        "value": {"intValue": "9"},
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    native, summary = adapt_otlp(payload, "wf", "cfg", {trace: "case-1"})
    execution = next(r for r in native["records"] if r["event_type"] == "execution")
    call = next(r for r in native["records"] if r["event_type"] == "model_call")
    assert execution["outcome"] == "unverified"
    assert execution["task_case_id"] == "case-1"
    assert call["input_tokens"] == 42 and call["model"] == "model-x"
    assert summary["mapped_traces"] == 1
    assert any("does not verify" in warning for warning in summary["warnings"])


def test_otlp_without_case_mapping_is_reported_and_skipped():
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "ab",
                                "spanId": "01",
                                "attributes": [
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "m"}}
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    native, summary = adapt_otlp(payload, "wf", "cfg", {})
    assert native["records"] == []
    assert summary["mapped_traces"] == 0
    assert any("no task-case mapping" in warning for warning in summary["warnings"])
