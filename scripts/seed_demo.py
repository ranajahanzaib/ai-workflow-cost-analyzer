"""Create deterministic synthetic customer-support and invoice examples."""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rng = random.Random(481516)
categories = [
    "Billing",
    "Refund",
    "Account Access",
    "Product Support",
    "Shipping",
    "General Inquiry",
]
routing = {
    "Billing": "billing-team",
    "Refund": "refunds-team",
    "Account Access": "identity-team",
    "Product Support": "product-team",
    "Shipping": "fulfillment-team",
    "General Inquiry": "support-team",
}
records = [
    {
        "event_type": "project",
        "id": "proj-support",
        "name": "Support Operations",
        "description": "Synthetic customer support routing economics",
    },
    {
        "event_type": "workflow",
        "id": "wf-routing",
        "project_id": "proj-support",
        "name": "Ticket classification and routing",
        "description": "Classify customer tickets and route them to the correct team.",
        "task_type": "support_triage",
        "baseline_hourly_rate": "30",
        "baseline_minutes": "8",
    },
    {
        "event_type": "experiment",
        "id": "exp-support-v1",
        "workflow_id": "wf-routing",
        "name": "Routing model evaluation",
        "description": "Paired synthetic tasks across two configurations.",
        "dataset_version": "support-synth-v1",
        "evaluator_version": "rules-v1",
    },
    {
        "event_type": "configuration",
        "id": "cfg-compact",
        "workflow_id": "wf-routing",
        "name": "Small Model — Low Token Cost",
        "model": "illustrative-small-v1",
    },
    {
        "event_type": "configuration",
        "id": "cfg-accurate",
        "workflow_id": "wf-routing",
        "name": "Premium Model — Higher Accuracy",
        "model": "illustrative-premium-v1",
    },
    {
        "event_type": "baseline_profile",
        "id": "base-support-v1",
        "workflow_id": "wf-routing",
        "name": "Human support agent",
        "hourly_rate_usd": "30",
        "typical_minutes": "8",
        "other_costs_usd": "0",
        "source": "synthetic_demo_assumption",
        "confidence": "illustrative",
        "notes": "Fictional labor assumption, not measured payroll.",
    },
    {
        "event_type": "pricing_profile",
        "id": "price-small-v1",
        "provider": "synthetic",
        "model": "illustrative-small-v1",
        "effective_from": "2026-01-01T00:00:00Z",
        "currency": "USD",
        "input_price_per_million": "0.50",
        "output_price_per_million": "1.00",
        "cached_input_price_per_million": "0.10",
        "source_type": "synthetic_demo_assumption",
        "source_reference": "Fictional example rates; not provider pricing.",
    },
    {
        "event_type": "pricing_profile",
        "id": "price-premium-v1",
        "provider": "synthetic",
        "model": "illustrative-premium-v1",
        "effective_from": "2026-01-01T00:00:00Z",
        "currency": "USD",
        "input_price_per_million": "2.50",
        "output_price_per_million": "8.00",
        "cached_input_price_per_million": "0.50",
        "source_type": "synthetic_demo_assumption",
        "source_reference": "Fictional example rates; not provider pricing.",
    },
]
for i in range(120):
    case_id = f"ticket-{i + 1:03}"
    category = categories[i % len(categories)]
    records.append(
        {
            "event_type": "task_case",
            "id": case_id,
            "workflow_id": "wf-routing",
            "external_case_id": f"SYN-{i + 1:03}",
            "category": category,
            "difficulty": ["easy", "medium", "hard"][i % 3],
            "description": f"Synthetic {category.lower()} inquiry {i + 1}; no customer text or real personal data.",
            "baseline_cost_usd": "4.00",
            "baseline_minutes": "8",
            "expected_outcome": {"category": category, "destination": routing[category]},
            "metadata": {"synthetic": True, "dataset_version": "support-synth-v1"},
        }
    )
    for config_id, small in (("cfg-compact", True), ("cfg-accurate", False)):
        execution_id = f"{config_id}-{case_id}"
        success = rng.random() < (0.72 if small else 0.93)
        attempts = 1 if rng.random() < (0.62 if small else 0.90) else 2
        outcome = "verified_success" if success else "verified_failure"
        fallback = not success and i % 5 != 0
        if i == 119 and small:
            outcome = "unverified"
            fallback = False
        records.append(
            {
                "event_type": "execution",
                "id": execution_id,
                "workflow_id": "wf-routing",
                "configuration_id": config_id,
                "experiment_id": "exp-support-v1",
                "task_case_id": case_id,
                "category": category,
                "runtime_status": "finished",
                "outcome": outcome,
                "attempts": attempts,
                "fallback_completed": fallback,
                "baseline_cost_usd": "4.00",
                "started_at": f"2026-10-{(i % 28) + 1:02}T12:00:00Z",
            }
        )
        for attempt_no in range(1, attempts + 1):
            attempt_id = f"attempt-{execution_id}-{attempt_no}"
            records.append(
                {
                    "event_type": "attempt",
                    "id": attempt_id,
                    "execution_id": execution_id,
                    "attempt_number": attempt_no,
                    "status": "error" if attempt_no < attempts else "finished",
                    "retry_reason": "invalid category on first pass"
                    if attempt_no < attempts
                    else None,
                }
            )
            amount = (0.0038 if small else 0.0125) * (1.15 if attempt_no > 1 else 1)
            model_event = {
                "event_type": "model_call",
                "id": f"call-{execution_id}-{attempt_no}",
                "execution_id": execution_id,
                "attempt_id": attempt_id,
                "provider": "unlisted-demo-provider" if i == 17 and not small else "synthetic",
                "model": "illustrative-small-v1" if small else "illustrative-premium-v1",
                "input_tokens": 3200 if small else 4200,
                "output_tokens": 420 if small else 510,
                "cached_tokens": 200 if attempt_no > 1 else 0,
                "pricing_source": "synthetic_demo_assumption",
            }
            if not (i == 17 and not small):
                model_event["reported_cost_usd"] = f"{amount:.6f}"
            records.append(model_event)
            if i % 10 == 0 and attempt_no == 1:
                tool = {
                    "event_type": "tool_call",
                    "id": f"tool-{execution_id}",
                    "execution_id": execution_id,
                    "attempt_id": attempt_id,
                    "name": "ticket_lookup",
                    "status": "success",
                }
                if i != 30:
                    tool["cost_usd"] = "0.0015"
                records.append(tool)
        if not small and i % 3 != 1:
            records.append(
                {
                    "event_type": "human_work",
                    "id": f"review-{execution_id}",
                    "execution_id": execution_id,
                    "category": "review",
                    "minutes": "0.6",
                    "hourly_rate_usd": "30",
                }
            )
        if small and i in (9, 21):
            records.append(
                {
                    "event_type": "human_work",
                    "id": f"correction-{execution_id}",
                    "execution_id": execution_id,
                    "category": "correction",
                    "minutes": "3",
                    "hourly_rate_usd": "30",
                }
            )
        if fallback:
            records.append(
                {
                    "event_type": "human_work",
                    "id": f"fallback-{execution_id}",
                    "execution_id": execution_id,
                    "category": "fallback_completion",
                    "minutes": "4",
                    "hourly_rate_usd": "30",
                }
            )
        records.append(
            {
                "event_type": "outcome_evidence",
                "id": f"evidence-{execution_id}",
                "execution_id": execution_id,
                "method": "synthetic_rule",
                "status": outcome,
                "reference": case_id,
                "reasoning": "Synthetic evaluator fixture; not real business evidence.",
            }
        )
        if i == 50 and not small:
            records.append(
                {
                    "event_type": "outcome_evidence",
                    "id": f"conflict-{execution_id}",
                    "execution_id": execution_id,
                    "method": "manual_attestation",
                    "status": "verified_failure",
                    "reference": case_id,
                    "reasoning": "Contradictory synthetic evidence fixture.",
                }
            )
ROOT.joinpath("examples/support-triage").mkdir(parents=True, exist_ok=True)
ROOT.joinpath("examples/support-triage/demo.json").write_text(
    json.dumps({"schema_version": "1.0", "records": records}, indent=2) + "\n"
)
print(f"Wrote {len(records)} synthetic support records (120 paired cases).")

invoice_records = [
    {
        "event_type": "project",
        "id": "proj-invoice",
        "name": "Invoice Operations",
        "description": "Synthetic invoice extraction economics",
    },
    {
        "event_type": "workflow",
        "id": "wf-invoice",
        "project_id": "proj-invoice",
        "name": "Invoice extraction and validation",
        "task_type": "invoice_processing",
        "baseline_hourly_rate": "32",
        "baseline_minutes": "6",
    },
    {
        "event_type": "configuration",
        "id": "cfg-invoice",
        "workflow_id": "wf-invoice",
        "name": "Invoice extractor + field validation",
        "model": "illustrative-invoice-v1",
    },
]
for i in range(6):
    case = f"invoice-{i + 1:03}"
    execution = f"invoice-run-{i + 1:03}"
    invoice_records.append(
        {
            "event_type": "task_case",
            "id": case,
            "workflow_id": "wf-invoice",
            "category": "invoice_processing",
            "difficulty": ["easy", "medium", "hard"][i % 3],
            "description": f"Synthetic invoice {case}; line-item total ${125 + i * 37}.50.",
            "baseline_cost_usd": "3.20",
            "baseline_minutes": "6",
            "expected_outcome": {
                "invoice_total": f"{125 + i * 37}.50",
                "currency": "USD",
                "vendor_id": f"V-{i + 10:03}",
            },
            "metadata": {"synthetic": True},
        }
    )
    invoice_records += [
        {
            "event_type": "execution",
            "id": execution,
            "workflow_id": "wf-invoice",
            "configuration_id": "cfg-invoice",
            "task_case_id": case,
            "category": "invoice_processing",
            "runtime_status": "finished",
            "outcome": "verified_failure" if i == 2 else "verified_success",
            "attempts": 1,
            "fallback_completed": i == 2,
            "baseline_cost_usd": "3.20",
            "started_at": f"2026-10-{i + 1:02}T09:00:00Z",
        },
        {
            "event_type": "model_call",
            "id": f"invoice-call-{i + 1:03}",
            "execution_id": execution,
            "provider": "synthetic",
            "model": "illustrative-invoice-v1",
            "input_tokens": 2200,
            "output_tokens": 500,
            "reported_cost_usd": "0.006500",
            "pricing_source": "synthetic_demo_assumption",
        },
        {
            "event_type": "outcome_evidence",
            "id": f"invoice-evidence-{i + 1:03}",
            "execution_id": execution,
            "method": "expected_output_match",
            "status": "verified_failure" if i == 2 else "verified_success",
            "reference": case,
            "reasoning": "Synthetic invoice field and total validation.",
        },
    ]
    if i == 2:
        invoice_records.append(
            {
                "event_type": "human_work",
                "id": f"invoice-fallback-{i + 1:03}",
                "execution_id": execution,
                "category": "fallback_completion",
                "minutes": "5",
                "hourly_rate_usd": "32",
            }
        )
ROOT.joinpath("examples/invoice-processing").mkdir(parents=True, exist_ok=True)
ROOT.joinpath("examples/invoice-processing/demo.json").write_text(
    json.dumps({"schema_version": "1.0", "records": invoice_records}, indent=2) + "\n"
)
print(f"Wrote {len(invoice_records)} synthetic invoice records.")
