#!/usr/bin/env bash
# Milestone 1 – Smoke Test
# Verifies that the backend is up, can accept a cAdvisor batch, and persists data.
#
# Usage:
#   ./scripts/smoke_test.sh              # test against localhost:8000 (default)
#   ./scripts/smoke_test.sh http://api:8000  # test from inside Docker network

set -euo pipefail

API_BASE="${1:-http://localhost:8000}"
TOKEN="${CADVISOR_METRICS_API_TOKEN:-my-secret-token}"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }

echo "=== Manifold Milestone 1 Smoke Test ==="
echo "API: ${API_BASE}"
echo ""

# 1. Health check
echo "1. Checking backend health..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${API_BASE}/healthz" || true)
[ "$HTTP_CODE" = "200" ] && pass "Backend healthy (HTTP $HTTP_CODE)" || fail "Backend not reachable (HTTP $HTTP_CODE)"

# 2. Get baseline ingest stats
echo "2. Checking current ingest stats..."
BEFORE=$(curl -s "${API_BASE}/ingest/stats")
echo "   Before: $BEFORE"

# 3. Post a synthetic cAdvisor batch
echo "3. Sending synthetic cAdvisor batch..."
PAYLOAD='{
  "schema_version": "1",
  "sent_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
  "machine_name": "smoke-test-node",
  "source": {"component": "cadvisor", "driver": "httpapi", "version": "v0.50.0"},
  "samples": [
    {
      "container_reference": {"name": "/smoke-test-container", "aliases": ["smoke"], "namespace": "docker"},
      "container_spec": {"image": "nginx:latest", "labels": {"app": "smoke"}},
      "stats": {
        "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
        "cpu": {"usage": {"total": 123456789}},
        "memory": {"usage": 67108864, "working_set": 50331648}
      }
    }
  ]
}'

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_BASE}/cadvisor/batch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d "$PAYLOAD")

BODY=$(echo "$RESPONSE" | head -n -1)
CODE=$(echo "$RESPONSE" | tail -n 1)

[ "$CODE" = "202" ] && pass "Batch accepted (HTTP $CODE): $BODY" || fail "Batch rejected (HTTP $CODE): $BODY"

# 4. Verify data was persisted
echo "4. Verifying data persistence..."
sleep 1
AFTER=$(curl -s "${API_BASE}/ingest/stats")
echo "   After: $AFTER"

SNAPSHOTS=$(echo "$AFTER" | python3 -c "import sys,json; print(json.load(sys.stdin)['snapshots'])" 2>/dev/null || echo "0")
[ "$SNAPSHOTS" -gt 0 ] && pass "Data persisted ($SNAPSHOTS snapshot(s) in DB)" || fail "No snapshots found in database"

echo ""
echo "=== All smoke tests passed! ==="
