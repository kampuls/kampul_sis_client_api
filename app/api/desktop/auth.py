from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
import logging
from datetime import datetime, timedelta, timezone

from ...core import get_db, settings
from ...schemas import Token
from ...auth.services import async_authenticate_user
from ...models import User
from ...services import login_throttle
from ...utils.client_ip import throttle_ip

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login and get access token (defaults to teacher role) for Desktop App."""
    ip = throttle_ip(request)
    if login_throttle.is_locked(form_data.username, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(login_throttle.retry_after_seconds())},
        )
    user = await async_authenticate_user(db, form_data.username, form_data.password)
    if not user:
        login_throttle.record_failure(form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_throttle.clear(form_data.username, ip)
    
    if int(getattr(user, "status", 0) or 0) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Desktop user is inactive",
        )

    # Desktop tokens are intentionally scoped. Mobile/web tokens cannot call
    # the privileged compatibility data surface.
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.desktop_token_hours)
    access_token = jwt.encode(
        {
            "sub": user.username,
            "role": int(getattr(user, "role", 0) or 0),
            "user_id": int(user.id),
            "token_version": int(getattr(user, "token_version", 1) or 1),
            "scope": "desktop",
            "type": "desktop_access",
            "exp": expires_at,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
async def read_users_me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user information for Desktop App."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            credentials.credentials, 
            settings.secret_key, 
            algorithms=[settings.algorithm]
        )
        username: str = payload.get("sub")
        user_role = payload.get("role")
        user_id = payload.get("user_id")

        if user_role is None or payload.get("scope") != "desktop":
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
    
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    else:
        user = db.query(User).filter(User.username == username).first()

    if user is None or int(getattr(user, "status", 0) or 0) != 1:
        raise credentials_exception
    if int(payload.get("token_version") or 1) != int(
        getattr(user, "token_version", 1) or 1
    ):
        raise credentials_exception

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "user_type": "desktop_staff",
    }
