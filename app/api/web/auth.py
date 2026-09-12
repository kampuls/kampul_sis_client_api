from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
import logging

from ...core import get_db, settings
from ...schemas import Token
from ...services import (
    authenticate_user,
    async_authenticate_user,
    create_short_lived_access_token
)
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
    db: Session = Depends(get_db)
):
    """
    Login for the Web Admin Dashboard.
    Only users in the `users` table (teachers/employees) are allowed.
    Uses username + password authentication.
    """
    ip = throttle_ip(request)
    if login_throttle.is_locked(form_data.username, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(login_throttle.retry_after_seconds())},
        )

    # Authenticate against the `users` table only
    user = await async_authenticate_user(db, form_data.username, form_data.password)

    if not user:
        login_throttle.record_failure(form_data.username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_throttle.clear(form_data.username, ip)

    # Block inactive users (status != 1)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive. Please contact an administrator.",
        )

    # Create a short-lived access token encoding the user's basic info
    access_token = create_short_lived_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,       # integer role ID
        }
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Get current user profile for Web Dashboard."""
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
        user_id: int = payload.get("user_id")
        username: str = payload.get("sub")
        role = payload.get("role")
    except JWTError:
        raise credentials_exception

    # SECURITY: `users`, `parents` and `students` have independent ID sequences,
    # so a parent token must never be resolved against the employee table — it
    # would return the employee who happens to share the parent's ID.
    numeric_employee_role = isinstance(role, int) or (
        isinstance(role, str) and role.isdigit()
    )
    if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
        raise credentials_exception

    # Lookup from `users` table only
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    else:
        user = db.query(User).filter(User.username == username).first()

    if user is None:
        raise credentials_exception

    # Block if user became inactive after token was issued
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    return {
        "id": user.id,
        "username": user.username,
        "email": getattr(user, "email", None),
        "name_en": user.eName,
        "name_kh": user.kName,
        "role": user.role,
        "status": user.status,
        "phone": getattr(user, "phone", None),
        "user_type": "user",  # clearly marks as teacher/employee
    }
