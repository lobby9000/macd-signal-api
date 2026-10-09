#!/usr/bin/env bash
# Start the API, run the Postman collection with Newman, write reports to reports/<label>/.
# Usage: scripts/run_newman.sh <label>
set -uo pipefail
LABEL=${1:-local}
PORT=${PORT:-8000}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/reports/$LABEL"
mkdir -p "$OUT"
cd "$ROOT" || exit 1
python -m uvicorn api.main:app --port "$PORT" --log-level warning > "$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 1 50); do curl -sf "http://localhost:$PORT/health" > /dev/null && break; sleep 0.2; done
newman run postman/macd-signal-api.postman_collection.json \
  --env-var "baseUrl=http://localhost:$PORT" \
  --reporters cli,junit,htmlextra,json \
  --reporter-junit-export "$OUT/newman-junit.xml" \
  --reporter-json-export "$OUT/newman.json" \
  --reporter-htmlextra-export "$OUT/newman-report.html" \
  --reporter-htmlextra-title "MACD Signal API - $LABEL" \
  --color off
STATUS=$?
echo "newman exit code: $STATUS (reports in reports/$LABEL)"
exit $STATUS
