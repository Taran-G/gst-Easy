import json
from pathlib import Path
import pytest
from app.graph.client import tenant_graph
from app.services.reconcile import import_gstr2b_entries, run_reconciliation
from app.core.config import settings

def test_gstr2b_reconciliation_counts():
    tenant_id = "test_recon_tenant"
    period = "092026"
    try:
        tenant_graph(tenant_id).delete()
    except Exception:
        pass
    g = tenant_graph(tenant_id)
    
    # 1. Seed vendors with filing frequencies
    g.query(
        """
        MERGE (s:Vendor {gstin: "06AABCS1234S1Z4"})
        SET s.legal_name = "Sharma Steels", s.filing_freq = "Monthly", s.gstin_status = "Active"
        
        MERGE (a:Vendor {gstin: "07AABCA5678A1ZX"})
        SET a.legal_name = "ABC Traders", a.filing_freq = "QRMP", a.gstin_status = "Active"
        
        MERGE (d:Vendor {gstin: "06AABCD9012D1Z6"})
        SET d.legal_name = "Delta Fasteners", d.filing_freq = "Monthly", d.gstin_status = "Suspended"
        """
    )
    
    # 2. Seed books invoices:
    # 5 Exact matches: INV-2026-001, ABC-982, INV-2026-010, INV-2026-011, ABC-012
    # 1 Matched with diff: INV-2026-015 (taxable 10000 vs 9999 in 2B)
    # 2 Missing in 2B: INV-2026-020, INV-2026-021
    # 1 Timing gap: ABC-104 (ABC Traders is QRMP)
    # Total books invoices = 9
    
    invoices_data = [
        ("06AABCS1234S1Z4", "INV-2026-001", "2026-09-10", 10000.0, 1800.0),
        ("07AABCA5678A1ZX", "ABC-982", "2026-09-12", 20000.0, 3600.0),
        ("06AABCS1234S1Z4", "INV-2026-010", "2026-09-14", 15000.0, 2700.0),
        ("06AABCS1234S1Z4", "INV-2026-011", "2026-09-15", 8000.0, 1440.0),
        ("07AABCA5678A1ZX", "ABC-012", "2026-09-18", 12000.0, 2160.0),
        ("06AABCS1234S1Z4", "INV-2026-015", "2026-09-20", 10000.0, 1800.0), # Stated with diff in 2B
        ("06AABCS1234S1Z4", "INV-2026-020", "2026-09-22", 18000.0, 3240.0), # Missing
        ("06AABCD9012D1Z6", "INV-2026-021", "2026-09-23", 14000.0, 2520.0), # Missing
        ("07AABCA5678A1ZX", "ABC-104", "2026-09-24", 11000.0, 1980.0),      # QRMP Timing Gap
    ]
    
    for gstin, inv_no, inv_date, taxable, tax in invoices_data:
        g.query(
            """
            MATCH (v:Vendor {gstin: $gstin})
            CREATE (i:Invoice {
                id: $id,
                number: $inv_no,
                number_norm: $inv_no,
                date: $date,
                fy: "2026-27",
                taxable: $taxable,
                cgst: $cgst,
                sgst: $sgst,
                igst: 0.0,
                total: $total,
                state: "POSTED",
                hold_status: "NONE"
            })
            CREATE (v)-[:ISSUED]->(i)
            """,
            {
                "gstin": gstin,
                "id": f"inv_{inv_no}",
                "inv_no": inv_no,
                "date": inv_date,
                "taxable": taxable,
                "cgst": tax / 2,
                "sgst": tax / 2,
                "total": taxable + tax
            }
        )
        
    # 3. Import GSTR-2B fixture (includes the 5 exact, 1 diff, and GHOST-777)
    fixture_path = Path(settings.FIXTURES_DIR) / "gstr2b" / f"{period}.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        entries_2b = json.load(f)
        
    import_count = import_gstr2b_entries(tenant_id, period, entries_2b)
    assert import_count == len(entries_2b)
    
    # 4. Run reconciliation
    res = run_reconciliation(tenant_id, period, from_date="2026-09-01", to_date="2026-09-30")
    
    # Verify expected fixture counts per Implementation Plan P3 step 8:
    # 5 matched, 1 matched-with-difference, 2 missing, 1 timing gap, 1 ghost invoice
    counts = res["counts"]
    assert counts["matched"] == 5, f"Expected 5 matched, got {counts['matched']}"
    assert counts["matched_with_difference"] == 1, f"Expected 1 matched-with-difference, got {counts['matched_with_difference']}"
    assert counts["missing_in_2b"] == 2, f"Expected 2 missing in 2B, got {counts['missing_in_2b']}"
    assert counts["expected_timing_gap"] == 1, f"Expected 1 timing gap, got {counts['expected_timing_gap']}"
    assert counts["in_2b_not_in_books"] == 1, f"Expected 1 ghost invoice, got {counts['in_2b_not_in_books']}"
