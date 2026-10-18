import io
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.seed import seed_database
from app.adapters.llm_gemini import _extract_from_pdf_heuristics

client = TestClient(app)

def test_production_whatsapp_webhook_verification():
    # Valid challenge
    res = client.get("/api/v1/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.challenge": "1122334455",
        "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN
    })
    assert res.status_code == 200
    assert res.text == "1122334455"

    # Invalid token rejected
    res_bad = client.get("/api/v1/webhooks/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.challenge": "1122334455",
        "hub.verify_token": "wrong-token"
    })
    assert res_bad.status_code == 403

def test_production_whatsapp_webhook_meta_payload():
    seed_database(reset=True)
    
    meta_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "biz_123",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.test001",
                                    "timestamp": "1729240000",
                                    "type": "text",
                                    "text": {"body": "Invoice submission"}
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    
    res = client.post("/api/v1/webhooks/whatsapp", json=meta_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["routed_tenant"] == "apex"

def test_production_multipart_upload_and_extension_validation():
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # 1. Reject invalid file format (.exe)
    fake_exe = io.BytesIO(b"MZ\x90\x00executable")
    bad_res = client.post(
        "/api/v1/ingest/upload",
        files={"file": ("malicious.exe", fake_exe, "application/octet-stream")},
        headers=headers
    )
    assert bad_res.status_code == 400
    assert "Unsupported file format" in bad_res.json()["detail"]

    # 2. Upload valid PDF
    pdf_path = Path(settings.FIXTURES_DIR) / "bills" / "clean_intrastate.pdf"
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        up_res = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("real_invoice.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            headers=headers
        )
        assert up_res.status_code == 200
        assert "invoice_id" in up_res.json()
        assert up_res.json()["state"] in ["READY", "BLOCKED", "MASTER_REQUEST"]

def test_production_timing_header():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert "X-Process-Time" in res.headers
    assert res.headers["X-Process-Time"].endswith("s")

def test_production_tally_sync_direct_fallback():
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # Simulate bill to approve
    sim_res = client.post("/api/v1/ingest/simulate?fixture_name=clean_interstate", headers=headers)
    inv_id = sim_res.json()["invoice_id"]
    client.post(f"/api/v1/invoices/{inv_id}/approve", headers=headers)

    # Sync to Tally (when Tally not running on localhost:9000, returns exported_file gracefully)
    sync_res = client.post("/api/v1/tally/sync-direct", json={"invoice_ids": [inv_id]}, headers=headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["status"] in ["synced", "exported_file"]
