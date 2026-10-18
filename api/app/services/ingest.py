import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

from app.adapters.llm_gemini import GeminiExtractorAdapter
from app.adapters.whatsapp_mock import MockWhatsAppAdapter
from app.core.audit import record_audit_event
from app.core.config import settings
from app.graph.client import tenant_graph, query
from app.services.resolve import resolve_vendor_and_items
from app.services.validate import validate_invoice, normalise_invoice_number, fy_of

logger = logging.getLogger(__name__)

extractor_adapter = GeminiExtractorAdapter()
whatsapp_adapter = MockWhatsAppAdapter()

def compute_file_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_tenant_details(tenant_id: str) -> Dict[str, Any]:
    g = tenant_graph(tenant_id)
    res = g.query("MATCH (t:Tenant {id: $id}) RETURN t.id, t.name, t.gstin, t.state_code", {"id": tenant_id})
    if res.result_set and len(res.result_set) > 0:
        return {
            "id": res.result_set[0][0],
            "name": res.result_set[0][1],
            "gstin": res.result_set[0][2],
            "state_code": res.result_set[0][3]
        }
    return {"id": tenant_id, "name": tenant_id, "gstin": "", "state_code": ""}

def process_document(
    tenant_id: str,
    file_path: str,
    source: str = "upload",
    sender_phone: Optional[str] = None,
    user_id: str = "system"
) -> Dict[str, Any]:
    """
    Full deterministic ingestion pipeline:
    1. Calculate SHA-256 and create Document node
    2. Extract fields via GeminiExtractorAdapter (with fixture replay)
    3. Resolve vendor & check duplicates via FalkorDB Cypher Q1
    4. Deterministically validate (Decimal math, GSTIN, taxes)
    5. Write nodes: Document, Vendor, Invoice, InvoiceLine, Task
    6. Audit log & consolidated WhatsApp reply
    """
    g = tenant_graph(tenant_id)
    file_sha = compute_file_sha256(file_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    doc_id = f"doc_{uuid.uuid4().hex[:10]}"
    
    # Check duplicate document by SHA-256
    res_dup = g.query("MATCH (d:Document {sha256: $sha}) RETURN d.id", {"sha": file_sha})
    is_dup_file = bool(res_dup.result_set and len(res_dup.result_set) > 0)
    
    doc_state = "DUPLICATE_FILE" if is_dup_file else "EXTRACTING"
    
    g.query(
        """
        CREATE (d:Document {
            id: $id,
            sha256: $sha,
            source: $source,
            received_at: $now,
            path: $path,
            state: $state
        })
        """,
        {
            "id": doc_id,
            "sha": file_sha,
            "source": source,
            "now": now_iso,
            "path": file_path,
            "state": doc_state
        }
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="UPLOAD",
        user_id=user_id,
        payload={"doc_id": doc_id, "source": source, "sha256": file_sha, "file_path": file_path}
    )
    
    # 2. Extract fields
    extraction = extractor_adapter.extract(file_path)
    extracted_dict = extraction.model_dump()
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="EXTRACTION",
        user_id=user_id,
        payload={"doc_id": doc_id, "invoice_number": extraction.invoice_number, "total": extraction.total_amount}
    )
    
    # 3. Resolve tenant and check duplicate invoice in FalkorDB
    tenant_info = get_tenant_details(tenant_id)
    norm_inv_no = normalise_invoice_number(extraction.invoice_number)
    try:
        fy = fy_of(extraction.invoice_date)
    except Exception:
        fy = "2026-27"
        
    first_item_name = extraction.lines[0].description if extraction.lines else None
    resolution = resolve_vendor_and_items(
        tenant_id=tenant_id,
        gstin=extraction.supplier_gstin,
        inv_no_norm=norm_inv_no,
        fy=fy,
        raw_item_name=first_item_name
    )
    
    is_duplicate_inv = resolution["is_duplicate"]
    
    # 4. Deterministic validation
    val_report = validate_invoice(extracted_dict, tenant_info, is_duplicate=is_duplicate_inv)
    
    # 5. Determine status
    if not val_report.is_valid:
        inv_state = "BLOCKED"
    elif resolution["needs_master_request"]:
        inv_state = "MASTER_REQUEST"
    else:
        inv_state = "READY"
        
    invoice_id = f"inv_{uuid.uuid4().hex[:10]}"
    
    # 6. Commit to Graph (Vendor, Invoice, Lines, Task)
    g.query(
        """
        MERGE (v:Vendor {gstin: $supp_gstin})
        ON CREATE SET v.filing_freq = "Monthly",
                      v.gstin_status = "Active",
                      v.risk_score = 0.1
        SET v.legal_name = coalesce(v.legal_name, $supp_name),
            v.trade_name = coalesce(v.trade_name, $supp_name),
            v.state_code = coalesce(v.state_code, $supp_state)
                      
        CREATE (i:Invoice {
            id: $inv_id,
            number: $inv_number,
            number_norm: $norm_inv_no,
            date: $inv_date,
            fy: $fy,
            taxable: $taxable,
            cgst: $cgst,
            sgst: $sgst,
            igst: $igst,
            total: $total,
            state: $inv_state,
            itc_status: "ELIGIBLE_PENDING_2B",
            hold_status: "NONE",
            place_of_supply: $pos,
            file_path: $file_path,
            issues_json: $issues_json,
            applied_rules: $applied_rules,
            created_at: $now
        })
        
        WITH v, i
        MATCH (d:Document {id: $doc_id})
        CREATE (v)-[:ISSUED]->(i)
        CREATE (d)-[:SOURCE_OF]->(i)
        SET d.state = "NEEDS_REVIEW"
        """,
        {
            "supp_gstin": extraction.supplier_gstin,
            "supp_name": extraction.supplier_name,
            "supp_state": extraction.supplier_gstin[:2] if len(extraction.supplier_gstin) >= 2 else "06",
            "inv_id": invoice_id,
            "inv_number": extraction.invoice_number,
            "norm_inv_no": norm_inv_no,
            "inv_date": extraction.invoice_date,
            "fy": fy,
            "taxable": float(extraction.taxable_amount),
            "cgst": float(extraction.cgst_amount),
            "sgst": float(extraction.sgst_amount),
            "igst": float(extraction.igst_amount),
            "total": float(extraction.total_amount),
            "inv_state": inv_state,
            "pos": extraction.place_of_supply,
            "file_path": file_path,
            "issues_json": json.dumps([i.model_dump() for i in val_report.issues]),
            "applied_rules": json.dumps(resolution["applied_rules"]),
            "doc_id": doc_id,
            "now": now_iso
        }
    )
    
    # Write line items
    for idx, line in enumerate(extraction.lines, start=1):
        g.query(
            """
            MATCH (i:Invoice {id: $inv_id})
            CREATE (l:InvoiceLine {
                no: $no,
                desc: $desc,
                hsn_sac: $hsn,
                qty: $qty,
                uom: $uom,
                rate: $rate,
                taxable: $taxable,
                gst_rate: $gst_rate
            })
            CREATE (i)-[:HAS_LINE]->(l)
            """,
            {
                "inv_id": invoice_id,
                "no": idx,
                "desc": line.description,
                "hsn": line.hsn_sac or "",
                "qty": float(line.qty or 1.0),
                "uom": line.uom or "PCS",
                "rate": float(line.rate or line.taxable_value),
                "taxable": float(line.taxable_value),
                "gst_rate": float(line.gst_rate)
            }
        )
        
    # If master request needed, create Task node
    if resolution["needs_master_request"]:
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        g.query(
            """
            MATCH (i:Invoice {id: $inv_id})
            CREATE (t:Task {
                id: $task_id,
                kind: "MASTER_REQUEST",
                state: "PENDING",
                owner: "Admin",
                details: "New supplier or unmapped item ledger required in Tally masters",
                created_at: $now
            })
            CREATE (t)-[:ABOUT]->(i)
            """,
            {
                "inv_id": invoice_id,
                "task_id": task_id,
                "now": now_iso
            }
        )
        
    # Send consolidated WhatsApp reply if phone available
    target_phone = sender_phone or extraction.supplier_phone
    if target_phone:
        summary_msg = (
            f"Bill #{extraction.invoice_number} from {extraction.supplier_name} received. "
            f"Amount: Rs. {extraction.total_amount:.2f}. Status: {inv_state}. "
            f"{'Ready for CA review.' if inv_state == 'READY' else 'Requires attention in portal.'}"
        )
        whatsapp_adapter.send_text(target_phone, summary_msg)
        
    return {
        "invoice_id": invoice_id,
        "doc_id": doc_id,
        "supplier_name": extraction.supplier_name,
        "invoice_number": extraction.invoice_number,
        "total_amount": extraction.total_amount,
        "state": inv_state,
        "validation": val_report.model_dump(),
        "resolution": resolution
    }
