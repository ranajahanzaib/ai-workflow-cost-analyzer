# Security policy

AI Workflow Cost Analyzer is a local-first analysis tool. It has no authentication or authorization and is not safe to expose directly to an untrusted network. The supported setup binds the API and development server to loopback.

## Reporting a vulnerability

Please do not open a public issue containing exploit details or sensitive data. Report vulnerabilities through GitHub's private Security Advisories feature. Include the affected version or commit, impact, and a minimal reproduction. Do not include real customer records, credentials, or private traces. The current response expectation is documented in [.github/SECURITY.md](.github/SECURITY.md).

## Deployment limits

Before any non-local deployment, add authentication, authorization, TLS, access controls for the DuckDB file and backups, and an operational patching process. Review uploaded data retention and filesystem protections for your environment. See [security and privacy notes](docs/security.md).
