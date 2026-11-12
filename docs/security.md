# Security and privacy

This local MVP stores data on disk in DuckDB and is designed for trusted local use. It has no authentication and must not be exposed to a public network. Bind to loopback; public use requires authentication, authorization, TLS, and storage protections. Uploads are size-limited and never executed; the application does not fetch user URLs or store prompt/completion bodies. No external telemetry is configured. Do not import sensitive data unless local machine protections meet your needs.
