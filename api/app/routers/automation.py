from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import require_tenant_access, get_current_user
from app.services.automation import agent_engine
from app.services.email_service import email_service
from app.core.config import settings

router = APIRouter(prefix="/automation", tags=["automation"])

class ToggleRequest(BaseModel):
    enabled: bool

class IntervalRequest(BaseModel):
    interval_seconds: int

class SimulateIncomingEmailRequest(BaseModel):
    from_addr: str = "sharma@sharmasteels.com"
    subject: str = "Tax Invoice from Sharma Steels Ltd — Apex Auto Parts"
    body: str = "Dear Accounts Team,\n\nPlease find attached tax invoice copy from Sharma Steels Ltd for material delivered. Kindly process payment.\n\nRegards,\nSharma Steels Ltd"
    fixture_name: Optional[str] = "clean_intrastate"
    company_name: Optional[str] = "Sharma Steels Ltd"
    is_gstr2b_notification: Optional[bool] = False

class ConfigureEmailRequest(BaseModel):
    mode: str = "prototype"  # prototype | live_gmail
    username: Optional[str] = ""
    password: Optional[str] = ""
    imap_server: Optional[str] = "imap.gmail.com"
    smtp_server: Optional[str] = "smtp.gmail.com"

@router.get("/status")
def get_automation_status(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Returns current status, metrics, and live activity stream of the Autonomous AI Agent.
    """
    email_data = email_service.get_all_emails()
    return {
        "is_running": agent_engine.is_running,
        "interval_seconds": agent_engine.interval_seconds,
        "cycle_count": agent_engine.cycle_count,
        "last_run": agent_engine.last_run,
        "next_run": agent_engine.next_run,
        "invoices_processed_count": agent_engine.invoices_processed_count,
        "alerts_generated_count": agent_engine.alerts_generated_count,
        "email_mode": email_service.mode,
        "email_username": email_service.username or "invoices@apexautoparts.com",
        "email_unread_count": email_data["unread_count"],
        "logs": list(agent_engine.logs)
    }

@router.post("/toggle")
def toggle_automation(
    req: ToggleRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Enables or pauses the Autonomous Agent background loop.
    """
    if req.enabled:
        agent_engine.start()
    else:
        agent_engine.pause()
    return {"status": "success", "is_running": agent_engine.is_running}

@router.post("/interval")
def set_automation_interval(
    req: IntervalRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Updates the agent polling frequency in seconds (e.g. 10, 30, 60).
    """
    agent_engine.set_interval(req.interval_seconds)
    return {"status": "success", "interval_seconds": agent_engine.interval_seconds}

@router.post("/run-now")
async def trigger_agent_cycle_now(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Manually triggers an immediate autonomous cycle.
    """
    summary = await agent_engine.run_cycle(manual=True)
    return {"status": "success", "summary": summary}

@router.get("/emails")
def get_monitored_emails(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Lists all inbox and sent emails in the agent's email monitoring channel.
    """
    return email_service.get_all_emails()

@router.post("/email/simulate-incoming")
async def simulate_incoming_vendor_email(
    req: SimulateIncomingEmailRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Simulates a supplier sending an email with an invoice attachment.
    The email is dropped into the agent's watched inbox and automatically processed!
    """
    if req.is_gstr2b_notification:
        from_addr = "donotreply@gst.gov.in"
        subject = req.subject or "Intimation of auto-drafted ITC statement in Form GSTR-2B for September 2026 (092026)"
        body_text = req.body or "Dear Taxpayer,\n\nForm GSTR-2B for tax period September 2026 (092026) has been generated and is available on the GST Portal for GSTIN 06AAACA1234A1Z5.\n\nReconcile your Input Tax Credit (ITC) before filing GSTR-3B."
        fixture_name = None
    else:
        from_addr = req.from_addr
        subject = req.subject
        body_text = req.body
        fixture_name = req.fixture_name

    new_eml = email_service.simulate_incoming_email(
        from_addr=from_addr,
        subject=subject,
        body_text=body_text,
        fixture_name=fixture_name
    )
    
    agent_engine.log(
        "EMAIL_DELIVERED",
        f"New incoming email dropped in watched inbox: '{subject}' from {from_addr}.",
        "INFO"
    )

    return {
        "status": "delivered_to_inbox",
        "message": "Email landed in monitored inbox. The autonomous agent will pick it up on the next cycle.",
        "email": new_eml
    }

@router.post("/email/configure")
def configure_email(
    req: ConfigureEmailRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Configures live Gmail IMAP/SMTP credentials or prototype mode.
    """
    email_service.mode = req.mode
    if req.username:
        email_service.username = req.username
    if req.password:
        email_service.password = req.password
    if req.imap_server:
        email_service.imap_server = req.imap_server
    if req.smtp_server:
        email_service.smtp_server = req.smtp_server

    agent_engine.log(
        "CONFIG_CHANGED",
        f"Email monitoring mode updated to '{req.mode}' (User: {req.username or 'local prototype'}).",
        "INFO"
    )

    return {
        "status": "success",
        "mode": email_service.mode,
        "username": email_service.username or "invoices@apexautoparts.com"
    }
