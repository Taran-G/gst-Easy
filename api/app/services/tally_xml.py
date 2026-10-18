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
    purchase_ledger_name = config.get("purchase_ledger", "Purchase GST 18%")
    cgst_ledger_name = config.get("cgst_ledger", "Input CGST @ 9%")
    sgst_ledger_name = config.get("sgst_ledger", "Input SGST @ 9%")
    igst_ledger_name = config.get("igst_ledger", "Input IGST @ 18%")
    roundoff_ledger_name = config.get("roundoff_ledger", "Round Off")

    supplier = invoice.get("supplier", {})
    party_ledger = supplier.get("tally_ledger") or f"{supplier.get('name', 'Vendor')} (Sundry Creditors)"
    
    inv_num_norm = invoice.get("number_norm") or invoice.get("invoice_number", "")
    fy = invoice.get("fy", "2026-27")
    guid = compute_voucher_guid(tenant_id, supplier.get("gstin", ""), inv_num_norm, fy)
    vch_date = format_tally_date(invoice.get("invoice_date", "2026-09-10"))

    # Track amounts with Decimal for zero-sum assertion
    amounts: List[Decimal] = []

    total_amt = Decimal(str(invoice.get("total_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    taxable_amt = Decimal(str(invoice.get("taxable_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cgst_amt = Decimal(str(invoice.get("cgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sgst_amt = Decimal(str(invoice.get("sgst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    igst_amt = Decimal(str(invoice.get("igst_amount", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    round_off = Decimal(str(invoice.get("round_off", 0.0))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Party ledger is credit: Positive in Tally
    amounts.append(total_amt)

    # Expense and Tax are debits: Negative in Tally
    amounts.append(-taxable_amt)
    if cgst_amt > Decimal("0.00"):
        amounts.append(-cgst_amt)
    if sgst_amt > Decimal("0.00"):
        amounts.append(-sgst_amt)
    if igst_amt > Decimal("0.00"):
        amounts.append(-igst_amt)
    if round_off != Decimal("0.00"):
        amounts.append(-round_off)

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

    # 1. Party Ledger Entry (Credit)
    party_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(party_entry, "LEDGERNAME").text = party_ledger
    ET.SubElement(party_entry, "ISDEEMEDPOSITIVE").text = "No"
    ET.SubElement(party_entry, "AMOUNT").text = f"{total_amt:.2f}"

    # 2. Purchase / Expense Ledger Entry (Debit)
    purch_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(purch_entry, "LEDGERNAME").text = purchase_ledger_name
    ET.SubElement(purch_entry, "ISDEEMEDPOSITIVE").text = "Yes"
    ET.SubElement(purch_entry, "AMOUNT").text = f"{-taxable_amt:.2f}"

    # 3. CGST Entry (Debit)
    if cgst_amt > Decimal("0.00"):
        cgst_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(cgst_entry, "LEDGERNAME").text = cgst_ledger_name
        ET.SubElement(cgst_entry, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(cgst_entry, "AMOUNT").text = f"{-cgst_amt:.2f}"

    # 4. SGST Entry (Debit)
    if sgst_amt > Decimal("0.00"):
        sgst_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(sgst_entry, "LEDGERNAME").text = sgst_ledger_name
        ET.SubElement(sgst_entry, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(sgst_entry, "AMOUNT").text = f"{-sgst_amt:.2f}"

    # 5. IGST Entry (Debit)
    if igst_amt > Decimal("0.00"):
        igst_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(igst_entry, "LEDGERNAME").text = igst_ledger_name
        ET.SubElement(igst_entry, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(igst_entry, "AMOUNT").text = f"{-igst_amt:.2f}"

    # 6. Round off Entry (if any)
    if round_off != Decimal("0.00"):
        ro_entry = ET.SubElement(voucher, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(ro_entry, "LEDGERNAME").text = roundoff_ledger_name
        ET.SubElement(ro_entry, "ISDEEMEDPOSITIVE").text = "Yes" if round_off > 0 else "No"
        ET.SubElement(ro_entry, "AMOUNT").text = f"{-round_off:.2f}"

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
