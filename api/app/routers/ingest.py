import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import firm_graph
from app.services.ingest import process_document
from app.adapters.whatsapp_cloud import MetaWhatsAppCloudAdapter

router = APIRouter(prefix="", tags=["ingest"])
wa_adapter = MetaWhatsAppCloudAdapter()

class WhatsAppWebhookSimulate(BaseModel):
    phone: Optional[str] = "+919876543210"
    media_path: Optional[str] = None
    fixture_name: Optional[str] = None
    text: Optional[str] = "Attached bill for payment"

@router.post("/ingest/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Multipart document upload for review queue."""
    # 1. Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    allowed_exts = [".pdf", ".png", ".jpg", ".jpeg"]
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Allowed formats: PDF, PNG, JPG, JPEG"
        )
        
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    clean_stem = Path(file.filename or "upload").stem.replace(" ", "_")
    unique_filename = f"{uuid.uuid4().hex[:10]}_{clean_stem}{ext}"
    save_path = Path(settings.DATA_DIR) / unique_filename
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Check file size limit
    file_size_mb = save_path.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        save_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB}MB"
        )
        
    result = process_document(
        tenant_id=tenant_id,
        file_path=str(save_path),
        source="upload",
        user_id=user.get("email", "unknown")
    )
    
    return result

@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")
):
    """
    Meta WhatsApp Cloud API Webhook Verification.
    Responds to Meta's setup challenge with hub.challenge.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256")
):
    """
    Production Meta WhatsApp Cloud API Webhook Event Receiver.
    Accepts Meta JSON payload or simulated JSON, verifies signature,
    downloads media from Meta Graph API, maps tenant, and processes invoice.
    """
    raw_body = await request.body()
    
    # 1. Verify Meta HMAC SHA-256 signature if configured
    if settings.WHATSAPP_APP_SECRET and not wa_adapter.verify_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
        
    try:
        payload = await request.json()
    except Exception:
        payload = {}
        
    # 2. Process event via central whatsapp service
    from app.services.whatsapp import handle_incoming_whatsapp
    result = handle_incoming_whatsapp(payload)
    if result.get("status") == "ignored_status_or_empty":
        return result
        
    return {
        "status": "success",
        "routed_tenant": result.get("routed_tenant", "apex"),
        "invoice_id": result.get("invoice_id"),
        "state": result.get("state"),
        "reply": result.get("outbound_reply", {}).get("text")
    }

@router.post("/ingest/simulate")
async def simulate_submission(
    fixture_name: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Convenient endpoint for UI 'Simulate WhatsApp' button.
    Loads matching fixture file directly into the tenant's review queue.
    """
    # Look up in fixtures/bills/
    file_path = Path(settings.FIXTURES_DIR) / "bills" / f"{fixture_name}.pdf"
    if not file_path.exists():
        # Fallback to golden json as input if file doesn't exist
        file_path = Path(settings.FIXTURES_DIR) / "bills" / "golden" / f"{fixture_name}.json"
        
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Fixture '{fixture_name}' not found in {settings.FIXTURES_DIR}/bills"
        )
        
    result = process_document(
        tenant_id=tenant_id,
        file_path=str(file_path),
        source="whatsapp_simulated",
        sender_phone="+919876543210",
        user_id=user.get("email", "demo_simulator")
    )
    
    return result

@router.post("/ingest/reset-demo")
async def reset_demo_state(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Resets the demo graphs for clean testing and eliminates duplicate entries.
    """
    from app.seed import seed_database
    seed_database(reset=True)
    return {"status": "success", "message": "Demo state successfully reset to clean baseline."}
