import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from xml.dom import minidom

NAMESPACE_TALLY = uuid.NAMESPACE_DNS

def compute_voucher_guid(tenant_id: str, supplier_gstin: str, invoice_number_norm: str, fy: str) -> str:
    seed = f"{tenant_id}|{supplier_gstin}|{invoice_number_norm}|{fy}"
    return str(uuid.uuid5(NAMESPACE_TALLY, seed))

def format_tally_date(iso_date: str) -> str:
    """Formats ISO YYYY-MM-DD into Tally YYYYMMDD format."""
    dt = datetime.strptime(iso_date[:10], "%Y-%m-%d")
    return dt.strftime("%Y%m%d")

def generate_purchase_voucher_xml(
    tenant_id: str,
    invoice: Dict[str, Any],
    tally_config: Optional[Dict[str, str]] = None
) -> str:
    """
    Generates a zero-sum TallyPrime Purchase Voucher XML.
    Party ledger: Positive amount (Credit), ISDEEMEDPOSITIVE=No.
    Expense and tax ledgers: Negative amount (Debit), ISDEEMEDPOSITIVE=Yes.
    Strictly asserts sum(amounts) == Decimal('0.00').
    """
    config = tally_config or {}
    purchase_ledger_default = config.get("purchase_ledger", "Purchase GST 18%")
    purchase_template = config.get("purchase_ledger_template", "Purchase GST {rate}%")
    cgst_ledger_name = config.get("cgst_ledger", "Input CGST @ 9%")
    sgst_ledger_name = config.get("sgst_ledger", "Input SGST @ 9%")
    igst_ledger_name = config.get("igst_ledger", "Input IGST @ 18%")
    roundoff_ledger_name = config.get("roundoff_ledger", "Round Off")

    supplier = invoice.get("supplier", {})
    party_pattern = config.get("party_ledger_pattern")
    
    if supplier.get("tally_ledger"):
        party_ledger = supplier["tally_ledger"]
    elif party_pattern:
        party_ledger = party_pattern.format(
            name=supplier.get("name", "Vendor"),
            legal_name=supplier.get("legal_name", supplier.get("name", "Vendor")),
            gstin=supplier.get("gstin", "")
        )
    else:
        party_ledger = f"{supplier.get('name', 'Vendor')} (Sundry Creditors)"
    
    inv_num_norm = invoice.get("number_norm") or invoice.get("invoice_number", "")
    fy = invoice.get("fy", "2026-27")
    guid = compute_voucher_guid(tenant_id, supplier.get("gstin", ""), inv_num_norm, fy)
    vch_date = format_tally_date(invoice.get("invoice_date", "2026-09-10"))

    # Track ledger allocations for zero-sum assertion
    # Each entry: (ledger_name, is_credit_bool, decimal_amount)
    ledger_entries: List[tuple] = []
    amounts: List[Decimal] = []

    total_amt = Decimal(str(invoice.get("total_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    round_off = Decimal(str(invoice.get("round_off", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Party ledger is credit: Positive in Tally
    amounts.append(total_amt)
    ledger_entries.append((party_ledger, "No", total_amt))

    lines = invoice.get("lines", [])
    has_multi_rate_lines = bool(lines and len({l.get("gst_rate") for l in lines if "gst_rate" in l}) > 1)

    if has_multi_rate_lines:
        # Group lines by rate
        from collections import defaultdict
        rate_taxable = defaultdict(Decimal)
        rate_cgst = defaultdict(Decimal)
        rate_sgst = defaultdict(Decimal)
        rate_igst = defaultdict(Decimal)

        for l in lines:
            r = int(float(l.get("gst_rate", 18.0)))
            t_val = Decimal(str(l.get("taxable_value", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            c_val = Decimal(str(l.get("cgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            s_val = Decimal(str(l.get("sgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            i_val = Decimal(str(l.get("igst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rate_taxable[r] += t_val
            rate_cgst[r] += c_val
            rate_sgst[r] += s_val
            rate_igst[r] += i_val

        for r, t_val in rate_taxable.items():
            if t_val > Decimal("0.00"):
                l_name = "Exempt Purchase" if r == 0 else purchase_template.format(rate=r)
                amounts.append(-t_val)
                ledger_entries.append((l_name, "Yes", -t_val))

        for r, c_val in rate_cgst.items():
            if c_val > Decimal("0.00"):
                half_r = r / 2
                half_r_str = f"{half_r:g}"
                l_name = f"Input CGST @ {half_r_str}%"
                amounts.append(-c_val)
                ledger_entries.append((l_name, "Yes", -c_val))

        for r, s_val in rate_sgst.items():
            if s_val > Decimal("0.00"):
                half_r = r / 2
                half_r_str = f"{half_r:g}"
                l_name = f"Input SGST @ {half_r_str}%"
                amounts.append(-s_val)
                ledger_entries.append((l_name, "Yes", -s_val))

        for r, i_val in rate_igst.items():
            if i_val > Decimal("0.00"):
                l_name = f"Input IGST @ {r}%"
                amounts.append(-i_val)
                ledger_entries.append((l_name, "Yes", -i_val))

    else:
        # Single-rate or header-level fallback
        taxable_amt = Decimal(str(invoice.get("taxable_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst_amt = Decimal(str(invoice.get("cgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst_amt = Decimal(str(invoice.get("sgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        igst_amt = Decimal(str(invoice.get("igst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        amounts.append(-taxable_amt)
        ledger_entries.append((purchase_ledger_default, "Yes", -taxable_amt))

        if cgst_amt > Decimal("0.00"):
            amounts.append(-cgst_amt)
            ledger_entries.append((cgst_ledger_name, "Yes", -cgst_amt))
        if sgst_amt > Decimal("0.00"):
            amounts.append(-sgst_amt)
            ledger_entries.append((sgst_ledger_name, "Yes", -sgst_amt))
        if igst_amt > Decimal("0.00"):
            amounts.append(-igst_amt)
            ledger_entries.append((igst_ledger_name, "Yes", -igst_amt))

    if round_off != Decimal("0.00"):
        amounts.append(-round_off)
        ledger_entries.append((roundoff_ledger_name, "Yes" if round_off > 0 else "No", -round_off))

    # ZERO-SUM ASSERTION (SRS FR-TAL-1)
    checksum = sum(amounts)
    if checksum != Decimal("0.00"):
        raise ValueError(
            f"Unbalanced Tally voucher for invoice {invoice.get('invoice_number')}: "
            f"Debits and credits sum to {checksum}, expected 0.00. Export refused."
        )

    # Build XML tree
    voucher = ET.Element("VOUCHER", {"VCHTYPE": "Purchase", "ACTION": "Create", "OBJVIEW": "Invoice Voucher View"})
    ET.SubElement(voucher, "DATE").text = vch_date
    ET.SubElement(voucher, "GUID").text = guid
    ET.SubElement(voucher, "VOUCHERTYPENAME").text = "Purchase"
    ET.SubElement(voucher, "VOUCHERNUMBER").text = invoice.get("invoice_number", "")
    ET.SubElement(voucher, "REFERENCE").text = invoice.get("invoice_number", "")
    ET.SubElement(voucher, "PARTYLEDGERNAME").text = party_ledger
    ET.SubElement(voucher, "PERSISTEDVIEW").text = "Invoice Voucher View"

    for l_name, deemed_pos, amt in ledger_entries:
        entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(entry, "LEDGERNAME").text = l_name
        ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = deemed_pos
        ET.SubElement(entry, "AMOUNT").text = f"{amt:.2f}"

    raw_xml = ET.tostring(voucher, encoding="utf-8")
    return raw_xml.decode("utf-8")

def generate_tally_xml_batch(tenant_id: str, invoices: List[Dict[str, Any]], tally_config: Optional[Dict[str, str]] = None) -> str:
    """Wraps vouchers into standard Tally envelope."""
    envelope = ET.Element("ENVELOPE")
    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    
    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")
    req_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(req_desc, "REPORTNAME").text = "All Masters"
    
    tally_msg = ET.SubElement(import_data, "REQUESTDATA")
    
    for inv in invoices:
        vch_xml = generate_purchase_voucher_xml(tenant_id, inv, tally_config)
        vch_elem = ET.fromstring(vch_xml)
        msg_wrapper = ET.SubElement(tally_msg, "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
        msg_wrapper.append(vch_elem)
        
    rough_string = ET.tostring(envelope, "utf-8")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")
