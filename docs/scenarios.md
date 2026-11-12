# Scenario analysis

The scenario endpoint and UI recalculate the selected workflow with explicit hourly rate, human-only baseline minutes, review minutes, correction minutes, a multiplier for existing model/tool costs, monthly fixed overhead, and monthly volume. Allocated overhead per execution is fixed monthly cost divided by supplied volume.

For each historical execution, scenario cost is `(observed inference + observed tool cost) × multiplier + assumed review/correction/fallback labor + allocated overhead`. Fallback minutes come from the recorded execution; review and correction are replaced with scenario assumptions. Baseline cost is scenario baseline minutes × scenario hourly rate ÷ 60. Existing outcomes and task mix remain unchanged.

The response returns recalculated cohort metrics, assumptions, the maximum per-task workflow budget (`baseline labor − review/correction labor − allocated overhead`), a break-even hourly rate where the assumed human-time savings are positive, and net-savings sensitivity at fixed rates from $10 to $60/hour. Sensitivity compares the resolved cohort only. Results are deterministic illustrations based on historical observations; they do not predict how a model or human behavior will change under a new configuration. Historical records are not modified.
