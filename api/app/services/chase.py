import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from app.adapters.whatsapp_mock import MockWhatsAppAdapter
from app.core.audit import record_audit_event
from app.core.rules import get_rules
from app.graph.client import tenant_graph

whatsapp_adapter = MockWhatsAppAdapter()

TEMPLATES = {
    "missing_2b": {
        "en": "Dear {supplier_name}, invoice #{invoice_number} dated {date} for Rs. {amount} has not yet appeared in our GSTR-2B. Please file or report it in your GSTR-1 to prevent GST payment hold.",
        "hi": "नमस्ते {supplier_name}, आपका बिल #{invoice_number} दिनांक {date} राशि Rs. {amount} हमारे GSTR-2B में उपलब्ध नहीं है। कृपया इसे अपने GSTR-1 में दर्ज करें ताकि भुगतान में कोई रुकावट न हो।"
    },
    "gstr3b_pending": {
        "en": "Dear {supplier_name}, GSTR-3B for period {period} appears pending for your GSTIN {gstin}. Kindly complete filing to ensure seamless credit clearance.",
        "hi": "नमस्ते {supplier_name}, आपके GSTIN {gstin} के लिए माह {period} का GSTR-3B लंबित दिख रहा है। कृपया इसे शीघ्र दाखिल करें।"
    },
    "missing_bill_copy": {
        "en": "Dear {supplier_name}, invoice #{invoice_number} for Rs. {amount} reflects in our GSTR-2B but is missing in our physical books. Please reply with a PDF copy of this bill.",
        "hi": "नमस्ते {supplier_name}, बिल #{invoice_number} राशि Rs. {amount} हमारे GSTR-2B में दिख रहा है लेकिन हमारे पास इसकी प्रति नहीं है। कृपया इसकी PDF कॉपी भेजें।"
    }
}

def check_chase_eligibility(tenant_id: str, gstin: str) -> Dict[str, Any]:
    """Verifies opt-out status and rate limits (max 1 chase / 3 days, 3 total)."""
    g = tenant_graph(tenant_id)
    rules = get_rules()
    cooldown_days = rules.chase_limits.get("cooldown_days", 3)
    max_chases = rules.chase_limits.get("max_chases_per_issue", 3)
    
    # Check vendor opt-out
    res_v = g.query("MATCH (v:Vendor {gstin: $gstin}) RETURN v.opted_out", {"gstin": gstin})
    if res_v.result_set and bool(res_v.result_set[0][0]):
        return {"allowed": False, "reason": "Supplier has opted out of automated WhatsApp reminders (STOP received)."}
        
    # Check chase history
    res_c = g.query(
        """
        MATCH (v:Vendor {gstin: $gstin})-[:ISSUED]->(i:Invoice)-[:CHASED_VIA]->(c:VendorChase)
        RETURN c.sent_at ORDER BY c.sent_at DESC
        """,
        {"gstin": gstin}
    )
    
    chases = res_c.result_set
    if len(chases) >= max_chases:
        return {"allowed": False, "reason": f"Maximum chase limit ({max_chases}) reached for this supplier."}
        
    if chases:
        last_sent_str = chases[0][0]
        try:
            last_sent = datetime.fromisoformat(last_sent_str)
            if datetime.now(timezone.utc) - last_sent < timedelta(days=cooldown_days):
                return {"allowed": False, "reason": f"Rate limit active: A chase was already sent within the last {cooldown_days} days."}
        except Exception:
            pass
            
    return {"allowed": True, "reason": "Eligible to draft and send reminder."}

def draft_vendor_chase(
    tenant_id: str,
    invoice_id: str,
    chase_type: str = "missing_2b",
    lang: str = "en"
) -> Dict[str, Any]:
    """Drafts a pre-approved utility-category WhatsApp reminder."""
    g = tenant_graph(tenant_id)
    
    res = g.query(
        """
        MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {id: $id})
        RETURN v.gstin, v.legal_name, v.phone, i.number, i.date, i.total, (i.cgst + i.sgst + i.igst) AS tax
        """,
        {"id": invoice_id}
    )
    
    if not res.result_set or len(res.result_set) == 0:
        raise ValueError(f"Invoice '{invoice_id}' not found")
        
    gstin, name, phone, number, inv_date, total, tax = res.result_set[0]
    
    eligibility = check_chase_eligibility(tenant_id, gstin)
    
    tmpl_map = TEMPLATES.get(chase_type, TEMPLATES["missing_2b"])
    template_text = tmpl_map.get(lang, tmpl_map["en"])
    
    rendered_text = template_text.format(
        supplier_name=name,
        invoice_number=number,
        date=inv_date,
        amount=f"{float(total):.2f}",
        gstin=gstin,
        period="092026"
    )
    
    rules = get_rules()
    cost_inr = rules.chase_limits.get("message_costs_inr", {}).get("utility", 0.35)
    
    return {
        "invoice_id": invoice_id,
        "vendor_gstin": gstin,
        "vendor_name": name,
        "phone": phone or "+919876543210",
        "chase_type": chase_type,
        "language": lang,
        "rendered_text": rendered_text,
        "cost_inr": cost_inr,
        "eligible": eligibility["allowed"],
        "eligibility_reason": eligibility["reason"]
    }

def approve_and_send_chase(
    tenant_id: str,
    invoice_id: str,
    chase_type: str = "missing_2b",
    lang: str = "en",
    user_id: str = "CA Partner"
) -> Dict[str, Any]:
    """Sends the approved chase and records :VendorChase node and audit event."""
    draft = draft_vendor_chase(tenant_id, invoice_id, chase_type, lang)
    if not draft["eligible"]:
        raise ValueError(f"Cannot send chase: {draft['eligibility_reason']}")
        
    g = tenant_graph(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    chase_id = f"chase_{int(datetime.now().timestamp())}"
    
    # Send through mock adapter
    sent_res = whatsapp_adapter.send_template(
        to_phone=draft["phone"],
        template_name=f"gst_reminder_{chase_type}",
        params={"supplier_name": draft["vendor_name"], "invoice_number": draft["invoice_id"]},
        lang=lang
    )
    
    # Record :VendorChase node in graph
    g.query(
        """
        MATCH (i:Invoice {id: $inv_id})
        CREATE (c:VendorChase {
            id: $id,
            channel: "whatsapp",
            template: $template,
            lang: $lang,
            cost_inr: $cost,
            sent_at: $now,
            status: "DELIVERED",
            approved_by: $user
        })
        CREATE (i)-[:CHASED_VIA]->(c)
        """,
        {
            "inv_id": invoice_id,
            "id": chase_id,
            "template": f"gst_reminder_{chase_type}",
            "lang": lang,
            "cost": draft["cost_inr"],
            "now": now_iso,
            "user": user_id
        }
    )
    
    record_audit_event(
        tenant_id=tenant_id,
        firm_id=None,
        event_type="CHASE",
        user_id=user_id,
        payload={"invoice_id": invoice_id, "chase_id": chase_id, "cost_inr": draft["cost_inr"]}
    )
    
    return {
        "status": "sent",
        "chase_id": chase_id,
        "phone": draft["phone"],
        "rendered_text": draft["rendered_text"],
        "cost_inr": draft["cost_inr"]
    }
