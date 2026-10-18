import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.core.rules import get_rules

GSTIN_REGEX = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

class ValidationIssue(BaseModel):
    code: str  # MATH_MISMATCH, GSTIN_INVALID, STATE_CODE_INVALID, TAX_TYPE_MISMATCH, WRONG_BUYER_GSTIN, DUPLICATE_INVOICE, DATE_FUTURE, DATE_OLD, RATE_NOT_ALLOWED, LOW_CONFIDENCE, TDS_SUGGESTED
    severity: str  # BLOCK | WARN | INFO
    field: Optional[str] = None
    message: str

class ValidationReport(BaseModel):
    is_valid: bool  # True if no BLOCK issues
    issues: List[ValidationIssue]
    normalized_invoice_number: str
    fy: str

def gstin_checksum_ok(gstin: Optional[str]) -> bool:
    """Validates 15-character GSTIN regex and mod-36 checksum."""
    if not gstin or not isinstance(gstin, str):
        return False
    gstin = gstin.strip().upper()
    if not GSTIN_REGEX.match(gstin):
        return False
    
    total = 0
    for i, c in enumerate(gstin[:14]):
        v = GSTIN_CHARS.index(c) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    expected = GSTIN_CHARS[(36 - total % 36) % 36]
    return expected == gstin[14]

def state_code_valid(code: Optional[str]) -> bool:
    """Validates 2-digit Indian GST state code against rules.yaml."""
    if not code:
        return False
    code_str = str(code).strip().zfill(2)
    rules = get_rules()
    return code_str in rules.state_codes

def normalise_invoice_number(s: Optional[str]) -> str:
    """Upper-case, strip spaces and leading zeros for robust deduplication and Tally matching."""
    if not s:
        return ""
    clean = re.sub(r"\s+", "", str(s)).upper()
    # Strip leading zeroes from numeric parts while preserving structure
    clean = re.sub(r"^0+", "", clean)
    return clean or "0"

def fy_of(d: Any) -> str:
    """Calculates Indian Financial Year (Apr-Mar) from a date."""
    if isinstance(d, str):
        # Parse ISO YYYY-MM-DD
        dt = datetime.strptime(d[:10], "%Y-%m-%d").date()
    elif isinstance(d, datetime):
        dt = d.date()
    elif isinstance(d, date):
        dt = d
    else:
        raise ValueError(f"Invalid date format: {d}")
        
    year = dt.year
    if dt.month >= 4:
        return f"{year}-{str(year + 1)[-2:]}"
    else:
        return f"{year - 1}-{str(year)[-2:]}"

def to_decimal(val: Any) -> Decimal:
    if val is None or val == "":
        return Decimal("0.00")
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def check_math(invoice_data: Dict[str, Any]) -> List[ValidationIssue]:
    """Pure Decimal arithmetic validation for line items and invoice totals."""
    issues: List[ValidationIssue] = []
    rules = get_rules()
    tolerance = Decimal(str(rules.tolerance_rupees))
    
    lines = invoice_data.get("lines") or []
    computed_taxable = Decimal("0.00")
    computed_cgst = Decimal("0.00")
    computed_sgst = Decimal("0.00")
    computed_igst = Decimal("0.00")
    
    for idx, line in enumerate(lines, start=1):
        qty = line.get("qty")
        rate = line.get("rate")
        line_taxable = to_decimal(line.get("taxable_value"))
        
        # Check qty * rate = taxable if both are provided
        if qty is not None and rate is not None:
            expected_line_taxable = (Decimal(str(qty)) * Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if abs(expected_line_taxable - line_taxable) > Decimal("0.05"):
                issues.append(ValidationIssue(
                    code="MATH_MISMATCH",
                    severity="BLOCK",
                    field=f"lines[{idx}].taxable_value",
                    message=f"Line {idx}: Qty ({qty}) × Rate ({rate}) = ₹{expected_line_taxable}, but got ₹{line_taxable}"
                ))
                
        computed_taxable += line_taxable
        computed_cgst += to_decimal(line.get("cgst_amount", 0.0))
        computed_sgst += to_decimal(line.get("sgst_amount", 0.0))
        computed_igst += to_decimal(line.get("igst_amount", 0.0))
        
    invoice_taxable = to_decimal(invoice_data.get("taxable_amount"))
    invoice_cgst = to_decimal(invoice_data.get("cgst_amount", 0.0))
    invoice_sgst = to_decimal(invoice_data.get("sgst_amount", 0.0))
    invoice_igst = to_decimal(invoice_data.get("igst_amount", 0.0))
    round_off = to_decimal(invoice_data.get("round_off", 0.0))
    total_amount = to_decimal(invoice_data.get("total_amount"))
    
    # Check sum of taxable lines matches taxable_amount if lines exist
    if lines and abs(computed_taxable - invoice_taxable) > Decimal("0.05"):
        issues.append(ValidationIssue(
            code="MATH_MISMATCH",
            severity="BLOCK",
            field="taxable_amount",
            message=f"Sum of item taxable values (₹{computed_taxable}) does not match invoice taxable amount (₹{invoice_taxable})"
        ))
        
    # Check total arithmetic: taxable + taxes + round_off = total
    computed_total = invoice_taxable + invoice_cgst + invoice_sgst + invoice_igst + round_off
    diff = abs(computed_total - total_amount)
    if diff > tolerance:
        issues.append(ValidationIssue(
            code="MATH_MISMATCH",
            severity="BLOCK",
            field="total_amount",
            message=f"Grand total mismatch: Taxable (₹{invoice_taxable}) + Taxes (₹{invoice_cgst + invoice_sgst + invoice_igst}) + Round-off (₹{round_off}) = ₹{computed_total}, but stated total is ₹{total_amount} (diff: ₹{diff})"
        ))
        
    return issues

def check_tax_type(
    supplier_state: str,
    place_of_supply: str,
    cgst: Decimal,
    sgst: Decimal,
    igst: Decimal
) -> List[ValidationIssue]:
    """Validates Intra-state (CGST+SGST) vs Inter-state (IGST) tax type rules."""
    issues: List[ValidationIssue] = []
    supp_st = str(supplier_state).strip().zfill(2)
    pos_st = str(place_of_supply).strip().zfill(2)
    
    is_intrastate = (supp_st == pos_st)
    
    if is_intrastate:
        # Intra-state: CGST & SGST must be charged, IGST must be 0
        if igst > Decimal("0.01"):
            issues.append(ValidationIssue(
                code="TAX_TYPE_MISMATCH",
                severity="BLOCK",
                field="igst_amount",
                message=f"Intra-state supply (Supplier state {supp_st} = Place of supply {pos_st}) cannot charge IGST (₹{igst}). Must charge equal CGST and SGST."
            ))
        if cgst > Decimal("0.00") or sgst > Decimal("0.00"):
            if abs(cgst - sgst) > Decimal("0.05"):
                issues.append(ValidationIssue(
                    code="TAX_TYPE_MISMATCH",
                    severity="BLOCK",
                    field="cgst_amount",
                    message=f"CGST (₹{cgst}) and SGST (₹{sgst}) must be equal for intra-state supply."
                ))
    else:
        # Inter-state: IGST must be charged, CGST and SGST must be 0
        if cgst > Decimal("0.01") or sgst > Decimal("0.01"):
            issues.append(ValidationIssue(
                code="TAX_TYPE_MISMATCH",
                severity="BLOCK",
                field="cgst_amount",
                message=f"Inter-state supply (Supplier state {supp_st} ≠ Place of supply {pos_st}) cannot charge CGST/SGST. Must charge IGST."
            ))
            
    return issues

def validate_invoice(
    invoice: Dict[str, Any],
    tenant: Dict[str, Any],
    is_duplicate: bool = False
) -> ValidationReport:
    """
    Main deterministic validation pipeline.
    Pure Python, Decimal arithmetic, strictly adheres to rules.yaml.
    """
    issues: List[ValidationIssue] = []
    rules = get_rules()
    
    # 1. Normalise invoice number & calculate FY
    inv_raw = invoice.get("invoice_number", "")
    norm_inv_no = normalise_invoice_number(inv_raw)
    inv_date_str = invoice.get("invoice_date", "")
    
    try:
        fy = fy_of(inv_date_str)
    except Exception:
        fy = "2026-27"
        issues.append(ValidationIssue(
            code="DATE_INVALID",
            severity="BLOCK",
            field="invoice_date",
            message=f"Invalid invoice date format: '{inv_date_str}'"
        ))
        
    # 2. Duplicate invoice check
    if is_duplicate:
        issues.append(ValidationIssue(
            code="DUPLICATE_INVOICE",
            severity="BLOCK",
            field="invoice_number",
            message=f"Duplicate invoice: Supplier {invoice.get('supplier_gstin')} with Invoice No '{norm_inv_no}' already exists in FY {fy}."
        ))
        
    # 3. GSTIN checksum validation
    supp_gstin = invoice.get("supplier_gstin", "").strip().upper()
    if not gstin_checksum_ok(supp_gstin):
        issues.append(ValidationIssue(
            code="GSTIN_INVALID",
            severity="BLOCK",
            field="supplier_gstin",
            message=f"Supplier GSTIN '{supp_gstin}' is invalid (failed mod-36 checksum or format)."
        ))
        
    buyer_gstin = invoice.get("buyer_gstin", "").strip().upper()
    if not gstin_checksum_ok(buyer_gstin):
        issues.append(ValidationIssue(
            code="GSTIN_INVALID",
            severity="BLOCK",
            field="buyer_gstin",
            message=f"Buyer GSTIN '{buyer_gstin}' is invalid."
        ))
        
    # 4. State code validation
    supp_state = supp_gstin[:2] if len(supp_gstin) >= 2 else ""
    if not state_code_valid(supp_state):
        issues.append(ValidationIssue(
            code="STATE_CODE_INVALID",
            severity="BLOCK",
            field="supplier_gstin",
            message=f"Supplier GSTIN state code '{supp_state}' is not a valid Indian state code."
        ))
        
    pos = str(invoice.get("place_of_supply", "")).strip().zfill(2)
    if not state_code_valid(pos):
        issues.append(ValidationIssue(
            code="STATE_CODE_INVALID",
            severity="BLOCK",
            field="place_of_supply",
            message=f"Place of supply '{pos}' is not a valid Indian state code."
        ))
        
    # 5. Buyer GSTIN match check (ITC would be denied if billed to another entity)
    tenant_gstin = tenant.get("gstin", "").strip().upper()
    if buyer_gstin and tenant_gstin and buyer_gstin != tenant_gstin:
        issues.append(ValidationIssue(
            code="WRONG_BUYER_GSTIN",
            severity="BLOCK",
            field="buyer_gstin",
            message=f"Invoice billed to buyer GSTIN '{buyer_gstin}', but current client tenant GSTIN is '{tenant_gstin}'. ITC will be rejected by GSTN."
        ))
        
    # 6. Dates check
    if inv_date_str:
        try:
            inv_date = datetime.strptime(inv_date_str[:10], "%Y-%m-%d").date()
            today = date.today()
            if inv_date > today:
                issues.append(ValidationIssue(
                    code="DATE_FUTURE",
                    severity="BLOCK",
                    field="invoice_date",
                    message=f"Invoice date {inv_date} is in the future."
                ))
            elif (today - inv_date).days > 180:
                issues.append(ValidationIssue(
                    code="DATE_OLD",
                    severity="WARN",
                    field="invoice_date",
                    message=f"Invoice is {(today - inv_date).days} days old (exceeds 180 days - check Rule 37 reversal)."
                ))
        except ValueError:
            pass
            
    # 7. Math checks
    math_issues = check_math(invoice)
    issues.extend(math_issues)
    
    # 8. Tax type match check
    cgst = to_decimal(invoice.get("cgst_amount", 0.0))
    sgst = to_decimal(invoice.get("sgst_amount", 0.0))
    igst = to_decimal(invoice.get("igst_amount", 0.0))
    tax_type_issues = check_tax_type(supp_state, pos, cgst, sgst, igst)
    issues.extend(tax_type_issues)
    
    # 9. Rate sanity check
    allowed_rates = rules.gst_rates
    for idx, line in enumerate(invoice.get("lines") or [], start=1):
        line_rate = int(round(float(line.get("gst_rate", 0))))
        if line_rate not in allowed_rates:
            issues.append(ValidationIssue(
                code="RATE_NOT_ALLOWED",
                severity="BLOCK",
                field=f"lines[{idx}].gst_rate",
                message=f"Line {idx} GST rate {line_rate}% is not in statutory GST rates {allowed_rates}."
            ))
            
    # 10. Confidence threshold check
    confidences = invoice.get("confidences") or {}
    thresh = rules.confidence_threshold
    for field, conf in confidences.items():
        if conf < thresh:
            sev = "BLOCK" if field in ["supplier_gstin", "invoice_number", "total_amount"] else "WARN"
            issues.append(ValidationIssue(
                code="LOW_CONFIDENCE",
                severity=sev,
                field=field,
                message=f"Field '{field}' extraction confidence ({conf:.2f}) is below threshold ({thresh})."
            ))
            
    has_blocking = any(i.severity == "BLOCK" for i in issues)
    
    return ValidationReport(
        is_valid=not has_blocking,
        issues=issues,
        normalized_invoice_number=norm_inv_no,
        fy=fy
    )
