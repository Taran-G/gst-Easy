import io
import json
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

def test_invoices_multi_criteria_filtering():
    seed_database(reset=True)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # Simulate 2 bills: clean_intrastate (Sharma Steels) and freight_roundoff_invoice (ABC Traders)
    client.post("/api/v1/ingest/simulate?fixture_name=clean_intrastate", headers=headers)
    client.post("/api/v1/ingest/simulate?fixture_name=math_error", headers=headers)
    client.post("/api/v1/ingest/simulate?fixture_name=freight_roundoff_invoice", headers=headers)

    # 1. Base query returns metadata
    all_res = client.get("/api/v1/invoices", headers=headers)
    assert all_res.status_code == 200
    all_data = all_res.json()
    assert "available_suppliers" in all_data
    assert "status_counts" in all_data
    assert len(all_data["available_suppliers"]) >= 2

    # 2. Status filter
    blocked_res = client.get("/api/v1/invoices?status=BLOCKED", headers=headers)
    assert blocked_res.status_code == 200
    for inv in blocked_res.json()["invoices"]:
        assert inv["state"] == "BLOCKED"

    # 3. Search query
    search_res = client.get("/api/v1/invoices?search=Sharma", headers=headers)
    assert search_res.status_code == 200
    for inv in search_res.json()["invoices"]:
        assert "Sharma" in inv["supplier_name"] or "Sharma" in inv["supplier_gstin"] or "Sharma" in inv["number"]

    # 4. Supplier GSTIN filter
    abc_supplier = [s for s in all_data["available_suppliers"] if "ABC" in s["legal_name"]]
    if abc_supplier:
        sup_gstin = abc_supplier[0]["gstin"]
        sup_res = client.get(f"/api/v1/invoices?supplier_gstin={sup_gstin}", headers=headers)
        assert sup_res.status_code == 200
        for inv in sup_res.json()["invoices"]:
            assert inv["supplier_gstin"] == sup_gstin

def test_duplicate_submission_does_not_create_duplicate_invoice():
    seed_database(reset=True)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # Ingest clean_intrastate once
    r1 = client.post("/api/v1/ingest/simulate?fixture_name=clean_intrastate", headers=headers)
    assert r1.status_code == 200
    inv_id = r1.json()["invoice_id"]

    # Ingest clean_intrastate a second time (should be flagged duplicate and NOT create duplicate invoice)
    r2 = client.post("/api/v1/ingest/simulate?fixture_name=clean_intrastate", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["invoice_id"] == inv_id
    assert r2.json().get("is_duplicate") is True

    # Verify Inbox has only 1 invoice for INV-2026-001
    inbox_res = client.get("/api/v1/invoices?search=INV-2026-001", headers=headers)
    assert inbox_res.status_code == 200
    assert inbox_res.json()["count"] == 1
    assert len(inbox_res.json()["invoices"]) == 1

def test_bulk_approve_and_skip_blocked():
    seed_database(reset=True)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # Ingest clean bill and math error bill
    r1 = client.post("/api/v1/ingest/simulate?fixture_name=clean_intrastate", headers=headers)
    inv_ready = r1.json()["invoice_id"]

    r2 = client.post("/api/v1/ingest/simulate?fixture_name=math_error", headers=headers)
    inv_blocked = r2.json()["invoice_id"]

    # Bulk approve both
    bulk_res = client.post("/api/v1/invoices/bulk-approve", json={
        "invoice_ids": [inv_ready, inv_blocked]
    }, headers=headers)
    assert bulk_res.status_code == 200
    data = bulk_res.json()
    assert data["status"] == "success"
    assert data["approved_count"] == 1
    assert inv_ready in data["approved_ids"]
    assert data["skipped_count"] == 1
    assert data["skipped"][0]["id"] == inv_blocked

def test_gstr2b_portal_json_upload():
    seed_database(reset=True)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    # Standard GST portal format
    portal_2b = {
        "docdata": {
            "b2b": [
                {
                    "ctin": "07AAAAA0000A1Z5",
                    "cname": "Standard Steel Supplier",
                    "inv": [
                        {
                            "inum": "INV-PORTAL-99",
                            "idt": "2026-09-15",
                            "val": 118000.0,
                            "pos": "07",
                            "items": [
                                {
                                    "num": 1,
                                    "itmdet": {
                                        "txval": 100000.0,
                                        "rt": 18.0,
                                        "camt": 9000.0,
                                        "samt": 9000.0,
                                        "iamt": 0.0
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }

    import io
    file_bytes = io.BytesIO(json.dumps(portal_2b).encode("utf-8"))
    upload_res = client.post(
        "/api/v1/gstr2b/upload?period=092026",
        headers=headers,
        files={"file": ("gstr2b_092026.json", file_bytes, "application/json")}
    )
    assert upload_res.status_code == 200
    res_data = upload_res.json()
    assert res_data["status"] == "success"
    assert res_data["entries_imported"] >= 1

def test_export_reconciliation_audit_csv():
    seed_database(reset=True)
    login_res = client.post("/api/v1/auth/login", json={
        "email": "partner@demo",
        "password": "partner123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": "apex"}

    csv_res = client.get("/api/v1/reconcile/092026/export-csv", headers=headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    content = csv_res.content.decode("utf-8")
    assert "LEDGERGRAPH GSTR-2B RECONCILIATION REPORT" in content
    assert "MATCHED INVOICES" in content
    assert "MISSING IN GSTR-2B" in content
    assert "EXPECTED TIMING GAP" in content
