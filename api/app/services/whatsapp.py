import csv
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.adapters.whatsapp_cloud import MetaWhatsAppCloudAdapter
from app.core.audit import record_audit_event
from app.core.config import settings
from app.graph.client import tenant_graph, firm_graph
from app.services.ingest import process_document

logger = logging.getLogger(__name__)
wa_adapter = MetaWhatsAppCloudAdapter()

def record_whatsapp_message(
    tenant_id: str,
    direction: str,
    sender_phone: str,
    recipient_phone: str,
    message_type: str = "text",
    text: str = "",
    media_path: Optional[str] = None,
    media_filename: Optional[str] = None,
    invoice_id: Optional[str] = None,
    status: str = "DELIVERED",
    cost_inr: float = 0.0,
    template_name: Optional[str] = None,
    vendor_gstin: Optional[str] = None
) -> Dict[str, Any]:
    """
    Persists a WhatsApp message record in the tenant's FalkorDB knowledge graph.
    Connects to Invoice and Vendor nodes for complete accounting traceability.
    """
    g = tenant_graph(tenant_id)
    msg_id = f"wam_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    g.query(
        """
        CREATE (m:WhatsAppMessage {
            id: $id,
            direction: $direction,
            sender_phone: $sender_phone,
            recipient_phone: $recipient_phone,
            message_type: $message_type,
            text: $text,
            media_path: $media_path,
            media_filename: $media_filename,
            invoice_id: $invoice_id,
            status: $status,
            cost_inr: $cost_inr,
            template_name: $template_name,
            timestamp: $now
        })
        """,
        {
            "id": msg_id,
            "direction": direction,
            "sender_phone": sender_phone,
            "recipient_phone": recipient_phone,
            "message_type": message_type,
            "text": text or "",
            "media_path": media_path or "",
            "media_filename": media_filename or "",
            "invoice_id": invoice_id or "",
            "status": status,
            "cost_inr": float(cost_inr),
            "template_name": template_name or "",
            "now": now_iso
        }
    )
    
    # Link to Invoice if provided
    if invoice_id:
        g.query(
            """
            MATCH (m:WhatsAppMessage {id: $msg_id}), (i:Invoice {id: $inv_id})
            MERGE (m)-[:ABOUT_INVOICE]->(i)
            """,
            {"msg_id": msg_id, "inv_id": invoice_id}
        )
        
    # Link to Vendor if GSTIN or phone matches
    if vendor_gstin:
        g.query(
            """
            MATCH (m:WhatsAppMessage {id: $msg_id}), (v:Vendor {gstin: $gstin})
            MERGE (v)-[:HAS_WHATSAPP_MESSAGE]->(m)
            """,
            {"msg_id": msg_id, "gstin": vendor_gstin}
        )
    elif sender_phone:
        g.query(
            """
            MATCH (m:WhatsAppMessage {id: $msg_id}), (v:Vendor)
            WHERE v.phone = $phone
            MERGE (v)-[:HAS_WHATSAPP_MESSAGE]->(m)
            """,
            {"msg_id": msg_id, "phone": sender_phone}
        )

    return {
        "id": msg_id,
        "direction": direction,
        "sender_phone": sender_phone,
        "recipient_phone": recipient_phone,
        "message_type": message_type,
        "text": text,
        "media_path": media_path,
        "media_filename": media_filename,
        "invoice_id": invoice_id,
        "status": status,
        "cost_inr": cost_inr,
        "template_name": template_name,
        "timestamp": now_iso
    }

def get_whatsapp_messages(
    tenant_id: str,
    limit: int = 50,
    direction: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves all inbound and outbound WhatsApp messages from the tenant's graph.
    """
    g = tenant_graph(tenant_id)
    
    where_clauses = []
    params: Dict[str, Any] = {"limit": limit}
    
    if direction and direction.upper() in ["INBOUND", "OUTBOUND"]:
        where_clauses.append("m.direction = $direction")
        params["direction"] = direction.upper()
        
    if search:
        where_clauses.append("(toLower(m.text) CONTAINS toLower($search) OR m.sender_phone CONTAINS $search OR m.recipient_phone CONTAINS $search OR m.invoice_id CONTAINS $search)")
        params["search"] = search
        
    where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    query = f"""
    MATCH (m:WhatsAppMessage)
    {where_str}
    OPTIONAL MATCH (m)-[:ABOUT_INVOICE]->(i:Invoice)
    OPTIONAL MATCH (v:Vendor)-[:ISSUED]->(i)
    RETURN m.id, m.direction, m.sender_phone, m.recipient_phone, m.message_type,
           m.text, m.media_path, m.media_filename, m.invoice_id, m.status,
           m.cost_inr, m.template_name, m.timestamp, i.number, coalesce(v.legal_name, '')
    ORDER BY m.timestamp DESC
    LIMIT $limit
    """
    
    res = g.query(query, params)
    
    messages = []
    inbound_count = 0
    outbound_count = 0
    invoices_ingested = 0
    
    for row in res.result_set:
        dir_val = row[1]
        if dir_val == "INBOUND":
            inbound_count += 1
            if row[4] in ["document", "image"]:
                invoices_ingested += 1
        else:
            outbound_count += 1
            
        messages.append({
            "id": row[0],
            "direction": row[1],
            "sender_phone": row[2],
            "recipient_phone": row[3],
            "message_type": row[4],
            "text": row[5],
            "media_path": row[6],
            "media_filename": row[7],
            "invoice_id": row[8],
            "status": row[9],
            "cost_inr": float(row[10] or 0.0),
            "template_name": row[11],
            "timestamp": row[12],
            "invoice_number": row[13],
            "vendor_name": row[14]
        })
        
    # Get lifetime summary counts
    count_res = g.query(
        """
        MATCH (m:WhatsAppMessage)
        RETURN count(m),
               sum(CASE WHEN m.direction = 'INBOUND' THEN 1 ELSE 0 END),
               sum(CASE WHEN m.direction = 'OUTBOUND' THEN 1 ELSE 0 END)
        """
    )
    total_lifetime = 0
    inbound_lifetime = 0
    outbound_lifetime = 0
    if count_res.result_set:
        total_lifetime = count_res.result_set[0][0] or 0
        inbound_lifetime = count_res.result_set[0][1] or 0
        outbound_lifetime = count_res.result_set[0][2] or 0
        
    return {
        "messages": messages,
        "stats": {
            "total": total_lifetime,
            "inbound": inbound_lifetime,
            "outbound": outbound_lifetime,
            "invoices_ingested": invoices_ingested
        }
    }

def handle_incoming_whatsapp(
    payload: Dict[str, Any],
    tenant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Central pipeline for handling all incoming WhatsApp messages & attachments.
    - Media attachments (PDF / Image) -> Deterministic ingestion, validation, and auto-reply.
    - Pure text messages -> Intent recognition (STOP, status, query) and agent response.
    """
    event = wa_adapter.parse_webhook(payload)
    if not event:
        return {"status": "ignored_status_or_empty"}
        
    sender_phone = event.get("sender_phone") or "+919876543210"
    text_content = event.get("text") or ""
    media_path = event.get("media_path")
    media_filename = Path(media_path).name if media_path else None
    
    # Resolve tenant
    routed_tenant = tenant_id
    if not routed_tenant:
        fg = firm_graph("demo")
        res = fg.query("MATCH (pm:PhoneMap {phone: $phone}) RETURN pm.tenant_id", {"phone": sender_phone})
        if res.result_set and len(res.result_set) > 0:
            routed_tenant = res.result_set[0][0]
        else:
            routed_tenant = "apex"  # Default baseline tenant
            
    g = tenant_graph(routed_tenant)
    
    # Find matching vendor by phone
    res_vendor = g.query("MATCH (v:Vendor) WHERE v.phone = $phone RETURN v.gstin, v.legal_name, v.opted_out", {"phone": sender_phone})
    vendor_gstin = None
    vendor_name = "Supplier"
    is_opted_out = False
    if res_vendor.result_set:
        vendor_gstin = res_vendor.result_set[0][0]
        vendor_name = res_vendor.result_set[0][1] or "Supplier"
        is_opted_out = bool(res_vendor.result_set[0][2])

    # Case A: Media Attachment (Bill PDF or Image)
    if media_path and os.path.exists(media_path):
        ext = Path(media_path).suffix.lower()
        msg_type = "image" if ext in [".jpg", ".jpeg", ".png"] else "document"
        
        # 1. Record Inbound Message
        inbound_msg = record_whatsapp_message(
            tenant_id=routed_tenant,
            direction="INBOUND",
            sender_phone=sender_phone,
            recipient_phone="Agent WhatsApp Bot",
            message_type=msg_type,
            text=text_content or f"Uploaded bill: {media_filename}",
            media_path=media_path,
            media_filename=media_filename,
            status="RECEIVED",
            vendor_gstin=vendor_gstin
        )
        
        # 2. Ingest Document
        result = process_document(
            tenant_id=routed_tenant,
            file_path=media_path,
            source="whatsapp",
            sender_phone=sender_phone,
            user_id="whatsapp_agent"
        )
        
        invoice_id = result.get("invoice_id")
        inv_number = result.get("invoice_number", "Unknown")
        supp_name = result.get("supplier_name", vendor_name)
        total = float(result.get("total_amount") or 0.0)
        state = result.get("state", "NEEDS_REVIEW")
        is_duplicate = result.get("is_duplicate", False)
        val_issues = result.get("validation_issues", [])
        
        # Link inbound message to invoice
        if invoice_id:
            g.query(
                "MATCH (m:WhatsAppMessage {id: $mid}), (i:Invoice {id: $iid}) MERGE (m)-[:ABOUT_INVOICE]->(i)",
                {"mid": inbound_msg["id"], "iid": invoice_id}
            )
            
        # 3. Formulate Agent Auto-Reply
        if is_duplicate:
            reply_text = (
                f"ℹ️ LedgerGraph CA Agent: Bill #{inv_number} from {supp_name} (Rs. {total:,.2f}) "
                f"is already recorded. Duplicate submission rejected without modifying existing books."
            )
        elif state == "READY":
            reply_text = (
                f"✅ LedgerGraph CA Agent: Bill #{inv_number} from {supp_name} for Rs. {total:,.2f} received. "
                f"Math verification & GSTIN check passed. Queued in READY state for CA review and Tally posting."
            )
        elif state == "BLOCKED":
            issue_msg = "; ".join([i.get("message", "") for i in val_issues[:2]]) or "Statutory rule mismatch"
            reply_text = (
                f"⚠️ LedgerGraph CA Agent: Bill #{inv_number} for Rs. {total:,.2f} is BLOCKED. "
                f"Reason: {issue_msg}. Please issue a corrected invoice."
            )
        elif state == "MASTER_REQUEST":
            reply_text = (
                f"ℹ️ LedgerGraph CA Agent: Bill #{inv_number} for Rs. {total:,.2f} received. "
                f"Pending new supplier/item ledger mapping in Tally masters."
            )
        else:
            reply_text = (
                f"📄 LedgerGraph CA Agent: Bill #{inv_number} for Rs. {total:,.2f} received and queued for review."
            )
            
        # 4. Dispatch and Record Agent Outbound Reply
        wa_adapter.send_text(sender_phone, reply_text)
        outbound_msg = record_whatsapp_message(
            tenant_id=routed_tenant,
            direction="OUTBOUND",
            sender_phone="Agent WhatsApp Bot",
            recipient_phone=sender_phone,
            message_type="text",
            text=reply_text,
            invoice_id=invoice_id,
            status="DELIVERED",
            cost_inr=0.0,
            vendor_gstin=vendor_gstin
        )
        
        return {
            "status": "success",
            "routed_tenant": routed_tenant,
            "invoice_id": invoice_id,
            "state": state,
            "inbound_message": inbound_msg,
            "outbound_reply": outbound_msg,
            "invoice": result
        }

    # Case B: Pure Text Message
    else:
        inbound_msg = record_whatsapp_message(
            tenant_id=routed_tenant,
            direction="INBOUND",
            sender_phone=sender_phone,
            recipient_phone="Agent WhatsApp Bot",
            message_type="text",
            text=text_content or "(empty text)",
            status="RECEIVED",
            vendor_gstin=vendor_gstin
        )
        
        clean_text = (text_content or "").strip().upper()
        
        # Check 1: Opt-Out / Opt-In
        if any(w in clean_text for w in ["STOP", "UNSUBSCRIBE", "BLOCK"]):
            if vendor_gstin:
                g.query("MATCH (v:Vendor {gstin: $gstin}) SET v.opted_out = true", {"gstin": vendor_gstin})
            reply_text = "You have been unsubscribed from automated WhatsApp payment and GST reminders. Reply START anytime to resume."
        elif any(w in clean_text for w in ["START", "RESUBSCRIBE", "SUBSCRIBE"]):
            if vendor_gstin:
                g.query("MATCH (v:Vendor {gstin: $gstin}) SET v.opted_out = false", {"gstin": vendor_gstin})
            reply_text = "You are now subscribed to automated invoice clearance and payment updates."
            
        # Check 2: Bill / Payment Status Inquiry
        elif any(w in clean_text for w in ["STATUS", "BILL", "PAYMENT", "PENDING", "HOLD", "KAB", "PAISE", "CLEAR"]):
            res_inv = g.query(
                """
                MATCH (i:Invoice)
                OPTIONAL MATCH (v:Vendor)-[:ISSUED]->(i)
                RETURN i.number, i.total, i.state, i.itc_status, coalesce(v.legal_name, 'Supplier')
                ORDER BY i.date DESC LIMIT 3
                """
            )
            if res_inv.result_set:
                lines = []
                for row in res_inv.result_set:
                    lines.append(f"• Bill #{row[0]}: Rs. {row[1]:,.2f} ({row[2]}, ITC: {row[3]})")
                inv_summary = "\n".join(lines)
                reply_text = f"📋 LedgerGraph Account Update:\n{inv_summary}\nContact CA firm for payment clearance."
            else:
                reply_text = "No pending invoices found on file. Please send an invoice PDF to initiate clearance."
                
        # Check 3: Filing / GSTR Update
        elif any(w in clean_text for w in ["GSTR", "2B", "3B", "FILED", "PORTAL"]):
            reply_text = "Thank you for the update! We will verify GSTR-2B reflection during our next automated reconciliation sync on the GST portal."
            
        # Default CA Firm Greeting
        else:
            reply_text = (
                f"Namaste! We received your message: \"{text_content[:60]}\". "
                f"Our CA team at Demo CA & Associates has logged your communication."
            )
            
        # Dispatch and Record Agent Outbound Reply
        wa_adapter.send_text(sender_phone, reply_text)
        outbound_msg = record_whatsapp_message(
            tenant_id=routed_tenant,
            direction="OUTBOUND",
            sender_phone="Agent WhatsApp Bot",
            recipient_phone=sender_phone,
            message_type="text",
            text=reply_text,
            status="DELIVERED",
            cost_inr=0.0,
            vendor_gstin=vendor_gstin
        )
        
        return {
            "status": "success",
            "routed_tenant": routed_tenant,
            "inbound_message": inbound_msg,
            "outbound_reply": outbound_msg
        }

def send_outbound_agent_message(
    tenant_id: str,
    to_phone: str,
    text: str,
    template_name: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    invoice_id: Optional[str] = None,
    user_id: str = "CA Partner"
) -> Dict[str, Any]:
    """
    Allows the CA Agent / Partner to dispatch outbound WhatsApp messages to suppliers/clients.
    """
    cost_inr = 0.35 if template_name else 0.0
    
    if template_name:
        res = wa_adapter.send_template(to_phone, template_name, params or {})
    else:
        res = wa_adapter.send_text(to_phone, text)
        
    msg = record_whatsapp_message(
        tenant_id=tenant_id,
        direction="OUTBOUND",
        sender_phone="CA Partner",
        recipient_phone=to_phone,
        message_type="template" if template_name else "text",
        text=text,
        invoice_id=invoice_id,
        status="DELIVERED",
        cost_inr=cost_inr,
        template_name=template_name
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="WHATSAPP_DISPATCH",
        user_id=user_id,
        payload={"message_id": msg["id"], "to_phone": to_phone, "cost_inr": cost_inr, "invoice_id": invoice_id}
    )
    
    return {
        "status": "sent",
        "message": msg
    }

def export_whatsapp_messages_csv(tenant_id: str) -> str:
    """
    Generates a statutory CSV audit trail of all WhatsApp messages.
    """
    data = get_whatsapp_messages(tenant_id, limit=1000)
    messages = data.get("messages", [])
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        "Message ID",
        "Timestamp (UTC)",
        "Direction",
        "Sender Phone",
        "Recipient Phone",
        "Message Type",
        "Invoice Number",
        "Vendor Name",
        "Status",
        "Cost (INR)",
        "Message Content"
    ])
    
    for m in messages:
        writer.writerow([
            m.get("id"),
            m.get("timestamp"),
            m.get("direction"),
            m.get("sender_phone"),
            m.get("recipient_phone"),
            m.get("message_type"),
            m.get("invoice_number") or m.get("invoice_id") or "N/A",
            m.get("vendor_name") or "N/A",
            m.get("status"),
            f"{m.get('cost_inr', 0.0):.2f}",
            m.get("text")
        ])
        
    return output.getvalue()
