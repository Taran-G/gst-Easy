import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import require_tenant_access, get_current_user
from app.services.whatsapp import (
    get_whatsapp_messages,
    handle_incoming_whatsapp,
    send_outbound_agent_message,
    export_whatsapp_messages_csv
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

class WhatsAppTextSimulate(BaseModel):
    phone: str = "+919876543210"
    text: str = "Status of bill #INV-2026-001"

class WhatsAppSendRequest(BaseModel):
    to_phone: str
    text: str
    invoice_id: Optional[str] = None
    template_name: Optional[str] = None

@router.get("/messages")
def list_messages(
    limit: int = Query(50, ge=1, le=500),
    direction: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns WhatsApp communications log (inbound & outbound) for the tenant.
    """
    return get_whatsapp_messages(tenant_id, limit=limit, direction=direction, search=search)

@router.get("/export")
def export_messages(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Exports all WhatsApp messages into a statutory CSV working paper.
    """
    csv_data = export_whatsapp_messages_csv(tenant_id)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=whatsapp_ledger_{tenant_id}.csv"
        }
    )

@router.post("/simulate/bill")
async def simulate_incoming_bill(
    file: Optional[UploadFile] = File(None),
    fixture_name: Optional[str] = Form(None),
    phone: str = Form("+919876543210"),
    caption: Optional[str] = Form("Attached invoice copy for clearance"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Simulates receiving a WhatsApp message with an attached bill (PDF/Image)
    from a supplier or client, runs ingestion, and triggers the AI Agent's auto-reply.
    """
    save_path = None
    
    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in [".pdf", ".png", ".jpg", ".jpeg"]:
            raise HTTPException(status_code=400, detail="Only PDF, PNG, JPG files are supported.")
        os.makedirs(settings.DATA_DIR, exist_ok=True)
        unique_name = f"wa_{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
        save_path = Path(settings.DATA_DIR) / unique_name
        with open(save_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    elif fixture_name:
        fixture_file = Path(settings.FIXTURES_DIR) / "bills" / f"{fixture_name}.pdf"
        if not fixture_file.exists():
            fixture_file = Path(settings.FIXTURES_DIR) / "bills" / "golden" / f"{fixture_name}.json"
        if not fixture_file.exists():
            raise HTTPException(status_code=404, detail=f"Fixture '{fixture_name}' not found.")
        save_path = fixture_file
    else:
        # Default to clean_intrastate
        save_path = Path(settings.FIXTURES_DIR) / "bills" / "clean_intrastate.pdf"

    payload = {
        "phone": phone,
        "media_path": str(save_path),
        "text": caption or f"Bill attached: {Path(save_path).name}"
    }

    result = handle_incoming_whatsapp(payload, tenant_id=tenant_id)
    return result

@router.post("/simulate/text")
def simulate_incoming_text(
    req: WhatsAppTextSimulate,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Simulates receiving an incoming WhatsApp text message from a vendor or client.
    The agent parses intent (status, STOP opt-out, query) and replies automatically.
    """
    payload = {
        "phone": req.phone,
        "text": req.text,
        "media_path": None
    }
    return handle_incoming_whatsapp(payload, tenant_id=tenant_id)

@router.post("/send")
def send_agent_message(
    req: WhatsAppSendRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Dispatches an outbound WhatsApp message from the CA Agent to a vendor or client.
    """
    user_email = user.get("email", "CA Partner")
    return send_outbound_agent_message(
        tenant_id=tenant_id,
        to_phone=req.to_phone,
        text=req.text,
        template_name=req.template_name,
        invoice_id=req.invoice_id,
        user_id=user_email
    )
