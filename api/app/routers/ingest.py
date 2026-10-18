import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import require_tenant_access, get_current_user
from app.graph.client import firm_graph
from app.services.ingest import process_document

router = APIRouter(prefix="", tags=["ingest"])

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
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    save_path = Path(settings.DATA_DIR) / file.filename
    
    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    result = process_document(
        tenant_id=tenant_id,
        file_path=str(save_path),
        source="upload",
        user_id=user.get("email", "unknown")
    )
    
    return result

@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    payload: WhatsAppWebhookSimulate,
    tenant_id: Optional[str] = Depends(require_tenant_access)
):
    """
    WhatsApp Webhook endpoint.
    Accepts simulated payload, routes tenant by sender PhoneMap or header.
    """
    phone = payload.phone or "+919876543210"
    
    # Route tenant by phone if not in header
    routed_tenant = tenant_id
    if not routed_tenant:
        fg = firm_graph("demo")
        res = fg.query("MATCH (pm:PhoneMap {phone: $phone}) RETURN pm.tenant_id", {"phone": phone})
        if res.result_set and len(res.result_set) > 0:
            routed_tenant = res.result_set[0][0]
        else:
            routed_tenant = "apex" # Fallback to default
            
    # Resolve file path
    target_path = None
    if payload.media_path and os.path.exists(payload.media_path):
        target_path = payload.media_path
    elif payload.fixture_name:
        candidates = list(Path(settings.FIXTURES_DIR).glob(f"**/{payload.fixture_name}*"))
        if candidates:
            target_path = str(candidates[0])
            
    if not target_path:
        # Default fixture
        target_path = str(Path(settings.FIXTURES_DIR) / "bills" / "clean_intrastate.pdf")
        
    result = process_document(
        tenant_id=routed_tenant,
        file_path=target_path,
        source="whatsapp",
        sender_phone=phone,
        user_id="whatsapp_bot"
    )
    
    return {
        "status": "success",
        "routed_tenant": routed_tenant,
        "result": result
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
