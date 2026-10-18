from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.core.security import verify_password, create_access_token, get_current_user
from app.graph.client import firm_graph

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    # In multi-tenant firm architecture, find user across firms (default firm 'demo' or email lookup)
    firm_id = "demo"
    fg = firm_graph(firm_id)
    
    res = fg.query(
        """
        MATCH (f:Firm)-[:HAS_USER]->(u:User {email: $email})
        RETURN u.id, u.email, u.password_hash, u.role, u.name, f.id, f.name
        """,
        {"email": req.email.strip().lower()}
    )
    
    if not res.result_set or len(res.result_set) == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    u_id, u_email, u_pwhash, u_role, u_name, f_id, f_name = res.result_set[0]
    
    if not verify_password(req.password, u_pwhash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    token_data = {
        "user_id": u_id,
        "firm_id": f_id,
        "email": u_email,
        "role": u_role,
        "name": u_name,
        "firm_name": f_name
    }
    
    token = create_access_token(token_data)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": token_data
    }

@router.get("/me")
def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return user

@router.get("/tenants")
def get_user_tenants(user: Dict[str, Any] = Depends(get_current_user)):
    """Returns all tenants owned by the user's firm."""
    firm_id = user["firm_id"]
    fg = firm_graph(firm_id)
    
    res = fg.query(
        """
        MATCH (f:Firm {id: $firm_id})-[:OWNS_TENANT]->(t:Tenant)
        RETURN t.id, t.name, t.gstin, t.state_code, t.filing_freq
        ORDER BY t.name ASC
        """,
        {"firm_id": firm_id}
    )
    
    tenants = []
    for r in res.result_set:
        tenants.append({
            "id": r[0],
            "name": r[1],
            "gstin": r[2],
            "state_code": r[3],
            "filing_freq": r[4]
        })
    return tenants
