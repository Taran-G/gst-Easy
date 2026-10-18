import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.seed import seed_database
from app.graph.client import tenant_graph

client = TestClient(app)

def get_auth_headers():
    res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

def test_automation_status():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    res = client.get("/api/v1/automation/status", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "is_running" in data
    assert "interval_seconds" in data
    assert "logs" in data
    assert "email_mode" in data

def test_automation_toggle():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # Pause
    res = client.post("/api/v1/automation/toggle", json={"enabled": False}, headers=headers)
    assert res.status_code == 200
    assert res.json()["is_running"] is False
    
    # Resume
    res2 = client.post("/api/v1/automation/toggle", json={"enabled": True}, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["is_running"] is True

def test_automation_simulate_incoming_email_and_autonomous_ingest():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    # 1. Drop a new invoice email from Sharma Steels into the watched inbox
    res_drop = client.post(
        "/api/v1/automation/email/simulate-incoming",
        json={
            "from_addr": "sharma@sharmasteels.com",
            "subject": "Monthly Steel Purchase Invoice",
            "body": "Please find attached invoice copy for payment.",
            "fixture_name": "clean_intrastate"
        },
        headers=headers
    )
    assert res_drop.status_code == 200
    assert res_drop.json()["status"] == "delivered_to_inbox"
    
    # 2. Trigger the autonomous agent cycle
    res_cycle = client.post("/api/v1/automation/run-now", headers=headers)
    assert res_cycle.status_code == 200
    summary = res_cycle.json()["summary"]
    assert summary["processed_bills"] >= 1
    
    # 3. Verify the email was processed and an automated reply was generated
    res_emails = client.get("/api/v1/automation/emails", headers=headers)
    assert res_emails.status_code == 200
    email_data = res_emails.json()
    
    # Check that inbox email is marked read and has processed_invoice_id
    read_emails = [e for e in email_data["inbox"] if e["is_read"]]
    assert len(read_emails) >= 1
    assert read_emails[0]["from_addr"] == "sharma@sharmasteels.com"
    
    # Check that automated confirmation reply was sent
    sent_emails = email_data["sent"]
    assert len(sent_emails) >= 1
    reply = sent_emails[0]
    assert reply["to_addr"] == "sharma@sharmasteels.com"
    assert "READY" in reply["body"] or "verified" in reply["body"].lower()

    # 4. Verify the bill is now visible in the purchase inbox
    res_inv = client.get("/api/v1/invoices", headers=headers)
    assert res_inv.status_code == 200
    invoices = res_inv.json()["invoices"]
    assert any(inv["number"] == "INV-2026-001" for inv in invoices)

def test_automation_interval():
    seed_database(reset=True)
    headers = get_auth_headers()
    
    res = client.post("/api/v1/automation/interval", json={"interval_seconds": 15}, headers=headers)
    assert res.status_code == 200
    assert res.json()["interval_seconds"] == 15
