"""Exact, independently testable economics calculations."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

D = Decimal
ZERO = D(0)
MILLION = D(1_000_000)
CENT = D("0.01")


def inference_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: Decimal,
    output_rate: Decimal,
    cached_tokens: int = 0,
    cached_rate: Decimal | None = None,
) -> Decimal:
    if min(input_tokens, output_tokens, cached_tokens) < 0 or cached_tokens > input_tokens:
        raise ValueError(
            "Token counts must be nonnegative and cached tokens cannot exceed input tokens"
        )
    if min(input_rate, output_rate, cached_rate if cached_rate is not None else D(0)) < 0:
        raise ValueError("Prices must be nonnegative")
    regular = input_tokens - cached_tokens
    return (
        D(regular) * input_rate
        + D(cached_tokens) * (cached_rate if cached_rate is not None else input_rate)
        + D(output_tokens) * output_rate
    ) / MILLION


def human_cost(minutes: Decimal, hourly_rate: Decimal) -> Decimal:
    if minutes < 0 or hourly_rate < 0:
        raise ValueError("Minutes and hourly rate must be nonnegative")
    return minutes * hourly_rate / D(60)


@dataclass(frozen=True)
class ExecutionCost:
    inference: Decimal = ZERO
    tools: Decimal = ZERO
    review: Decimal = ZERO
    correction: Decimal = ZERO
    fallback: Decimal = ZERO
    infrastructure: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return sum(
            (
                self.inference,
                self.tools,
                self.review,
                self.correction,
                self.fallback,
                self.infrastructure,
            ),
            D(0),
        )


def aggregate(executions: Iterable[dict]) -> dict:
    rows = list(executions)
    successes = sum(r["outcome"] == "verified_success" for r in rows)
    failures = sum(r["outcome"] == "verified_failure" for r in rows)
    unknown = len(rows) - successes - failures
    total = sum((D(str(r["total_cost"])) for r in rows), D(0))
    resolved = [
        r for r in rows if r["outcome"] == "verified_success" or r.get("fallback_completed")
    ]
    resolved_cost = sum((D(str(r["total_cost"])) for r in resolved), D(0))
    baseline_rows = [r for r in rows if r.get("baseline_cost") is not None]
    baseline = sum((D(str(r["baseline_cost"])) for r in baseline_rows), D(0))
    evaluated = successes + failures
    attempts = sum(int(r.get("attempts", 1)) for r in rows)
    retried = [r for r in rows if int(r.get("attempts", 1)) > 1]
    costs = sorted(D(str(r["total_cost"])) for r in rows)
    percentile = lambda p: costs[max(0, ceil(len(costs) * p) - 1)] if costs else None
    resolved_missing_baselines = sum(r.get("baseline_cost") is None for r in resolved)
    interventions = sum(
        D(str(r.get("human_cost", 0))) + D(str(r.get("fallback_cost", 0))) > 0 for r in rows
    )
    fallback_count = sum(bool(r.get("fallback_completed")) for r in rows)
    retry_spend = sum(
        (
            D(str(r.get("retry_inference_cost", 0))) + D(str(r.get("retry_tool_cost", 0)))
            for r in rows
        ),
        D(0),
    )
    return {
        "executions": len(rows),
        "verified_successes": successes,
        "verified_failures": failures,
        "unknown_outcomes": unknown,
        "verified_success_fraction": D(successes) / D(len(rows)) if rows else None,
        "evaluated_success_rate": D(successes) / D(evaluated) if evaluated else None,
        "total_cost": total,
        "cost_per_execution": total / D(len(rows)) if rows else None,
        "cost_per_verified_success": total / D(successes) if successes else None,
        "resolved_tasks": len(resolved),
        "cost_per_resolved_task": resolved_cost / D(len(resolved)) if resolved else None,
        "baseline_cost": baseline,
        "net_savings_resolved": sum(
            (D(str(r["baseline_cost"])) - D(str(r["total_cost"])) for r in resolved), D(0)
        )
        if not resolved_missing_baselines
        else None,
        "excluded_unresolved": len(rows) - len(resolved),
        "resolved_missing_baselines": resolved_missing_baselines,
        "total_attempts": attempts,
        "retry_attempts": sum(max(int(r.get("attempts", 1)) - 1, 0) for r in rows),
        "executions_with_retries": len(retried),
        "retry_rate": D(len(retried)) / D(len(rows)) if rows else None,
        "mean_attempts": D(attempts) / D(len(rows)) if rows else None,
        "retry_spending": retry_spend,
        "human_intervention_rate": D(interventions) / D(len(rows)) if rows else None,
        "human_fallback_count": fallback_count,
        "human_fallback_rate": D(fallback_count) / D(len(rows)) if rows else None,
        "automation_rate": D(successes) / D(len(rows)) if rows else None,
        "median_execution_cost": (costs[(len(costs) - 1) // 2] + costs[len(costs) // 2]) / D(2)
        if costs
        else None,
        "p90_execution_cost": percentile(0.90),
        "p95_execution_cost": percentile(0.95),
        "missing_model_costs": sum(int(r.get("missing_model_costs", 0)) for r in rows),
        "missing_tool_costs": sum(int(r.get("missing_tool_costs", 0)) for r in rows),
        "provisional": unknown > 0
        or any(
            int(r.get("missing_model_costs", 0)) or int(r.get("missing_tool_costs", 0))
            for r in rows
        ),
        "warnings": (["Some outcomes are unverified or indeterminate"] if unknown else [])
        + (
            ["Some model calls have neither reported nor calculable cost"]
            if any(int(r.get("missing_model_costs", 0)) for r in rows)
            else []
        )
        + (
            ["Some tool calls have no recorded charge"]
            if any(int(r.get("missing_tool_costs", 0)) for r in rows)
            else []
        ),
    }


def display(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))
