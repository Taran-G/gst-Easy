import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.audit import record_audit_event
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import tenant_graph, query
from app.services.resolve import create_or_update_vendor_mapping

router = APIRouter(prefix="/masters", tags=["masters"])

class MapLedgerRequest(BaseModel):
    vendor_gstin: str
    tally_ledger_name: str
    invoice_id: Optional[str] = None

@router.get("/requests")
def list_master_requests(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Lists pending Master Request cards in the review queue."""
    g = tenant_graph(tenant_id)
    
    res = g.query(
        """
        MATCH (t:Task {kind: "MASTER_REQUEST", state: "PENDING"})-[:ABOUT]->(i:Invoice)
        MATCH (v:Vendor)-[:ISSUED]->(i)
        RETURN t.id, t.details, t.created_at, i.id, i.number, i.total, v.gstin, v.legal_name
        ORDER BY t.created_at DESC
        """
    )
    
    requests = []
    for r in res.result_set:
        requests.append({
            "task_id": r[0],
            "details": r[1],
            "created_at": r[2],
            "invoice_id": r[3],
            "invoice_number": r[4],
            "total_amount": r[5],
            "vendor_gstin": r[6],
            "vendor_name": r[7]
        })
    return requests

@router.get("/ledgers")
def get_tally_ledgers(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Returns all TallyLedger nodes for mapping dropdown."""
    g = tenant_graph(tenant_id)
    res = g.query("MATCH (l:TallyLedger) RETURN l.name, l.parent_group ORDER BY l.name ASC")
    ledgers = [{"name": r[0], "parent": r[1]} for r in res.result_set]
    return ledgers

@router.post("/map")
def map_vendor_to_ledger(
    req: MapLedgerRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Maps a Vendor GSTIN to a Tally ledger.
    Writes [:MAPS_TO_LEDGER] and stores procedural memory :ApprovalRule.
    Also clears pending MASTER_REQUEST tasks for that vendor/invoice!
    """
    user_name = user.get("email", "Admin")
    mapping_res = create_or_update_vendor_mapping(
        tenant_id=tenant_id,
        vendor_gstin=req.vendor_gstin,
        tally_ledger_name=req.tally_ledger_name,
        approved_by_user=user_name
    )
    
    g = tenant_graph(tenant_id)
    
    # Complete associated task
    g.query(
        """
        MATCH (t:Task {kind: "MASTER_REQUEST", state: "PENDING"})-[:ABOUT]->(i:Invoice)
        MATCH (v:Vendor {gstin: $gstin})-[:ISSUED]->(i)
        SET t.state = "COMPLETED",
            t.completed_by = $user
        """,
        {"gstin": req.vendor_gstin, "user": user_name}
    )
    
    # If invoice was in MASTER_REQUEST state, re-evaluate to READY if no other blocking issue
    if req.invoice_id:
        g.query(
            """
            MATCH (i:Invoice {id: $id})
            WHERE i.state = "MASTER_REQUEST"
            SET i.state = "READY"
            """,
            {"id": req.invoice_id}
        )
    else:
        # Update all invoices of this vendor that were stuck in MASTER_REQUEST
        g.query(
            """
            MATCH (v:Vendor {gstin: $gstin})-[:ISSUED]->(i:Invoice {state: "MASTER_REQUEST"})
            SET i.state = "READY"
            """,
            {"gstin": req.vendor_gstin}
        )
        
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="RULE_CHANGE",
        user_id=user_name,
        payload={
            "action": "MAP_LEDGER",
            "vendor_gstin": req.vendor_gstin,
            "ledger": req.tally_ledger_name,
            "rule_id": mapping_res["rule_id"]
        }
    )
    
    return {
        "status": "success",
        "message": f"Mapped GSTIN {req.vendor_gstin} to ledger '{req.tally_ledger_name}'. Rule stored in procedural memory.",
        "mapping": mapping_res
    }

@router.post("/import")
async def import_masters_csv(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Imports Tally masters CSV (type,name,parent,uom,gst_rate)
    Creates :TallyLedger and :TallyStockItem nodes.
    """
    g = tenant_graph(tenant_id)
    content = await file.read()
    text = content.decode("utf-8")
    
    reader = csv.DictReader(io.StringIO(text))
    ledgers_created = 0
    items_created = 0
    
    for row in reader:
        m_type = (row.get("type") or "").strip().lower()
        name = (row.get("name") or "").strip()
        parent = (row.get("parent") or "").strip()
        uom = (row.get("uom") or "").strip()
        rate = float(row.get("gst_rate") or 0.0)
        
        if not name:
            continue
            
        if m_type == "ledger":
            g.query(
                """
                MERGE (tl:TallyLedger {name: $name})
                SET tl.parent_group = $parent,
                    tl.gst_rate = $rate
                """,
                {"name": name, "parent": parent, "rate": rate}
            )
            ledgers_created += 1
        elif m_type == "stock_item":
            g.query(
                """
                MERGE (si:TallyStockItem {name: $name})
                SET si.uom = $uom,
                    si.gst_rate = $rate
                """,
                {"name": name, "uom": uom, "rate": rate}
            )
            items_created += 1
            
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="IMPORT_MASTERS",
        user_id=user.get("email", "unknown"),
        payload={"filename": file.filename, "ledgers": ledgers_created, "stock_items": items_created}
    )
    
    return {
        "status": "success",
        "ledgers_created": ledgers_created,
        "stock_items_created": items_created
    }
