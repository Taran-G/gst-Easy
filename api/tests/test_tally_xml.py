from decimal import Decimal
import pytest
from app.services.tally_xml import (
    generate_purchase_voucher_xml,
    compute_voucher_guid,
    generate_tally_xml_batch
)

def test_tally_xml_zero_sum_balanced():
    inv = {
        "invoice_number": "INV-2026-001",
        "number_norm": "INV-2026-001",
        "invoice_date": "2026-09-10",
        "fy": "2026-27",
        "taxable_amount": 10000.0,
        "cgst_amount": 900.0,
        "sgst_amount": 900.0,
        "igst_amount": 0.0,
        "round_off": 0.0,
        "total_amount": 11800.0,
        "supplier": {
            "gstin": "06AABCS1234S1Z4",
            "name": "Sharma Steels",
            "tally_ledger": "Sharma Steels (Sundry Creditors)"
        }
    }
    
    xml = generate_purchase_voucher_xml("apex", inv)
    assert "<VOUCHER" in xml
    assert "<PARTYLEDGERNAME>Sharma Steels (Sundry Creditors)</PARTYLEDGERNAME>" in xml
    assert "<AMOUNT>11800.00</AMOUNT>" in xml
    assert "<AMOUNT>-10000.00</AMOUNT>" in xml
    assert "<AMOUNT>-900.00</AMOUNT>" in xml

def test_tally_xml_unbalanced_rejected():
    """Asserts that sum != 0.00 raises ValueError (FR-TAL-1)."""
    inv = {
        "invoice_number": "INV-BAD",
        "number_norm": "INV-BAD",
        "invoice_date": "2026-09-10",
        "fy": "2026-27",
        "taxable_amount": 10000.0,
        "cgst_amount": 900.0,
        "sgst_amount": 900.0,
        "igst_amount": 0.0,
        "round_off": 0.0,
        "total_amount": 12500.0, # Unbalanced! Stated 12500 vs 11800
        "supplier": {"gstin": "06AABCS1234S1Z4", "name": "Sharma Steels"}
    }
    
    with pytest.raises(ValueError) as exc:
        generate_purchase_voucher_xml("apex", inv)
    assert "Unbalanced Tally voucher" in str(exc.value)

def test_tally_guid_stable_idempotency():
    """Same tenant, supplier, norm_number, and fy produces identical stable GUID."""
    guid1 = compute_voucher_guid("apex", "06AABCS1234S1Z4", "INV-2026-001", "2026-27")
    guid2 = compute_voucher_guid("apex", "06AABCS1234S1Z4", "INV-2026-001", "2026-27")
    assert guid1 == guid2
    
    # Different invoice yields different GUID
    guid3 = compute_voucher_guid("apex", "06AABCS1234S1Z4", "INV-2026-002", "2026-27")
    assert guid1 != guid3

def test_tally_xml_multi_rate_support():
    """Validates that multi-rate line items generate distinct purchase & tax ledger debit entries."""
    inv = {
        "invoice_number": "INV-MULTI-01",
        "number_norm": "INV-MULTI-01",
        "invoice_date": "2026-09-15",
        "fy": "2026-27",
        "taxable_amount": 40000.0,
        "cgst_amount": 3150.0,
        "sgst_amount": 3150.0,
        "igst_amount": 0.0,
        "round_off": 0.0,
        "total_amount": 46300.0,
        "supplier": {"gstin": "06AABCS1234S1Z4", "name": "Sharma Steels"},
        "lines": [
            {
                "description": "HR Steel Coil 2.5mm",
                "gst_rate": 18.0,
                "taxable_value": 25000.0,
                "cgst_amount": 2250.0,
                "sgst_amount": 2250.0,
                "igst_amount": 0.0
            },
            {
                "description": "CR Steel Sheet",
                "gst_rate": 12.0,
                "taxable_value": 15000.0,
                "cgst_amount": 900.0,
                "sgst_amount": 900.0,
                "igst_amount": 0.0
            }
        ]
    }

    xml = generate_purchase_voucher_xml("apex", inv)
    assert "<PARTYLEDGERNAME>Sharma Steels (Sundry Creditors)</PARTYLEDGERNAME>" in xml
    assert "<AMOUNT>46300.00</AMOUNT>" in xml
    assert "<LEDGERNAME>Purchase GST 18%</LEDGERNAME>" in xml
    assert "<AMOUNT>-25000.00</AMOUNT>" in xml
    assert "<LEDGERNAME>Purchase GST 12%</LEDGERNAME>" in xml
    assert "<AMOUNT>-15000.00</AMOUNT>" in xml
    assert "<LEDGERNAME>Input CGST @ 9%</LEDGERNAME>" in xml
    assert "<AMOUNT>-2250.00</AMOUNT>" in xml
    assert "<LEDGERNAME>Input CGST @ 6%</LEDGERNAME>" in xml
    assert "<AMOUNT>-900.00</AMOUNT>" in xml

def test_tally_xml_party_ledger_pattern():
    """Validates custom party ledger pattern formatting."""
    inv = {
        "invoice_number": "INV-CUSTOM-01",
        "invoice_date": "2026-09-10",
        "taxable_amount": 1000.0,
        "cgst_amount": 90.0,
        "sgst_amount": 90.0,
        "igst_amount": 0.0,
        "total_amount": 1180.0,
        "supplier": {"name": "Apex Auto Parts", "gstin": "06AAACA1234A1ZO"}
    }
    config = {"party_ledger_pattern": "{name} - {gstin}"}
    xml = generate_purchase_voucher_xml("apex", inv, tally_config=config)
    assert "<PARTYLEDGERNAME>Apex Auto Parts - 06AAACA1234A1ZO</PARTYLEDGERNAME>" in xml

