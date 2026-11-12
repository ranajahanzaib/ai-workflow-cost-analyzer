#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PID=""
WEB_PID=""
API_HOST="${AI_WORKFLOW_COST_ANALYZER_API_HOST:-127.0.0.1}"
API_PORT="${AI_WORKFLOW_COST_ANALYZER_API_PORT:-8000}"
WEB_HOST="${AI_WORKFLOW_COST_ANALYZER_WEB_HOST:-127.0.0.1}"
WEB_PORT="${AI_WORKFLOW_COST_ANALYZER_WEB_PORT:-5173}"
cleanup() {
  [[ -z "$API_PID" ]] || kill "$API_PID" 2>/dev/null || true
  [[ -z "$WEB_PID" ]] || kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(cd "$ROOT/apps/api" && exec env PYTHONPATH=src uv run uvicorn outcomemeter.main:app --host "$API_HOST" --port "$API_PORT") &
API_PID=$!
(cd "$ROOT/apps/web" && exec env WEB_HOST="$WEB_HOST" WEB_PORT="$WEB_PORT" VITE_API_TARGET="${VITE_API_TARGET:-http://${API_HOST}:${API_PORT}}" pnpm run dev) &
WEB_PID=$!
echo "AI Workflow Cost Analyzer API: http://${API_HOST}:${API_PORT}/docs"
echo "AI Workflow Cost Analyzer web: http://${WEB_HOST}:${WEB_PORT}"
set +e
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 0.5
done
if ! kill -0 "$API_PID" 2>/dev/null; then
  wait "$API_PID"
  STATUS=$?
elif ! kill -0 "$WEB_PID" 2>/dev/null; then
  wait "$WEB_PID"
  STATUS=$?
else
  STATUS=0
fi
exit "$STATUS"
