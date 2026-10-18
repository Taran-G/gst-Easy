from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.audit import get_audit_trail
from app.core.security import require_tenant_access, get_current_user
from app.mcp.server import handle_mcp_tool_call, MCP_TOOL_DEFINITIONS
from app.services.chase import draft_vendor_chase, approve_and_send_chase
from app.services.impact import find_impact_path
from app.services.risk import (
    calculate_vendor_risk_ranking,
    calculate_hold_advice,
    check_rule_37_aging,
    get_rule37a_candidates,
    refresh_vendor_status,
    get_vendor_accounting_profile
)

router = APIRouter(prefix="", tags=["risk"])

class ChaseDraftRequest(BaseModel):
    invoice_id: str
    type: str = "missing_2b"
    language: str = "en"
    firm_name: Optional[str] = None
    custom_template: Optional[str] = None

class ChaseApproveRequest(BaseModel):
    invoice_id: str
    type: str = "missing_2b"
    language: str = "en"

class MCPCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]

@router.get("/risk/vendors")
def get_vendors_ranking(
    top_n: int = Query(10),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Returns suppliers ranked by PageRank, ITC at risk, and filing history."""
    return calculate_vendor_risk_ranking(tenant_id, top_n)

@router.get("/risk/vendors/{gstin}")
def get_vendor_profile(
    gstin: str,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Returns comprehensive real accounting, invoice transaction, and statutory risk profile for a supplier."""
    try:
        return get_vendor_accounting_profile(tenant_id, gstin)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/risk/impact")
def get_impact_trace(
    gstin: str = Query(..., description="Supplier GSTIN to trace impact for"),
    delay: int = Query(4, description="Simulated delay in days"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Centerpiece Multi-hop Impact Trace Query.
    Returns downstream customer delivery schedules, broken orders, ITC at risk,
    highlighted graph elements and exact Cypher.
    """
    return find_impact_path(tenant_id, gstin, delay)

@router.get("/risk/hold-advice")
def get_hold_advice_list(
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    return calculate_hold_advice(tenant_id, period)

@router.get("/rules37/aging")
def get_rule_37_aging_list(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    return check_rule_37_aging(tenant_id)

@router.get("/rules37a/candidates")
def get_rule_37a_candidates_list(
    fy: str = Query("2026-27"),
    period: str = Query("092026"),
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    return get_rule37a_candidates(tenant_id, fy, period)

@router.post("/chases/draft")
def draft_chase_endpoint(
    req: ChaseDraftRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    firm_name = req.firm_name or "Demo CA & Associates"
    return draft_vendor_chase(
        tenant_id=tenant_id,
        invoice_id=req.invoice_id,
        chase_type=req.type,
        lang=req.language,
        firm_name=firm_name,
        custom_template=req.custom_template
    )

@router.post("/chases/approve")
def approve_chase_endpoint(
    req: ChaseApproveRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    user_email = user.get("email", "CA Partner")
    return approve_and_send_chase(tenant_id, req.invoice_id, req.type, req.language, user_email)

@router.get("/audit")
def view_audit_log(
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Returns append-only tamper-evident audit trail with SHA-256 chain."""
    return get_audit_trail(tenant_id=tenant_id, firm_id=None)

@router.get("/mcp/tools")
def get_mcp_tools():
    """Lists available MCP tools and JSON schemas."""
    return MCP_TOOL_DEFINITIONS

@router.post("/mcp/call")
def execute_mcp_tool(
    req: MCPCallRequest,
    tenant_id: str = Depends(require_tenant_access),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Executes an MCP tool call."""
    args = req.arguments.copy()
    args["tenant_id"] = tenant_id
    try:
        return handle_mcp_tool_call(req.tool_name, args)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
