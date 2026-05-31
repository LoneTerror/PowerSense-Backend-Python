import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.client import get_db
from src.database.models import User
from src.common.security import SECRET_KEY, ALGORITHM

# This tells FastAPI to look for an "Authorization: Bearer <token>" header
token_auth_scheme = HTTPBearer()

async def get_current_token_payload(credentials: HTTPAuthorizationCredentials = Depends(token_auth_scheme)):
    """Validates the JWT and extracts the payload."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid token type. Please use an Access Token."
            )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

async def require_admin(payload: dict = Depends(get_current_token_payload)):
    """RBAC Lock: Only allows users with the 'admin' role."""
    role = payload.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="RBAC: You do not have permission to perform this action."
        )
    return payload

async def get_current_user_id(
    token_payload: dict = Depends(get_current_token_payload), 
    db: AsyncSession = Depends(get_db)
) -> int:
    """Extracts the email from the JWT and returns the user's Database ID."""
    email = token_payload.get("sub")
    query = select(User.id).where(User.email == email)
    user_id = (await db.execute(query)).scalar_one_or_none()
    
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user_id