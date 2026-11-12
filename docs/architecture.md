# Architecture

AI Workflow Cost Analyzer is a single-process local application. FastAPI exposes typed JSON APIs; a repository module initializes a local DuckDB database; the React/Vite client presents calculated responses. Writes use a process lock and explicit transactions. Do not run multiple API workers against one database file.

The data flow is import validation → normalized domain records → transactional DuckDB persistence → economics aggregation → dashboard/report API. Financial logic lives in `apps/api/src/outcomemeter/economics.py`, separate from routes. The API binds to loopback in the documented development command. No external services are needed.
