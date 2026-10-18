import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token, hash_password
from app.graph.client import firm_graph, tenant_graph
from app.graph.schema import bootstrap_firm, bootstrap_tenant

client = TestClient(app)

def test_login_success():
    res = client.post("/api/v1/auth/login", json={
        "email": "accountant@demo",
        "password": "accountant123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "accountant@demo"
    assert data["user"]["role"] == "Reviewer"
    assert data["user"]["firm_id"] == "demo"

def test_login_failure():
    res = client.post("/api/v1/auth/login", json={
        "email": "accountant@demo",
        "password": "wrongpassword"
    })
    assert res.status_code == 401

def test_get_tenants():
    login_res = client.post("/api/v1/auth/login", json={
        "email": "accountant@demo",
        "password": "accountant123"
    })
    token = login_res.json()["access_token"]
    
    res = client.get("/api/v1/auth/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    tenants = res.json()
    tenant_ids = [t["id"] for t in tenants]
    assert "apex" in tenant_ids
    assert "greenleaf" in tenant_ids

def test_tenant_isolation_cross_firm_forbidden():
    """
    Verification check: Accountant of Firm A requesting tenant of Firm B gets 403.
    """
    # 1. Setup second firm 'firm_b' with a tenant 'tenant_b'
    firm_b_id = "firm_b"
    tenant_b_id = "tenant_b"
    
    fb_graph = firm_graph(firm_b_id)
    bootstrap_firm(firm_b_id)
    
    fb_graph.query(
        """
        MERGE (f:Firm {id: $firm_id, name: "Second CA Firm"})
        MERGE (u:User {email: "accountant@firmb", id: "u_fb", role: "Reviewer", name: "User B", password_hash: $pw})
        MERGE (t:Tenant {id: $tenant_id, name: "Firm B Client", gstin: "27AAACA9999A1Z5", state_code: "27"})
        MERGE (f)-[:HAS_USER]->(u)
        MERGE (f)-[:OWNS_TENANT]->(t)
        """,
        {
            "firm_id": firm_b_id,
            "tenant_id": tenant_b_id,
            "pw": hash_password("pass123")
        }
    )
    
    # 2. Login as accountant of Firm Demo (Firm A)
    res_a = client.post("/api/v1/auth/login", json={
        "email": "accountant@demo",
        "password": "accountant123"
    })
    token_a = res_a.json()["access_token"]
    
    # Create a protected test route or use auth test with require_tenant_access
    from fastapi import Depends
    from app.core.security import require_tenant_access
    
    @app.get("/api/v1/test-guard")
    def test_guard(tenant: str = Depends(require_tenant_access)):
        return {"access": "granted", "tenant": tenant}
        
    # Firm A accessing its own tenant (apex) -> 200 OK
    res_ok = client.get(
        "/api/v1/test-guard",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant": "apex"}
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["tenant"] == "apex"
    
    # Firm A accessing Firm B's tenant (tenant_b) -> MUST RETURN 403 FORBIDDEN!
    res_forbidden = client.get(
        "/api/v1/test-guard",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant": "tenant_b"}
    )
    assert res_forbidden.status_code == 403
    assert "not owned by Firm" in res_forbidden.json()["detail"]
