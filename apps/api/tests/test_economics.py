from decimal import Decimal as D

import pytest

from outcomemeter.economics import aggregate, human_cost, inference_cost


def test_token_cost_accounts_for_cached_input_without_double_counting():
    assert inference_cost(1_000_000, 100_000, D(2), D(10), 200_000, D("0.5")) == D("2.7")


def test_human_cost_uses_decimal_arithmetic():
    assert human_cost(D("2.5"), D(36)) == D("1.5")


@pytest.mark.parametrize(
    "args", [(-1, 0, D(1), D(1)), (1, 1, D(-1), D(1)), (1, 1, D(1), D(1), 2, None)]
)
def test_invalid_token_pricing_is_rejected(args):
    with pytest.raises(ValueError):
        inference_cost(*args)


def test_cost_per_success_includes_failed_execution_costs():
    metrics = aggregate(
        [
            {"outcome": "verified_success", "total_cost": "2.00"},
            {"outcome": "verified_failure", "total_cost": "1.00"},
        ]
    )
    assert metrics["cost_per_verified_success"] == D("3.00")


def test_unknown_not_success_and_zero_success_is_na():
    metrics = aggregate([{"outcome": "unverified", "total_cost": "1"}])
    assert metrics["verified_successes"] == 0 and metrics["cost_per_verified_success"] is None
    assert metrics["verified_success_fraction"] == 0 and metrics["evaluated_success_rate"] is None


def test_unresolved_tasks_excluded_from_resolved_savings():
    metrics = aggregate(
        [
            {"outcome": "verified_success", "total_cost": "2", "baseline_cost": "5"},
            {"outcome": "verified_failure", "total_cost": "3", "baseline_cost": "5"},
        ]
    )
    assert metrics["net_savings_resolved"] == D(3) and metrics["excluded_unresolved"] == 1


def test_missing_baseline_makes_resolved_savings_unavailable():
    metrics = aggregate([{"outcome": "verified_success", "total_cost": "2", "baseline_cost": None}])
    assert metrics["net_savings_resolved"] is None
    assert metrics["resolved_missing_baselines"] == 1


def test_retry_cost_is_a_subset_and_retry_rate_uses_executions():
    metrics = aggregate(
        [
            {
                "outcome": "verified_success",
                "total_cost": "2",
                "attempts": 2,
                "retry_inference_cost": "0.4",
            },
            {"outcome": "verified_failure", "total_cost": "1", "attempts": 1},
        ]
    )
    assert metrics["retry_attempts"] == 1
    assert metrics["executions_with_retries"] == 1
    assert metrics["retry_rate"] == D("0.5")
    assert metrics["retry_spending"] == D("0.4")
