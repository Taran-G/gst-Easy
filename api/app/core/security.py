from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
import bcrypt
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings
from app.graph.client import firm_graph

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = payload.get("user_id")
    firm_id = payload.get("firm_id")
    if not user_id or not firm_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user_id or firm_id claims",
        )
    return payload

def require_tenant_access(
    tenant_id: Optional[str] = Header(None, alias="X-Tenant"),
    user: Dict[str, Any] = Depends(get_current_user)
) -> str:
    """
    Checks that the user's firm owns the requested tenant.
    Raises 403 Forbidden if the tenant does not belong to the user's firm.
    """
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant header is required"
        )
    
    # Strict Client isolation: A client can ONLY access their assigned tenant
    if user.get("role") == "Client":
        allowed_tenant = user.get("client_tenant_id")
        if not allowed_tenant or tenant_id != allowed_tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Client is strictly limited to dashboard '{allowed_tenant}'"
            )
        return tenant_id

    firm_id = user["firm_id"]
    fg = firm_graph("demo")
    
    # Verify firm owns tenant (or if demo firm owns default tenants)
    res = fg.query(
        "MATCH (f:Firm)-[:OWNS_TENANT]->(t:Tenant {id: $tenant_id}) WHERE f.id = $firm_id OR f.id = 'demo' RETURN count(t) > 0 AS owns",
        {"firm_id": firm_id, "tenant_id": tenant_id}
    )
    
    owns = False
    if res.result_set and len(res.result_set) > 0:
        owns = bool(res.result_set[0][0])
        
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Tenant '{tenant_id}' is not owned by Firm '{firm_id}'"
        )
        
    return tenant_id
