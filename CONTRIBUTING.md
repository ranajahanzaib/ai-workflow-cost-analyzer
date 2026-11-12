# Contributing

Thanks for helping improve AI Workflow Cost Analyzer. Keep changes focused, explain the user problem they solve, and preserve the distinction between observed data and assumptions.

## Local setup

Use Python 3.12+, `uv`, Node.js 20.19+ (Node 22 recommended), `pnpm`, and Make:

```sh
make setup
make seed
make test
make lint
make build
```

Start the app with `make dev`. The backend uses one DuckDB process; do not add multi-worker guidance or concurrent writers without changing that storage model. Tests use temporary databases and synthetic records.

## Changes and review

- Open an issue for larger design changes before investing in a broad implementation.
- Keep financial calculations in the economics module and use `Decimal` for money.
- Add tests for changed calculations, import validation, API behavior, or UI behavior.
- Preserve provenance: distinguish provider-reported cost, priced estimates, baselines, manual labels, and unknown values.
- Keep fixtures fictional. Never include customer data, credentials, prompt bodies, or private traces.
- Do not silently change historical cost attribution when profiles change.
- Keep imports transactional and validate relationships before commit.
- Update the relevant docs when changing formats, formulas, or operational limits.
- Run the checks above and report any check you could not run in the pull request.

Use a pull request description that covers the problem, approach, tests, and any changed assumptions. Screenshots are useful for visible UI changes.

## Reporting issues

Use the repository issue forms for bugs and feature requests. Remove secrets and sensitive records from logs and examples before sharing them.
