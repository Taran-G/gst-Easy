from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.services.ingest import process_document
from app.services.risk import check_rule_37_aging
from app.graph.client import tenant_graph

client = TestClient(app)

def test_real_bill_1_multi_item_mixed_rate():
    tenant_id = "test_real_tenant_1"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    g.query("MERGE (t:Tenant {id: $id, gstin: '06AAACA1234A1ZO', state_code: '06'})", {"id": tenant_id})

    # Map Sharma Steels
    g.query(
        """
        MERGE (v:Vendor {gstin: '06AABCS1234S1Z4'})
        SET v.legal_name = 'Sharma Steels'
        MERGE (tl:TallyLedger {name: 'Sharma Steels (Sundry Creditors)'})
        MERGE (v)-[:MAPS_TO_LEDGER]->(tl)
        MERGE (si1:TallyStockItem {name: 'HR Steel Coil 2.5mm'})
        MERGE (si2:TallyStockItem {name: 'CR Steel Sheet'})
        """
    )

    pdf_path = str(Path(settings.FIXTURES_DIR) / "bills" / "multi_item_mixed_rate.pdf")
    res = process_document(tenant_id=tenant_id, file_path=pdf_path, source="upload", user_id="tester")

    assert res["is_valid"] is True
    assert res["state"] == "READY"
    assert res["taxable_amount"] == 40000.0
    assert res["total_amount"] == 46300.0
    assert len(res["lines"]) == 2
    assert res["cgst_amount"] == 3150.0
    assert res["sgst_amount"] == 3150.0

def test_real_bill_2_freight_and_negative_roundoff():
    tenant_id = "test_real_tenant_2"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    g.query("MERGE (t:Tenant {id: $id, gstin: '06AAACA1234A1ZO', state_code: '06'})", {"id": tenant_id})

    g.query(
        """
        MERGE (v:Vendor {gstin: '07AABCA5678A1ZX'})
        SET v.legal_name = 'ABC Traders'
        MERGE (tl:TallyLedger {name: 'ABC Traders (Sundry Creditors)'})
        MERGE (v)-[:MAPS_TO_LEDGER]->(tl)
        MERGE (si1:TallyStockItem {name: 'Bearing Units 6204'})
        MERGE (si2:TallyStockItem {name: 'Freight & Delivery Charges'})
        """
    )

    pdf_path = str(Path(settings.FIXTURES_DIR) / "bills" / "freight_roundoff_invoice.pdf")
    res = process_document(tenant_id=tenant_id, file_path=pdf_path, source="upload", user_id="tester")

    assert res["is_valid"] is True
    assert res["state"] == "READY"
    assert res["total_amount"] == 23541.0
    assert res["igst_amount"] == 3591.07
    assert res["round_off"] == -0.47

def test_real_bill_3_old_invoice_statutory_rule37_warning():
    tenant_id = "test_real_tenant_3"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    g.query("MERGE (t:Tenant {id: $id, gstin: '06AAACA1234A1ZO', state_code: '06'})", {"id": tenant_id})

    g.query(
        """
        MERGE (v:Vendor {gstin: '06AABCD9012D1Z6'})
        SET v.legal_name = 'Delta Fasteners'
        MERGE (tl:TallyLedger {name: 'Delta Fasteners (Sundry Creditors)'})
        MERGE (v)-[:MAPS_TO_LEDGER]->(tl)
        MERGE (si:TallyStockItem {name: 'High Tensile Bolts'})
        """
    )

    pdf_path = str(Path(settings.FIXTURES_DIR) / "bills" / "old_invoice_rule37.pdf")
    res = process_document(tenant_id=tenant_id, file_path=pdf_path, source="upload", user_id="tester")

    # Invoice is valid for review, but flagged with DATE_OLD warning
    assert res["is_valid"] is True
    date_old_issues = [i for i in res["validation_issues"] if i.get("code") == "DATE_OLD"]
    assert len(date_old_issues) >= 1
    assert "180 days" in date_old_issues[0]["message"]
