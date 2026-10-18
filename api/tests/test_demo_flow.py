import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.seed import seed_database

client = TestClient(app)

def test_full_two_minute_demo_flow():
    # 0. Clean repeatable demo state
    seed_database(reset=True)
    
    # 1. Login as Reviewer / CA Partner
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}
    
    # 2. Simulate 3 WhatsApp bills for Apex:
    # (a) clean_intrastate
    res1 = client.post("/api/v1/ingest/simulate?fixture_name=clean_intrastate", headers=headers)
    assert res1.status_code == 200
    assert res1.json()["state"] == "READY"
    clean_id = res1.json()["invoice_id"]
    
    # (b) math_error
    res2 = client.post("/api/v1/ingest/simulate?fixture_name=math_error", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["state"] == "BLOCKED"
    math_id = res2.json()["invoice_id"]
    
    # (c) unknown_supplier (creates Master Request)
    res3 = client.post("/api/v1/ingest/simulate?fixture_name=unknown_supplier", headers=headers)
    assert res3.status_code == 200
    assert res3.json()["state"] == "MASTER_REQUEST"
    unknown_id = res3.json()["invoice_id"]
    
    # 3. Check Inbox: 3 bills present with correct states
    inbox_res = client.get("/api/v1/invoices?tab=all", headers=headers)
    assert inbox_res.status_code == 200
    invoices = inbox_res.json()["invoices"]
    inv_map = {inv["id"]: inv["state"] for inv in invoices}
    assert inv_map[clean_id] == "READY"
    assert inv_map[math_id] == "BLOCKED"
    assert inv_map[unknown_id] == "MASTER_REQUEST"
    
    # 4. Approve clean bill -> succeeds!
    appr_res = client.post(f"/api/v1/invoices/{clean_id}/approve", headers=headers)
    assert appr_res.status_code == 200
    assert appr_res.json()["state"] == "APPROVED"
    
    # Trying to approve BLOCKED bill -> must fail!
    fail_appr = client.post(f"/api/v1/invoices/{math_id}/approve", headers=headers)
    assert fail_appr.status_code == 400
    
    # 5. Fix math error live: PATCH invoice total to 11800.00 -> state clears from BLOCKED to READY!
    patch_res = client.patch(f"/api/v1/invoices/{math_id}", json={"total_amount": 11800.00}, headers=headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["new_state"] == "READY"
    assert patch_res.json()["is_valid"] is True
    
    # 6. Map unknown supplier to Tally ledger -> state changes to READY!
    map_res = client.post("/api/v1/masters/map", json={
        "vendor_gstin": "06AABCK9999K1ZO",
        "tally_ledger_name": "Krishna Forge (Sundry Creditors)",
        "invoice_id": unknown_id
    }, headers=headers)
    assert map_res.status_code == 200
    
    detail_res = client.get(f"/api/v1/invoices/{unknown_id}", headers=headers)
    assert detail_res.json()["state"] == "READY"
    
    # 7. Export approved bills to Tally XML
    xml_res = client.post("/api/v1/tally/export", json={"invoice_ids": [clean_id]}, headers=headers)
    assert xml_res.status_code == 200
    assert "<VOUCHER" in xml_res.text
    assert "<PARTYLEDGERNAME>" in xml_res.text
    
    # 8. Reconcile with GSTR-2B
    recon_res = client.post("/api/v1/reconcile/092026", headers=headers)
    assert recon_res.status_code == 200
    counts = recon_res.json()["counts"]
    assert counts["matched"] >= 1
    
    # 9. Centerpiece: Impact Trace for Sharma Steels + 4 days
    impact_res = client.get("/api/v1/risk/impact?gstin=06AABCS1234S1Z4&delay=4", headers=headers)
    assert impact_res.status_code == 200
    impact_data = impact_res.json()
    assert impact_data["supplier_name"] == "Sharma Steels"
    assert len(impact_data["orders_affected"]) >= 2
    assert "Maruti-504" in [o["order_number"] for o in impact_data["orders_affected"]]
    assert "impact_trace.cypher" in impact_data["cypher"] or "MATCH" in impact_data["cypher"]
    
    # 10. Approve WhatsApp chase
    chase_res = client.post("/api/v1/chases/approve", json={
        "invoice_id": clean_id,
        "type": "missing_2b",
        "language": "en"
    }, headers=headers)
    assert chase_res.status_code == 200
    assert chase_res.json()["status"] == "sent"
    
    # 11. Verify Audit Trail
    audit_res = client.get("/api/v1/audit", headers=headers)
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert len(events) >= 5
    from app.core.audit import verify_audit_chain
    assert verify_audit_chain(events) is True
    
    # 12. Switch tenant to Greenleaf -> verify isolation!
    greenleaf_headers = {"Authorization": f"Bearer {token}", "X-Tenant": "greenleaf"}
    gl_inbox = client.get("/api/v1/invoices?tab=all", headers=greenleaf_headers)
    assert gl_inbox.status_code == 200
    # Apex bills must NOT appear in Greenleaf graph!
    gl_ids = [inv["id"] for inv in gl_inbox.json()["invoices"]]
    assert clean_id not in gl_ids
    assert math_id not in gl_ids
    assert unknown_id not in gl_ids
