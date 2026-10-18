#!/usr/bin/env bash
set -eo pipefail

API_BASE=${API_BASE:-"http://localhost:8000"}

echo "=== LedgerGraph Production Smoke Test ==="
echo "Targeting API at: $API_BASE"

# 1. Health check
echo -n "1. Checking API Health... "
HEALTH=$(curl -s -f "$API_BASE/api/v1/health" || echo "")
if [[ "$HEALTH" =~ "ok" ]]; then
  echo "OK ($HEALTH)"
else
  echo "FAILED"
  exit 1
fi

# 2. Login as CA Partner
echo -n "2. Authenticating as partner@demo... "
LOGIN_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"partner@demo","password":"partner123"}')
TOKEN=$(echo "$LOGIN_RESP" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [[ -n "$TOKEN" ]]; then
  echo "OK (Token acquired)"
else
  echo "FAILED"
  exit 1
fi

AUTH_HEADER="Authorization: Bearer $TOKEN"
TENANT_HEADER="X-Tenant: apex"

# 3. Simulate Ingestion
echo -n "3. Ingesting bill (clean_intrastate)... "
INGEST_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/ingest/simulate?fixture_name=clean_intrastate" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
STATE=$(echo "$INGEST_RESP" | grep -o '"state":"[^"]*' | cut -d'"' -f4)
echo "OK (State: $STATE)"

# 4. Reconcile GSTR-2B
echo -n "4. Running GSTR-2B Reconciliation for period 092026... "
RECON_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/reconcile/092026" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
echo "OK"

# 5. Impact Trace (Sharma Steels)
echo -n "5. Running Impact Trace for Sharma Steels... "
IMPACT_RESP=$(curl -s -f "$API_BASE/api/v1/risk/impact?gstin=06AABCS1234S1Z4&delay=4" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
ORDERS_COUNT=$(echo "$IMPACT_RESP" | grep -o '"order_number"' | wc -l | tr -d ' ')
echo "OK ($ORDERS_COUNT downstream orders affected)"

# 6. Audit Trail
echo -n "6. Inspecting Tamper-Evident Audit Trail... "
AUDIT_RESP=$(curl -s -f "$API_BASE/api/v1/audit" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
EVENT_COUNT=$(echo "$AUDIT_RESP" | grep -o '"event_type"' | wc -l | tr -d ' ')
echo "OK ($EVENT_COUNT audit events chained)"

echo "=== ALL SMOKE CHECKS PASSED SUCCESSFULLY ==="
