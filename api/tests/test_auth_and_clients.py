import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.email_service import extract_email_intent_and_entities

client = TestClient(app)

def test_ca_firm_signup_and_client_creation():
    """Tests CA Firm accountant signup, client tenant creation, and switching."""
    email = f"ca_{uuid.uuid4().hex[:6]}@sharma-ca.com"
    signup_payload = {
        "name": "CA Rajesh Singhal",
        "email": email,
        "password": "Password123!",
        "role": "Admin",
        "firm_name": "Singhal & Associates",
        "company_name": "Singhal Motors",
        "gstin": "06AAACA1234A1Z5",
        "pain_points": ["itc_loss", "rule_37"],
        "monthly_invoice_volume": "200-1000",
        "accounting_software": "Tally Prime"
    }
    
    # 1. Sign up as CA
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "Admin"
    token = data["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # 2. CA creates a new client dashboard
    new_client_res = client.post(
        "/api/v1/auth/tenants",
        headers=auth_headers,
        json={
            "name": "Reliable Logistics Private Limited",
            "gstin": "27AABCR1234F1Z9",
            "filing_freq": "Monthly"
        }
    )
    assert new_client_res.status_code == 200, new_client_res.text
    new_client = new_client_res.json()
    assert new_client["name"] == "Reliable Logistics Private Limited"
    assert new_client["gstin"] == "27AABCR1234F1Z9"
    new_tenant_id = new_client["id"]
    
    # 3. CA lists tenants - should include the new client
    tenants_res = client.get("/api/v1/auth/tenants", headers=auth_headers)
    assert tenants_res.status_code == 200
    tenant_ids = [t["id"] for t in tenants_res.json()]
    assert new_tenant_id in tenant_ids
    
    # 4. CA accesses invoices for the new client
    inv_res = client.get("/api/v1/invoices", headers={**auth_headers, "X-Tenant": new_tenant_id})
    assert inv_res.status_code == 200

def test_client_role_strict_isolation():
    """Tests that Client accounts can ONLY view their own dashboard and cannot switch."""
    email = f"client_{uuid.uuid4().hex[:6]}@tata.com"
    signup_payload = {
        "name": "Tata Motors Dealership",
        "email": email,
        "password": "ClientPassword123!",
        "role": "Client",
        "company_name": "Tata Motors West",
        "gstin": "27AAACT1234A1Z5",
        "pain_points": ["manual_entry", "tally_reconcile"],
        "monthly_invoice_volume": "50-200",
        "accounting_software": "Tally Prime"
    }
    
    # 1. Sign up as Client
    res = client.post("/api/v1/auth/signup", json=signup_payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["user"]["role"] == "Client"
    client_tenant_id = data["default_tenant_id"]
    assert client_tenant_id is not None
    token = data["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Client queries /auth/tenants - MUST return ONLY their single assigned tenant!
    tenants_res = client.get("/api/v1/auth/tenants", headers=auth_headers)
    assert tenants_res.status_code == 200
    assigned_tenants = tenants_res.json()
    assert len(assigned_tenants) == 1
    assert assigned_tenants[0]["id"] == client_tenant_id
    
    # 3. Client can access their own tenant
    ok_res = client.get("/api/v1/invoices", headers={**auth_headers, "X-Tenant": client_tenant_id})
    assert ok_res.status_code == 200
    
    # 4. Client attempts to access another tenant (e.g. 'apex' or 'greenleaf') -> MUST return 403 Forbidden!
    forbidden_res = client.get("/api/v1/invoices", headers={**auth_headers, "X-Tenant": "apex"})
    assert forbidden_res.status_code == 403, "Client should be forbidden from accessing other tenants"
    assert "Access denied: Client is strictly limited to dashboard" in forbidden_res.text
    
    # 5. Client attempts to create a new tenant -> MUST return 403 Forbidden!
    create_forbidden = client.post(
        "/api/v1/auth/tenants",
        headers=auth_headers,
        json={"name": "Hacked Tenant", "gstin": "06AAACA1234A1Z5"}
    )
    assert create_forbidden.status_code == 403

def test_email_intent_and_gstr2b_extraction():
    """Tests the smart parser detecting GSTR-2B notifications and company names."""
    # Test 1: GSTR-2B notification
    subject1 = "Intimation of auto-drafted ITC statement in Form GSTR-2B for period 092026"
    body1 = "Dear Taxpayer, GSTR-2B for September 2026 is available for download."
    intent1 = extract_email_intent_and_entities(subject1, body1, "donotreply@gst.gov.in")
    assert intent1["is_gstr2b"] is True
    assert intent1["period"] == "092026"
    
    # Test 2: Tax invoice from Company Name
    subject2 = "Tax Invoice INV-2026-990 from Sharma Steels Ltd"
    body2 = "Please find attached bill for steel reinforcement bars."
    intent2 = extract_email_intent_and_entities(subject2, body2, "billing@sharmasteels.com")
    assert intent2["is_gstr2b"] is False
    assert "Sharma Steels" in intent2["company_name"]
