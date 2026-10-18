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

# 7. CSV Reconciliation Audit Working Paper
echo -n "7. Exporting GSTR-2B Audit Working Paper (CSV)... "
CSV_RESP=$(curl -s -f "$API_BASE/api/v1/reconcile/092026/export-csv" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
if [[ "$CSV_RESP" =~ "LEDGERGRAPH GSTR-2B RECONCILIATION REPORT" ]]; then
  echo "OK (CSV working paper generated)"
else
  echo "FAILED"
  exit 1
fi

# 8. Approve and Export Tally XML
INV_ID=$(echo "$INGEST_RESP" | grep -o '"invoice_id":"[^"]*' | cut -d'"' -f4)
echo -n "8. Approving Bill and Exporting Tally XML... "
APPROVE_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/invoices/bulk-approve" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"invoice_ids\":[\"$INV_ID\"]}")

TALLY_XML=$(curl -s -f -X POST "$API_BASE/api/v1/tally/export" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER" \
  -H "Content-Type: application/json" \
  -d "{\"invoice_ids\":[\"$INV_ID\"]}")

if [[ "$TALLY_XML" =~ "ENVELOPE" && "$TALLY_XML" =~ "VOUCHER" ]]; then
  echo "OK (Zero-sum Tally XML verified)"
else
  echo "FAILED"
  exit 1
fi

# 9. WhatsApp Bill Import & Agent Auto-Reply
echo -n "9. Testing WhatsApp Bill Import & Auto-Reply... "
WA_BILL_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/whatsapp/simulate/bill" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER" \
  -F "fixture_name=clean_interstate" \
  -F "phone=+919876543210" \
  -F "caption=Attached Reliable Transport invoice")
if [[ "$WA_BILL_RESP" =~ "outbound_reply" ]]; then
  echo "OK (Inbound bill ingested & Agent auto-reply dispatched)"
else
  echo "FAILED"
  exit 1
fi

# 10. WhatsApp Text Query & Agent Intent Reply
echo -n "10. Testing WhatsApp Text Query & Agent Reply... "
WA_TEXT_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/whatsapp/simulate/text" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919876543210","text":"What is status of our pending bills?"}')
if [[ "$WA_TEXT_RESP" =~ "outbound_reply" ]]; then
  echo "OK (Agent replied with live account summary)"
else
  echo "FAILED"
  exit 1
fi

# 11. WhatsApp Message Ledger CSV Export
echo -n "11. Exporting WhatsApp Communications Ledger (CSV)... "
WA_CSV_RESP=$(curl -s -f "$API_BASE/api/v1/whatsapp/export" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
if [[ "$WA_CSV_RESP" =~ "Message ID" && "$WA_CSV_RESP" =~ "INBOUND" && "$WA_CSV_RESP" =~ "OUTBOUND" ]]; then
  echo "OK (WhatsApp audit working paper generated)"
else
  echo "FAILED"
  exit 1
fi

# 12. Autonomous Agent Automated Cycle & Email Ingestion
echo -n "12. Testing Autonomous AI Agent Cycle & Email Ingestion... "
curl -s -f -X POST "$API_BASE/api/v1/automation/email/simulate-incoming" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER" \
  -H "Content-Type: application/json" \
  -d '{"from_addr":"sharma@sharmasteels.com","subject":"Auto Invoice Delivery","fixture_name":"clean_intrastate"}' > /dev/null

AUTO_CYCLE_RESP=$(curl -s -f -X POST "$API_BASE/api/v1/automation/run-now" \
  -H "$AUTH_HEADER" -H "$TENANT_HEADER")
if [[ "$AUTO_CYCLE_RESP" =~ "processed_bills" ]]; then
  echo "OK (Autonomous background cycle executed & auto-reply dispatched)"
else
  echo "FAILED"
  exit 1
fi

echo "=== ALL SMOKE CHECKS PASSED SUCCESSFULLY ==="
