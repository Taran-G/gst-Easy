from decimal import Decimal
import pytest
from app.services.validate import (
    gstin_checksum_ok,
    state_code_valid,
    normalise_invoice_number,
    fy_of,
    check_math,
    check_tax_type,
    validate_invoice
)

def test_gstin_checksum():
    # Valid GSTINs
    assert gstin_checksum_ok("06AAACA1234A1ZO") is True
    assert gstin_checksum_ok("24AAACG5678G1ZK") is True
    assert gstin_checksum_ok("06AABCS1234S1Z4") is True
    assert gstin_checksum_ok("07AABCA5678A1ZX") is True
    
    # Invalid GSTINs (bad check char, bad length, bad regex)
    assert gstin_checksum_ok("06AAACA1234A1Z9") is False
    assert gstin_checksum_ok("INVALIDGSTIN") is False
    assert gstin_checksum_ok("") is False
    assert gstin_checksum_ok(None) is False

def test_state_code():
    assert state_code_valid("06") is True  # Haryana
    assert state_code_valid("24") is True  # Gujarat
    assert state_code_valid("07") is True  # Delhi
    assert state_code_valid("99") is False # Invalid

def test_normalise_invoice_number():
    assert normalise_invoice_number(" INV-2026-001 ") == "INV-2026-001"
    assert normalise_invoice_number("000456") == "456"
    assert normalise_invoice_number("000INV/01") == "INV/01"
    assert normalise_invoice_number("ab-12") == "AB-12"

def test_fy_of():
    assert fy_of("2026-09-15") == "2026-27"
    assert fy_of("2026-04-01") == "2026-27"
    assert fy_of("2027-03-31") == "2026-27"
    assert fy_of("2026-01-15") == "2025-26"

def test_check_math_clean():
    inv = {
        "taxable_amount": 10000.0,
        "cgst_amount": 900.0,
        "sgst_amount": 900.0,
        "igst_amount": 0.0,
        "round_off": 0.0,
        "total_amount": 11800.0,
        "lines": [
            {"qty": 2.0, "rate": 5000.0, "taxable_value": 10000.0, "cgst_amount": 900.0, "sgst_amount": 900.0, "igst_amount": 0.0}
        ]
    }
    issues = check_math(inv)
    assert len(issues) == 0

def test_check_math_error():
    inv = {
        "taxable_amount": 10000.0,
        "cgst_amount": 900.0,
        "sgst_amount": 900.0,
        "igst_amount": 0.0,
        "round_off": 0.0,
        "total_amount": 12500.0,  # Wrong! Should be 11800
        "lines": [
            {"qty": 2.0, "rate": 5000.0, "taxable_value": 10000.0, "cgst_amount": 900.0, "sgst_amount": 900.0, "igst_amount": 0.0}
        ]
    }
    issues = check_math(inv)
    assert any(i.code == "MATH_MISMATCH" and i.severity == "BLOCK" for i in issues)

def test_check_tax_type_mismatch():
    # Supplier 06, POS 06 (Intra-state) but IGST charged
    issues = check_tax_type("06", "06", Decimal("0.00"), Decimal("0.00"), Decimal("1800.00"))
    assert any(i.code == "TAX_TYPE_MISMATCH" for i in issues)

    # Supplier 07, POS 06 (Inter-state) but CGST/SGST charged
    issues_inter = check_tax_type("07", "06", Decimal("900.00"), Decimal("900.00"), Decimal("0.00"))
    assert any(i.code == "TAX_TYPE_MISMATCH" for i in issues_inter)
