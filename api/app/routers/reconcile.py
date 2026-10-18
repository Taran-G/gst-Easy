import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel

from datetime import datetime, timezone
from app.adapters.gsp_live import LiveGspAdapter
from app.adapters.tally_bridge import TallyHttpBridge
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import tenant_graph
from app.services.reconcile import import_gstr2b_entries, run_reconciliation
from app.services.tally_xml import generate_tally_xml_batch

router = APIRouter(prefix="", tags=["reconcile"])

gsp_adapter = LiveGspAdapter()
tally_bridge = TallyHttpBridge()

def parse_gstr2b_uploaded_data(raw_data: Any, period: str) -> List[Dict[str, Any]]:
    entries = []
    
    # Format 1: GST Portal JSON format: { "data": { "docdata": { "b2b": [ { "ctin": ..., "cname": ..., "inv": [...] } ] } } }
    if isinstance(raw_data, dict):
        b2b_list = None
        if "data" in raw_data and isinstance(raw_data["data"], dict):
            docdata = raw_data["data"].get("docdata", {})
            b2b_list = docdata.get("b2b", [])
        elif "docdata" in raw_data and isinstance(raw_data["docdata"], dict):
            b2b_list = raw_data["docdata"].get("b2b", [])
        elif "b2b" in raw_data:
            b2b_list = raw_data["b2b"]
            
        if b2b_list is not None:
            for vendor in b2b_list:
                ctin = vendor.get("ctin") or vendor.get("supplier_gstin", "")
                cname = vendor.get("cname") or vendor.get("supplier_name", "Vendor")
                for inv in vendor.get("inv", []):
                    inum = inv.get("inum") or inv.get("invoice_number", "")
                    items = inv.get("items", [])
                    taxable = sum(float(item.get("txval", 0.0)) for item in items) if items else float(inv.get("val", 0.0))
                    tax = sum(
                        float(item.get("camt", 0.0)) + float(item.get("samt", 0.0)) + float(item.get("iamt", 0.0))
                        for item in items
                    ) if items else 0.0
                    
                    entries.append({
                        "supplier_gstin": ctin,
                        "supplier_name": cname,
                        "invoice_number": inum,
                        "taxable": taxable,
                        "tax": tax,
                        "ims_action": inv.get("itcavl", "Y")
                    })
            return entries
            
        # Format 2: Dict with "entries" list
        if "entries" in raw_data and isinstance(raw_data["entries"], list):
            return raw_data["entries"]

    # Format 3: Raw list of invoice entries
    if isinstance(raw_data, list):
        return raw_data

    return entries

class TallyExportRequest(BaseModel):
    invoice_ids: List[str]

@router.post("/gstr2b/import")
def import_gstr2b(
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Imports GSTR-2B entries for a period using GspPort mock or live GSP API."""
    entries = gsp_adapter.get_gstr2b(tenant_id, period)
    if not entries:
        raise HTTPException(status_code=404, detail=f"No GSTR-2B entries found for period {period}")
        
    count = import_gstr2b_entries(tenant_id, period, entries)
    return {"status": "success", "period": period, "entries_imported": count}

@router.post("/gstr2b/upload")
async def upload_gstr2b(
    file: UploadFile = File(...),
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Accepts an uploaded GSTR-2B file (JSON exported from GST portal or custom list)
    and loads entries directly into the tenant's reconciliation graph.
    """
    content = await file.read()
    try:
        raw_json = json.loads(content.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format. Please upload a valid GSTR-2B JSON file.")
        
    entries = parse_gstr2b_uploaded_data(raw_json, period)
    if not entries:
        raise HTTPException(status_code=400, detail="Could not extract any B2B invoice entries from uploaded file.")
        
    count = import_gstr2b_entries(tenant_id, period, entries)
    return {"status": "success", "period": period, "entries_imported": count}

@router.get("/reconcile/{period}/export-csv")
def export_reconciliation_csv(
    period: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Generates a multi-section CSV audit working paper of the GSTR-2B reconciliation.
    """
    res = run_reconciliation(tenant_id, period)
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Title & Metadata
    writer.writerow(["LEDGERGRAPH GSTR-2B RECONCILIATION REPORT"])
    writer.writerow(["Client Tenant:", tenant_id])
    writer.writerow(["Tax Period:", period])
    writer.writerow(["Generated At (UTC):", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])
    
    # Summary
    itc = res["itc_summary"]
    writer.writerow(["--- ITC SUMMARY (INR) ---"])
    writer.writerow(["Matched ITC", itc["matched_itc"]])
    writer.writerow(["At-Risk ITC (Missing in 2B)", itc["at_risk_itc"]])
    writer.writerow(["Timing Gap ITC (QRMP Suppliers)", itc["timing_gap_itc"]])
    writer.writerow(["Total Claimable ITC", itc["total_claimable"]])
    writer.writerow([])
    
    # Sections
    sections = [
        ("MATCHED INVOICES (Books & GSTR-2B)", res.get("matched", [])),
        ("MISSING IN GSTR-2B (Payment Hold Advised)", res.get("missing_in_2b", [])),
        ("EXPECTED TIMING GAP (QRMP Suppliers)", res.get("expected_timing_gap", [])),
        ("IN GSTR-2B NOT IN BOOKS (Ghost Invoices)", res.get("in_2b_not_in_books", [])),
    ]
    
    for section_title, rows in sections:
        writer.writerow([f"=== {section_title} ({len(rows)} entries) ==="])
        writer.writerow(["Supplier Name", "Supplier GSTIN", "Invoice #", "Books Taxable", "Books Tax", "2B Taxable", "2B Tax", "Status", "Compliance Advice"])
        for r in rows:
            writer.writerow([
                r.get("supplier_name", ""),
                r.get("supplier_gstin", ""),
                r.get("invoice_number", ""),
                r.get("books_taxable", 0.0),
                r.get("books_tax", 0.0),
                r.get("gstr2b_taxable", 0.0),
                r.get("gstr2b_tax", 0.0),
                r.get("status", ""),
                r.get("advice", "")
            ])
        writer.writerow([])
        
    csv_bytes = output.getvalue().encode("utf-8")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=GSTR2B_Reconciliation_{tenant_id}_{period}.csv"}
    )

@router.post("/reconcile/{period}")
def trigger_reconciliation(
    period: str,
    from_date: str = Query("2026-09-01"),
    to_date: str = Query("2026-09-30"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Executes matching engine between books and GSTR-2B."""
    # Ensure 2B is loaded first
    import_gstr2b_entries(tenant_id, period, gsp_adapter.get_gstr2b(tenant_id, period))
    res = run_reconciliation(tenant_id, period, from_date, to_date)
    return res

@router.get("/reconcile/{period}")
def get_reconciliation(
    period: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    res = run_reconciliation(tenant_id, period)
    return res

@router.get("/itc/summary")
def get_itc_summary(
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    res = run_reconciliation(tenant_id, period)
    return {
        "tenant_id": tenant_id,
        "period": period,
        "itc_summary": res["itc_summary"],
        "counts": res["counts"]
    }

@router.post("/tally/export")
def export_tally_vouchers(
    req: TallyExportRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Exports approved invoices to zero-sum Tally XML.
    Marks invoices as EXPORTED.
    """
    g = tenant_graph(tenant_id)
    invoices = []
    
    for inv_id in req.invoice_ids:
        res = g.query(
            """
            MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {id: $id})
            OPTIONAL MATCH (v)-[:MAPS_TO_LEDGER]->(tl:TallyLedger)
            RETURN i.id, i.number, i.number_norm, i.date, i.fy, i.taxable,
                   i.cgst, i.sgst, i.igst, i.total, v.gstin, v.legal_name, tl.name
            """,
            {"id": inv_id}
        )
        if res.result_set and len(res.result_set) > 0:
            r = res.result_set[0]
            invoices.append({
                "id": r[0],
                "invoice_number": r[1],
                "number_norm": r[2],
                "invoice_date": r[3],
                "fy": r[4],
                "taxable_amount": r[5],
                "cgst_amount": r[6],
                "sgst_amount": r[7],
                "igst_amount": r[8],
                "total_amount": r[9],
                "supplier": {
                    "gstin": r[10],
                    "name": r[11],
                    "tally_ledger": r[12]
                }
            })
            
            # Set state to EXPORTED
            g.query("MATCH (i:Invoice {id: $id}) SET i.state = 'EXPORTED'", {"id": inv_id})
            
    if not invoices:
        raise HTTPException(status_code=400, detail="No invoices found to export")
        
    xml_content = generate_tally_xml_batch(tenant_id, invoices)
    
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename=tally_batch_{tenant_id}.xml"}
    )

@router.post("/tally/mark-imported")
def mark_tally_imported(
    req: TallyExportRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Transitions EXPORTED vouchers to POSTED and creates :TallyVoucher nodes."""
    g = tenant_graph(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for inv_id in req.invoice_ids:
        guid = f"vch_{inv_id}"
        g.query(
            """
            MATCH (i:Invoice {id: $id})
            CREATE (tv:TallyVoucher {
                guid: $guid,
                vch_no: i.number,
                export_state: "SUCCESS",
                exported_at: $now
            })
            CREATE (i)-[:POSTED_AS]->(tv)
            SET i.state = "POSTED"
            """,
            {"id": inv_id, "guid": guid, "now": now_iso}
        )
    return {"status": "success", "marked_posted_count": len(req.invoice_ids)}

@router.post("/tally/sync-direct")
def sync_tally_direct(
    req: TallyExportRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Directly posts generated XML to TallyPrime HTTP server on localhost:9000.
    Automatically marks invoices POSTED if Tally acknowledges creation.
    """
    g = tenant_graph(tenant_id)
    invoices = []
    
    for inv_id in req.invoice_ids:
        res = g.query(
            """
            MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {id: $id})
            OPTIONAL MATCH (v)-[:MAPS_TO_LEDGER]->(tl:TallyLedger)
            RETURN i.id, i.number, i.number_norm, i.date, i.fy, i.taxable,
                   i.cgst, i.sgst, i.igst, i.total, v.gstin, v.legal_name, tl.name
            """,
            {"id": inv_id}
        )
        if res.result_set and len(res.result_set) > 0:
            r = res.result_set[0]
            invoices.append({
                "id": r[0],
                "invoice_number": r[1],
                "number_norm": r[2],
                "invoice_date": r[3],
                "fy": r[4],
                "taxable_amount": r[5],
                "cgst_amount": r[6],
                "sgst_amount": r[7],
                "igst_amount": r[8],
                "total_amount": r[9],
                "supplier": {
                    "gstin": r[10],
                    "name": r[11],
                    "tally_ledger": r[12]
                }
            })
            
    if not invoices:
        raise HTTPException(status_code=400, detail="No invoices found to sync")
        
    sync_result = tally_bridge.sync_to_tally_direct(tenant_id, invoices)
    
    if sync_result.get("status") == "synced":
        now_iso = datetime.now(timezone.utc).isoformat()
        for inv_id in req.invoice_ids:
            g.query(
                """
                MATCH (i:Invoice {id: $id})
                CREATE (tv:TallyVoucher {
                    guid: $guid,
                    vch_no: i.number,
                    export_state: "SUCCESS",
                    exported_at: $now
                })
                CREATE (i)-[:POSTED_AS]->(tv)
                SET i.state = "POSTED"
                """,
                {"id": inv_id, "guid": f"vch_{inv_id}", "now": now_iso}
            )
            
    return sync_result

