# Data quality

AI Workflow Cost Analyzer reports coverage and warnings for outcome labels, model pricing, baselines, recorded human work, conflicting evidence, and unpriced operations. These are coverage indicators, not a score proving that a dataset is representative or labels are correct.

- Unknown and indeterminate outcomes remain visible and are excluded from evaluated success-rate denominators.
- Verified fraction uses all selected executions as denominator; evaluated success rate uses verified successes plus verified failures.
- Missing model/tool prices remain unknown and are reported as incomplete cost evidence rather than measured zero.
- A missing baseline does not become zero. If any resolved task in the selected resolved cohort lacks a baseline, net savings is unavailable.
- Conflicting evidence is surfaced for review. Imported outcome labels are not automatically rewritten from evidence.
- Human-work coverage indicates recorded work; it does not establish that all intervention was captured.
- Synthetic fixture labels, costs, and evaluator behavior are fictional and do not validate real task quality.

Inspect event provenance, profile versions, evaluator rules, task selection, and exclusions before using the metrics in business decisions.
