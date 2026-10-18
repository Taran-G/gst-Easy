import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.audit import record_audit_event
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import tenant_graph, query
from app.services.ingest import get_tenant_details
from app.services.resolve import resolve_vendor_and_items
from app.services.validate import validate_invoice, normalise_invoice_number, fy_of

router = APIRouter(prefix="/invoices", tags=["invoices"])

class InvoiceEditRequest(BaseModel):
    taxable_amount: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    total_amount: Optional[float] = None
    supplier_gstin: Optional[str] = None
    place_of_supply: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None

class RejectRequest(BaseModel):
    reason: str

@router.get("")
def list_inbox(
    tab: str = Query("all", description="needs_review | blocked | ready | approved | all"),
    status: Optional[str] = Query(None, description="READY | BLOCKED | MASTER_REQUEST | APPROVED | ALL"),
    supplier_gstin: Optional[str] = Query(None),
    itc_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns the Inbox list with multi-criteria filtering by tab, status, supplier, ITC, and search query.
    """
    g = tenant_graph(tenant_id)
    
    conditions = []
    params = {}
    
    if tab == "needs_review":
        conditions.append("i.state IN ['DRAFT', 'MASTER_REQUEST', 'BLOCKED']")
    elif tab == "blocked":
        conditions.append("i.state = 'BLOCKED'")
    elif tab == "ready":
        conditions.append("i.state = 'READY'")
    elif tab == "approved":
        conditions.append("i.state IN ['APPROVED', 'EXPORTED', 'POSTED']")
        
    if status and status != "ALL":
        conditions.append("i.state = $status")
        params["status"] = status
        
    if supplier_gstin and supplier_gstin != "ALL":
        conditions.append("v.gstin = $supp_gstin")
        params["supp_gstin"] = supplier_gstin
        
    if itc_status and itc_status != "ALL":
        conditions.append("i.itc_status = $itc_status")
        params["itc_status"] = itc_status
        
    if search and search.strip():
        conditions.append("(toLower(i.number) CONTAINS toLower($search) OR toLower(v.legal_name) CONTAINS toLower($search) OR toLower(v.gstin) CONTAINS toLower($search))")
        params["search"] = search.strip()
        
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
    cypher = f"""
    MATCH (v:Vendor)-[:ISSUED]->(i:Invoice)
    {where_clause}
    OPTIONAL MATCH (d:Document)-[:SOURCE_OF]->(i)
    OPTIONAL MATCH (i)-[:HAS_LINE]->(l:InvoiceLine)
    RETURN i.id, i.number, i.date, i.total, i.taxable, i.cgst, i.sgst, i.igst,
           i.state, i.itc_status, i.hold_status, v.gstin, v.legal_name,
           head(collect(d.id)) AS doc_id, head(collect(d.source)) AS source, i.issues_json, count(l) AS line_count
    ORDER BY i.date DESC
    """
    
    res = g.query(cypher, params)
    invoices = []
    seen_ids = set()
    for r in res.result_set:
        inv_id = r[0]
        if inv_id in seen_ids:
            continue
        seen_ids.add(inv_id)
        
        issues = []
        if r[15]:
            try:
                issues = json.loads(r[15])
            except Exception:
                issues = []
                
        invoices.append({
            "id": inv_id,
            "number": r[1],
            "date": r[2],
            "total_amount": r[3],
            "taxable_amount": r[4],
            "cgst_amount": r[5],
            "sgst_amount": r[6],
            "igst_amount": r[7],
            "state": r[8],
            "itc_status": r[9],
            "hold_status": r[10],
            "supplier_gstin": r[11],
            "supplier_name": r[12],
            "doc_id": r[13],
            "source": r[14],
            "issues": issues,
            "line_count": r[16]
        })
        
    # Available suppliers for dropdown
    supp_res = g.query(
        """
        MATCH (v:Vendor)-[:ISSUED]->(i:Invoice)
        RETURN v.gstin, v.legal_name, count(i) AS bill_count
        ORDER BY bill_count DESC
        """
    )
    available_suppliers = [
        {"gstin": r[0], "legal_name": r[1] or r[0], "bill_count": int(r[2])}
        for r in supp_res.result_set
    ]
    
    # Status count metrics
    cnt_res = g.query(
        """
        MATCH (i:Invoice)
        RETURN count(i) AS total,
               sum(CASE WHEN i.state IN ['DRAFT', 'MASTER_REQUEST', 'BLOCKED'] THEN 1 ELSE 0 END) AS needs_review,
               sum(CASE WHEN i.state = 'READY' THEN 1 ELSE 0 END) AS ready,
               sum(CASE WHEN i.state = 'BLOCKED' THEN 1 ELSE 0 END) AS blocked,
               sum(CASE WHEN i.state IN ['APPROVED', 'EXPORTED', 'POSTED'] THEN 1 ELSE 0 END) AS approved
        """
    )
    counts_row = cnt_res.result_set[0] if cnt_res.result_set else [0, 0, 0, 0, 0]
    status_counts = {
        "all": int(counts_row[0] or 0),
        "needs_review": int(counts_row[1] or 0),
        "ready": int(counts_row[2] or 0),
        "blocked": int(counts_row[3] or 0),
        "approved": int(counts_row[4] or 0)
    }
        
    return {
        "tenant_id": tenant_id,
        "tab": tab,
        "count": len(invoices),
        "invoices": invoices,
        "available_suppliers": available_suppliers,
        "status_counts": status_counts
    }

@router.get("/{invoice_id}")
def get_invoice_detail(
    invoice_id: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    g = tenant_graph(tenant_id)
    
    res = g.query(
        """
        MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {id: $id})
        OPTIONAL MATCH (d:Document)-[:SOURCE_OF]->(i)
        OPTIONAL MATCH (i)-[:APPROVED_BY]->(a:Approval)
        RETURN i.id, i.number, i.number_norm, i.date, i.fy, i.taxable, i.cgst, i.sgst, i.igst,
               i.total, i.state, i.itc_status, i.hold_status, i.place_of_supply, i.file_path,
               i.issues_json, i.applied_rules, v.gstin, v.legal_name, v.trade_name, v.state_code,
               d.id AS doc_id, d.path AS doc_path, a.user AS approved_by, a.at AS approved_at
        """,
        {"id": invoice_id}
    )
    
    if not res.result_set or len(res.result_set) == 0:
        raise HTTPException(status_code=404, detail=f"Invoice '{invoice_id}' not found")
        
    r = res.result_set[0]
    
    # Fetch line items
    lines_res = g.query(
        """
        MATCH (i:Invoice {id: $id})-[:HAS_LINE]->(l:InvoiceLine)
        RETURN l.no, l.desc, l.hsn_sac, l.qty, l.uom, l.rate, l.taxable, l.gst_rate
        ORDER BY l.no ASC
        """,
        {"id": invoice_id}
    )
    
    lines = []
    for lr in lines_res.result_set:
        lines.append({
            "no": lr[0],
            "description": lr[1],
            "hsn_sac": lr[2],
            "qty": lr[3],
            "uom": lr[4],
            "rate": lr[5],
            "taxable_value": lr[6],
            "gst_rate": lr[7]
        })
        
    issues = json.loads(r[15]) if r[15] else []
    applied_rules = json.loads(r[16]) if r[16] else []
    
    # Check master mapping for supplier
    res_map = g.query(
        """
        MATCH (v:Vendor {gstin: $gstin})
        OPTIONAL MATCH (v)-[:MAPS_TO_LEDGER]->(tl:TallyLedger)
        RETURN tl.name
        """,
        {"gstin": r[17]}
    )
    tally_ledger = res_map.result_set[0][0] if res_map.result_set else None
    
    return {
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
        "state": r[10],
        "itc_status": r[11],
        "hold_status": r[12],
        "place_of_supply": r[13],
        "file_path": r[14],
        "issues": issues,
        "applied_rules": applied_rules,
        "supplier": {
            "gstin": r[17],
            "name": r[18],
            "state_code": r[20],
            "tally_ledger": tally_ledger
        },
        "document": {
            "id": r[21],
            "path": r[22]
        },
        "lines": lines,
        "approval": {
            "approved_by": r[23],
            "approved_at": r[24]
        } if r[23] else None
    }

@router.patch("/{invoice_id}")
def update_invoice(
    invoice_id: str,
    req: InvoiceEditRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Field edits re-run validation and store diffs in audit log.
    Editing the wrong total live clears the MATH_MISMATCH block!
    """
    g = tenant_graph(tenant_id)
    inv_data = get_invoice_detail(invoice_id, tenant_id, user)
    tenant_info = get_tenant_details(tenant_id)
    
    # Merge existing with patch
    updated = {
        "supplier_name": inv_data["supplier"]["name"],
        "supplier_gstin": req.supplier_gstin or inv_data["supplier"]["gstin"],
        "buyer_name": tenant_info["name"],
        "buyer_gstin": tenant_info["gstin"],
        "invoice_number": req.invoice_number or inv_data["invoice_number"],
        "invoice_date": req.invoice_date or inv_data["invoice_date"],
        "place_of_supply": req.place_of_supply or inv_data["place_of_supply"],
        "taxable_amount": req.taxable_amount if req.taxable_amount is not None else inv_data["taxable_amount"],
        "cgst_amount": req.cgst_amount if req.cgst_amount is not None else inv_data["cgst_amount"],
        "sgst_amount": req.sgst_amount if req.sgst_amount is not None else inv_data["sgst_amount"],
        "igst_amount": req.igst_amount if req.igst_amount is not None else inv_data["igst_amount"],
        "total_amount": req.total_amount if req.total_amount is not None else inv_data["total_amount"],
        "lines": inv_data["lines"]
    }
    
    val_report = validate_invoice(updated, tenant_info, is_duplicate=False)
    
    # Re-determine state
    has_blocking = any(i.severity == "BLOCK" for i in val_report.issues)
    needs_master = (inv_data["supplier"]["tally_ledger"] is None)
    
    if has_blocking:
        new_state = "BLOCKED"
    elif needs_master:
        new_state = "MASTER_REQUEST"
    else:
        new_state = "READY"
        
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Update Invoice node
    g.query(
        """
        MATCH (i:Invoice {id: $id})
        SET i.taxable = $taxable,
            i.cgst = $cgst,
            i.sgst = $sgst,
            i.igst = $igst,
            i.total = $total,
            i.state = $state,
            i.issues_json = $issues_json,
            i.updated_at = $now
        """,
        {
            "id": invoice_id,
            "taxable": float(updated["taxable_amount"]),
            "cgst": float(updated["cgst_amount"]),
            "sgst": float(updated["sgst_amount"]),
            "igst": float(updated["igst_amount"]),
            "total": float(updated["total_amount"]),
            "state": new_state,
            "issues_json": json.dumps([i.model_dump() for i in val_report.issues]),
            "now": now_iso
        }
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="EDIT",
        user_id=user.get("email", "unknown"),
        payload={"invoice_id": invoice_id, "diff": req.model_dump(exclude_unset=True), "new_state": new_state}
    )
    
    return {
        "status": "updated",
        "invoice_id": invoice_id,
        "new_state": new_state,
        "is_valid": val_report.is_valid,
        "issues": [i.model_dump() for i in val_report.issues]
    }

@router.post("/{invoice_id}/approve")
def approve_invoice(
    invoice_id: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    HITL Approval:
    - Disabled if any BLOCK exists
    - Writes :Approval node and [:APPROVED_BY] edge
    - Transitions state to APPROVED
    """
    g = tenant_graph(tenant_id)
    inv = get_invoice_detail(invoice_id, tenant_id, user)
    
    # Guard: cannot approve if BLOCKED
    if inv["state"] == "BLOCKED":
        raise HTTPException(
            status_code=400,
            detail="Cannot approve invoice while blocking issues exist. Correct issues first."
        )
        
    if inv["state"] == "MASTER_REQUEST":
        raise HTTPException(
            status_code=400,
            detail="Cannot approve invoice without mapping supplier to Tally ledger master first."
        )
        
    now_iso = datetime.now(timezone.utc).isoformat()
    app_id = f"appr_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    g.query(
        """
        MATCH (i:Invoice {id: $id})
        CREATE (a:Approval {
            id: $app_id,
            user: $user,
            action: "APPROVE",
            at: $now
        })
        CREATE (i)-[:APPROVED_BY]->(a)
        SET i.state = "APPROVED"
        """,
        {
            "id": invoice_id,
            "app_id": app_id,
            "user": user.get("email", "CA Partner"),
            "now": now_iso
        }
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="APPROVE",
        user_id=user.get("email", "unknown"),
        payload={"invoice_id": invoice_id, "amount": inv["total_amount"]}
    )
    
    return {"status": "approved", "invoice_id": invoice_id, "state": "APPROVED"}

@router.post("/{invoice_id}/reject")
def reject_invoice(
    invoice_id: str,
    req: RejectRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    g = tenant_graph(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    app_id = f"rej_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    g.query(
        """
        MATCH (i:Invoice {id: $id})
        CREATE (a:Approval {
            id: $app_id,
            user: $user,
            action: "REJECT",
            reason: $reason,
            at: $now
        })
        CREATE (i)-[:APPROVED_BY]->(a)
        SET i.state = "REJECTED"
        """,
        {
            "id": invoice_id,
            "app_id": app_id,
            "user": user.get("email", "unknown"),
            "reason": req.reason,
            "now": now_iso
        }
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="REJECT",
        user_id=user.get("email", "unknown"),
        payload={"invoice_id": invoice_id, "reason": req.reason}
    )
    
    return {"status": "rejected", "invoice_id": invoice_id, "state": "REJECTED"}

class BulkApproveRequest(BaseModel):
    invoice_ids: List[str]

@router.post("/bulk-approve")
def bulk_approve_invoices(
    req: BulkApproveRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Approves all eligible invoices in a batch, skipping invoices with validation blocks
    or unmapped supplier master requests.
    """
    g = tenant_graph(tenant_id)
    approved = []
    skipped = []
    
    for inv_id in req.invoice_ids:
        try:
            inv = get_invoice_detail(inv_id, tenant_id, user)
            if inv["state"] == "BLOCKED":
                skipped.append({"id": inv_id, "reason": "Invoice has blocking issues"})
                continue
            if inv["state"] == "MASTER_REQUEST":
                skipped.append({"id": inv_id, "reason": "Supplier requires Tally ledger mapping"})
                continue
            if inv["state"] in ["APPROVED", "EXPORTED", "POSTED"]:
                approved.append(inv_id)
                continue
                
            now_iso = datetime.now(timezone.utc).isoformat()
            app_id = f"appr_{datetime.now().strftime('%Y%m%d%H%M%S')}_{inv_id[:6]}"
            g.query(
                """
                MATCH (i:Invoice {id: $id})
                CREATE (a:Approval {
                    id: $app_id,
                    user: $user,
                    action: "APPROVE",
                    at: $now
                })
                CREATE (i)-[:APPROVED_BY]->(a)
                SET i.state = "APPROVED"
                """,
                {
                    "id": inv_id,
                    "app_id": app_id,
                    "user": user.get("email", "CA Partner"),
                    "now": now_iso
                }
            )
            record_audit_event(
                tenant_id=tenant_id,
                firm_id=None,
                event_type="APPROVE",
                user_id=user.get("email", "unknown"),
                payload={"invoice_id": inv_id, "amount": inv["total_amount"]}
            )
            approved.append(inv_id)
        except Exception as e:
            skipped.append({"id": inv_id, "reason": str(e)})
            
    return {
        "status": "success",
        "approved_count": len(approved),
        "approved_ids": approved,
        "skipped_count": len(skipped),
        "skipped": skipped
    }
