import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.adapters.gsp_mock import MockGspAdapter
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import tenant_graph
from app.services.reconcile import import_gstr2b_entries, run_reconciliation
from app.services.tally_xml import generate_tally_xml_batch

router = APIRouter(prefix="", tags=["reconcile"])

gsp_mock = MockGspAdapter()

class TallyExportRequest(BaseModel):
    invoice_ids: List[str]

@router.post("/gstr2b/import")
def import_gstr2b(
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Imports GSTR-2B entries for a period using GspPort mock or fixtures."""
    entries = gsp_mock.get_gstr2b(tenant_id, period)
    if not entries:
        raise HTTPException(status_code=404, detail=f"No GSTR-2B entries found for period {period}")
        
    count = import_gstr2b_entries(tenant_id, period, entries)
    return {"status": "success", "period": period, "entries_imported": count}

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
    import_gstr2b_entries(tenant_id, period, gsp_mock.get_gstr2b(tenant_id, period))
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
