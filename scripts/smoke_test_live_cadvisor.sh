#!/usr/bin/env bash
# Milestone 1 – Live cAdvisor Ingestion Verification
# ────────────────────────────────────────────────────
# Verifies that the compose-managed cAdvisor service is ACTUALLY pushing
# container telemetry to the backend, rather than relying on a synthetic POST.
#
# Usage:
#   ./scripts/smoke_test_live_cadvisor.sh                          # default localhost:8000
#   ./scripts/smoke_test_live_cadvisor.sh http://localhost:8000     # explicit URL
#
# Prerequisites:
#   docker compose up --build   (api + cadvisor must both be running)
#
# Exit codes:
#   0 – live ingestion verified
#   1 – timeout / failure

set -euo pipefail

API_BASE="${1:-http://localhost:8000}"
TIMEOUT="${LIVE_CADVISOR_TIMEOUT:-60}"     # seconds to wait for real snapshots

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
info() { echo -e "${YELLOW}… $1${NC}"; }

# Helper: extract a field from /ingest/stats JSON
get_stat() {
    curl -s "${API_BASE}/ingest/stats" | python3 -c "import sys,json; print(json.load(sys.stdin)['$1'])" 2>/dev/null || echo "0"
}

echo "=== Manifold – Live cAdvisor Ingestion Test ==="
echo "API:     ${API_BASE}"
echo "Timeout: ${TIMEOUT}s"
echo ""

# ── 1. Wait for /healthz ───────────────────────────────────
info "Waiting for backend health…"
HEALTH_WAIT=0
while [ "$HEALTH_WAIT" -lt "$TIMEOUT" ]; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/healthz" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        pass "Backend healthy (HTTP $HTTP_CODE)"
        break
    fi
    sleep 2
    HEALTH_WAIT=$((HEALTH_WAIT + 2))
done
[ "$HEALTH_WAIT" -ge "$TIMEOUT" ] && fail "Backend did not become healthy within ${TIMEOUT}s"

# ── 2. Record baseline snapshot count ──────────────────────
BASELINE=$(get_stat snapshots)
info "Baseline snapshot count: ${BASELINE}"

# ── 3. Wait for snapshot count to increase from background ingestion
info "Waiting for real cAdvisor-originated snapshots (no synthetic POSTs)…"
ELAPSED=0
while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    CURRENT=$(get_stat snapshots)
    CONTAINERS=$(get_stat containers)

    if [ "$CURRENT" -gt "$BASELINE" ]; then
        echo ""
        pass "Live cAdvisor ingestion confirmed!"
        echo "   Snapshots:   ${BASELINE} → ${CURRENT}  (+$((CURRENT - BASELINE)))"
        echo "   Containers:  ${CONTAINERS}"
        echo "   Elapsed:     ${ELAPSED}s"
        echo ""
        echo "=== Live cAdvisor verification passed! ==="
        exit 0
    fi

    info "[${ELAPSED}s/${TIMEOUT}s] snapshots=${CURRENT} (waiting for > ${BASELINE})…"
done

echo ""
fail "No new snapshots arrived within ${TIMEOUT}s – cAdvisor may not be pushing to the backend."
