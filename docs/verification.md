# Outcome verification

Execution runtime status (`pending`, `running`, `finished`, `error`, `cancelled`) is distinct from outcome status. Only explicit `verified_success` contributes to the verified-success numerator. `unverified` and `indeterminate` remain unknown. Evidence rows record method, status, reference, and reasoning, but importing evidence does not overwrite the separately supplied execution outcome. The included demo uses synthetic evaluator labels and is not real business evidence.
