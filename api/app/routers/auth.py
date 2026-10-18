from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.security import verify_password, hash_password, create_access_token, get_current_user
from app.graph.client import firm_graph
from app.graph.schema import bootstrap_tenant, bootstrap_firm

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    default_tenant_id: Optional[str] = "apex"

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "Admin"  # "Admin" (Accountant / CA Firm) or "Client" (Business Owner)
    firm_name: Optional[str] = "CA Associates"
    company_name: Optional[str] = None
    gstin: Optional[str] = None
    state_code: Optional[str] = None
    pain_points: Optional[List[str]] = Field(default_factory=list)
    monthly_invoice_volume: Optional[str] = "50-200"
    accounting_software: Optional[str] = "Tally Prime"

class CreateTenantRequest(BaseModel):
    name: str
    gstin: str
    state_code: Optional[str] = None
    filing_freq: Optional[str] = "Monthly"

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    # Lookup user across master firm registry
    fg = firm_graph("demo")
    
    res = fg.query(
        """
        MATCH (f:Firm)-[:HAS_USER]->(u:User {email: $email})
        RETURN u.id, u.email, u.password_hash, u.role, u.name, f.id, f.name, coalesce(u.client_tenant_id, "")
        """,
        {"email": req.email.strip().lower()}
    )
    
    if not res.result_set or len(res.result_set) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    u_id, u_email, u_pwhash, u_role, u_name, f_id, f_name, u_client_tenant_id = res.result_set[0]
    
    if not verify_password(req.password, u_pwhash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    token_data: Dict[str, Any] = {
        "user_id": u_id,
        "firm_id": f_id,
        "email": u_email,
        "role": u_role,
        "name": u_name,
        "firm_name": f_name
    }
    
    default_tenant = "apex"
    if u_client_tenant_id:
        token_data["client_tenant_id"] = u_client_tenant_id
        default_tenant = u_client_tenant_id
        
    token = create_access_token(token_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": token_data,
        "default_tenant_id": default_tenant
    }

@router.post("/signup", response_model=LoginResponse)
def signup(req: SignupRequest):
    fg = firm_graph("demo")
    clean_email = req.email.strip().lower()
    
    # 1. Check if user already exists
    existing = fg.query(
        "MATCH (u:User {email: $email}) RETURN count(u) > 0",
        {"email": clean_email}
    )
    if existing.result_set and bool(existing.result_set[0][0]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists. Please sign in."
        )

    pwhash = hash_password(req.password)
    user_id = f"u_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 2. Setup based on Role (CA Firm Accountant vs Business Client)
    if req.role == "Client":
        firm_id = "demo"
        firm_name = "Client Portal"
        
        # Client gets an isolated tenant dashboard for their company
        company = req.company_name or f"{req.name}'s Company"
        clean_slug = re.sub(r'[^a-zA-Z0-9]', '_', company.lower().strip())[:14]
        tenant_id = f"client_{clean_slug}_{uuid.uuid4().hex[:4]}"
        
        gstin = (req.gstin or "27AAACT1234A1Z5").strip().upper()
        state_code = req.state_code or (gstin[:2] if len(gstin) >= 2 else "27")
        
        # Bootstrap schema for tenant
        bootstrap_tenant(tenant_id)
        
        # Save in graph
        fg.query(
            """
            MATCH (f:Firm {id: $firm_id})
            MERGE (t:Tenant {id: $tenant_id})
            SET t.name = $company_name,
                t.gstin = $gstin,
                t.state_code = $state_code,
                t.filing_freq = "Monthly"
            MERGE (f)-[:OWNS_TENANT]->(t)
            
            MERGE (u:User {email: $email})
            SET u.id = $user_id,
                u.name = $name,
                u.role = "Client",
                u.password_hash = $pwhash,
                u.client_tenant_id = $tenant_id,
                u.pain_points = $pain_points,
                u.monthly_invoice_volume = $monthly_invoice_volume,
                u.accounting_software = $accounting_software,
                u.created_at = $created_at
            MERGE (f)-[:HAS_USER]->(u)
            MERGE (u)-[:ASSIGNED_TENANT]->(t)
            """,
            {
                "firm_id": firm_id,
                "tenant_id": tenant_id,
                "company_name": company,
                "gstin": gstin,
                "state_code": state_code,
                "email": clean_email,
                "user_id": user_id,
                "name": req.name,
                "pwhash": pwhash,
                "pain_points": str(req.pain_points),
                "monthly_invoice_volume": req.monthly_invoice_volume,
                "accounting_software": req.accounting_software,
                "created_at": now_iso
            }
        )
        
        token_data = {
            "user_id": user_id,
            "firm_id": firm_id,
            "email": clean_email,
            "role": "Client",
            "name": req.name,
            "firm_name": firm_name,
            "client_tenant_id": tenant_id
        }
        default_tenant = tenant_id

    else:
        # CA Firm Accountant / Admin
        firm_slug = re.sub(r'[^a-zA-Z0-9]', '_', (req.firm_name or "CA").lower().strip())[:12]
        firm_id = f"firm_{firm_slug}_{uuid.uuid4().hex[:4]}"
        firm_name = req.firm_name or "CA Practice"
        
        # Create initial client tenant for the accountant
        initial_client_name = req.company_name or "Apex Auto Parts"
        initial_slug = re.sub(r'[^a-zA-Z0-9]', '_', initial_client_name.lower().strip())[:14]
        tenant_id = f"{initial_slug}_{uuid.uuid4().hex[:4]}"
        gstin = (req.gstin or "06AAACA1234A1Z5").strip().upper()
        state_code = req.state_code or (gstin[:2] if len(gstin) >= 2 else "06")
        
        bootstrap_tenant(tenant_id)
        
        fg.query(
            """
            MERGE (f:Firm {id: $firm_id})
            SET f.name = $firm_name
            
            MERGE (t:Tenant {id: $tenant_id})
            SET t.name = $client_name,
                t.gstin = $gstin,
                t.state_code = $state_code,
                t.filing_freq = "Monthly"
            MERGE (f)-[:OWNS_TENANT]->(t)
            
            MERGE (u:User {email: $email})
            SET u.id = $user_id,
                u.name = $name,
                u.role = "Admin",
                u.password_hash = $pwhash,
                u.pain_points = $pain_points,
                u.monthly_invoice_volume = $monthly_invoice_volume,
                u.accounting_software = $accounting_software,
                u.created_at = $created_at
            MERGE (f)-[:HAS_USER]->(u)
            """,
            {
                "firm_id": firm_id,
                "firm_name": firm_name,
                "tenant_id": tenant_id,
                "client_name": initial_client_name,
                "gstin": gstin,
                "state_code": state_code,
                "email": clean_email,
                "user_id": user_id,
                "name": req.name,
                "pwhash": pwhash,
                "pain_points": str(req.pain_points),
                "monthly_invoice_volume": req.monthly_invoice_volume,
                "accounting_software": req.accounting_software,
                "created_at": now_iso
            }
        )
        
        token_data = {
            "user_id": user_id,
            "firm_id": firm_id,
            "email": clean_email,
            "role": "Admin",
            "name": req.name,
            "firm_name": firm_name
        }
        default_tenant = tenant_id

    token = create_access_token(token_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": token_data,
        "default_tenant_id": default_tenant
    }

@router.get("/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return user

@router.get("/tenants")
def get_user_tenants(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns accessible tenants.
    Clients are strictly restricted to their own assigned tenant.
    Accountants can see and switch across all client tenants owned by their firm.
    """
    # 1. If Client: only return their single tenant
    if user.get("role") == "Client":
        client_tenant_id = user.get("client_tenant_id")
        if not client_tenant_id:
            return []
            
        fg = firm_graph("demo")
        res = fg.query(
            """
            MATCH (t:Tenant {id: $tenant_id})
            RETURN t.id, t.name, t.gstin, t.state_code, t.filing_freq
            """,
            {"tenant_id": client_tenant_id}
        )
        tenants = []
        for r in (res.result_set or []):
            tenants.append({
                "id": r[0],
                "name": r[1],
                "gstin": r[2],
                "state_code": r[3],
                "filing_freq": r[4]
            })
        return tenants

    # 2. Accountant / CA Firm: Return all client tenants owned by firm
    firm_id = user["firm_id"]
    fg = firm_graph("demo")
    
    res = fg.query(
        """
        MATCH (f:Firm {id: $firm_id})-[:OWNS_TENANT]->(t:Tenant)
        RETURN t.id, t.name, t.gstin, t.state_code, t.filing_freq
        ORDER BY t.name ASC
        """,
        {"firm_id": firm_id}
    )
    
    # Fallback to apex & greenleaf if demo firm or newly provisioned
    tenants = []
    for r in (res.result_set or []):
        tenants.append({
            "id": r[0],
            "name": r[1],
            "gstin": r[2],
            "state_code": r[3],
            "filing_freq": r[4]
        })
        
    if not tenants and firm_id == "demo":
        tenants = [
            {"id": "apex", "name": "Apex Auto Parts", "gstin": "06AAACA1234A1Z5", "state_code": "06", "filing_freq": "Monthly"},
            {"id": "greenleaf", "name": "Greenleaf Traders", "gstin": "24AABCG5678B1Z2", "state_code": "24", "filing_freq": "Monthly"}
        ]
        
    return tenants

@router.post("/tenants")
def create_client_tenant(
    req: CreateTenantRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Enables accountants to create new client dashboards.
    Clients are forbidden from creating tenants.
    """
    if user.get("role") == "Client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client accounts cannot create new client dashboards"
        )
        
    clean_name = req.name.strip()
    clean_gstin = req.gstin.strip().upper()
    if len(clean_gstin) != 15:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GSTIN must be exactly 15 characters (e.g. 06AAACA1234A1Z5)"
        )
        
    state_code = req.state_code or clean_gstin[:2]
    clean_slug = re.sub(r'[^a-zA-Z0-9]', '_', clean_name.lower())[:16]
    tenant_id = f"client_{clean_slug}_{uuid.uuid4().hex[:4]}"
    
    # Bootstrap schema for this tenant
    bootstrap_tenant(tenant_id)
    
    firm_id = user["firm_id"]
    fg = firm_graph("demo")
    
    fg.query(
        """
        MERGE (f:Firm {id: $firm_id})
        MERGE (t:Tenant {id: $tenant_id})
        SET t.name = $name,
            t.gstin = $gstin,
            t.state_code = $state_code,
            t.filing_freq = $filing_freq
        MERGE (f)-[:OWNS_TENANT]->(t)
        """,
        {
            "firm_id": firm_id,
            "tenant_id": tenant_id,
            "name": clean_name,
            "gstin": clean_gstin,
            "state_code": state_code,
            "filing_freq": req.filing_freq or "Monthly"
        }
    )
    
    return {
        "id": tenant_id,
        "name": clean_name,
        "gstin": clean_gstin,
        "state_code": state_code,
        "filing_freq": req.filing_freq or "Monthly"
    }
