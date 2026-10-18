import json
from pathlib import Path
import pytest
from app.services.validate import validate_invoice
from app.core.config import settings

APEX_TENANT = {
    "id": "apex",
    "name": "Apex Auto Parts",
    "gstin": "06AAACA1234A1ZO",
    "state_code": "06"
}

GOLDEN_DIR = Path(settings.FIXTURES_DIR) / "bills" / "golden"

def load_fixture(name: str):
    with open(GOLDEN_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)

def test_fixture_1_clean_intrastate():
    data = load_fixture("clean_intrastate")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is True
    assert len([i for i in report.issues if i.severity == "BLOCK"]) == 0

def test_fixture_2_clean_interstate():
    data = load_fixture("clean_interstate")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is True
    assert len([i for i in report.issues if i.severity == "BLOCK"]) == 0

def test_fixture_3_math_error():
    data = load_fixture("math_error")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is False
    codes = [i.code for i in report.issues if i.severity == "BLOCK"]
    assert "MATH_MISMATCH" in codes

def test_fixture_4_bad_gstin():
    data = load_fixture("bad_gstin")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is False
    codes = [i.code for i in report.issues if i.severity == "BLOCK"]
    assert "GSTIN_INVALID" in codes

def test_fixture_5_wrong_tax_type():
    data = load_fixture("wrong_tax_type")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is False
    codes = [i.code for i in report.issues if i.severity == "BLOCK"]
    assert "TAX_TYPE_MISMATCH" in codes

def test_fixture_6_wrong_buyer_gstin():
    data = load_fixture("wrong_buyer_gstin")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    assert report.is_valid is False
    codes = [i.code for i in report.issues if i.severity == "BLOCK"]
    assert "WRONG_BUYER_GSTIN" in codes

def test_fixture_7_duplicate_invoice():
    data = load_fixture("duplicate_of_1")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=True)
    assert report.is_valid is False
    codes = [i.code for i in report.issues if i.severity == "BLOCK"]
    assert "DUPLICATE_INVOICE" in codes

def test_fixture_8_unknown_supplier():
    data = load_fixture("unknown_supplier")
    report = validate_invoice(data, APEX_TENANT, is_duplicate=False)
    # The invoice fields themselves are mathematically and structurally valid
    assert report.is_valid is True
