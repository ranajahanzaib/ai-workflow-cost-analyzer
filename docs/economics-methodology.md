# Economics methodology

All financial calculations use `Decimal` in the independent economics module and DuckDB `DECIMAL(20,8)` columns. Inputs are retained at eight decimal places; display values round to cents using half-up rounding. The API currently reports USD only.

## Inference and attribution

When token prices are available, regular input tokens are multiplied by the input price per million; cached input tokens use their separate rate; output tokens use the output rate. Cached tokens are understood as included in total input tokens and are priced by replacing that portion's ordinary input rate. A provider-reported charge takes precedence for the attributed cost of a call; the reported and calculated fields remain separate. They are never added together. Missing charges are not measured zero and must be treated as incomplete evidence.

Every model and tool event from every logical attempt contributes to execution cost. Retries are a drilldown over inference and tool expenses, never an additive expense category. Human work is minutes × hourly rate ÷ 60. Human fallback is included in actual resolution cost and is distinct from review/correction. Costs are not rounded per operation before aggregation.

## Metrics

- Cost per execution = all attributed cost in the selected cohort ÷ all executions.
- Cost per verified success = all attributed cost, including failed and unknown executions, ÷ verified successful executions. With no verified successes the value is unavailable, not zero.
- Evaluated success rate = verified successes ÷ (verified successes + verified failures). Unknown and indeterminate outcomes remain separately visible. The all-selected verified fraction uses all selected executions as its denominator.
- Cost per resolved task uses verified AI success or explicitly recorded fallback completion. Unresolved cases are excluded.
- Resolved-cohort net savings = baseline minus actual cost for resolved cases only. Unresolved cases are excluded and counted. A baseline is an assumption unless its source says otherwise.

## Evidence and limits

The synthetic dataset uses fixed random seed 481516 and fictional costs/outcomes. It demonstrates the data model, not a real benchmark. Manual labels and business-event references are evidence with stated provenance, not cryptographic proof. Incomplete pricing, baseline assumptions, and unverified outcomes can materially alter interpretation. Historical observation is not rewritten by scenario inputs.

## Worked example

Suppose a cohort has 10 executions costing $12 in total: eight verified successes, one verified failure, and one unverified result. Cost per execution is $1.20. Cost per verified success is $1.50 (`$12 / 8`), because failed and unknown runs still consumed resources. Evaluated success rate is 88.9% (`8 / (8 + 1)`), while the verified-success fraction across all selected runs is 80% (`8 / 10`). If only seven tasks were resolved (six AI successes and one explicit human fallback) and their total attributed cost is $9.10, cost per resolved task is $1.30. If all seven have a human baseline totaling $14, net savings is $4.90. If even one resolved task lacks a baseline, net savings is unavailable rather than treating that baseline as zero.

These are descriptive cohort calculations. "Verified" means the dataset carries an explicit verified outcome label; it does not mean AI Workflow Cost Analyzer independently audited the label or proves a causal business impact. Savings are estimated against recorded baselines and should not be described as confirmed savings without suitable evidence and study design.
