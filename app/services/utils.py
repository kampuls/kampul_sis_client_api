import bcrypt
import asyncio
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException
from starlette import status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import User, Student, Parent

# Password hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token security
security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash (synchronous — use async_verify_password in async routes)."""
    if isinstance(plain_password, str):
        plain_password_bytes = plain_password.encode('utf-8')
    else:
        plain_password_bytes = plain_password
    if isinstance(hashed_password, str):
        hashed_password_bytes = hashed_password.encode('utf-8')
    else:
        hashed_password_bytes = hashed_password
    return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)


async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Async bcrypt verification — runs in thread pool so the event loop is NEVER blocked.
    Use this in all async route handlers (login etc.) to prevent freezing under load.
    bcrypt takes ~200-400ms CPU; without this, 100 concurrent logins = 10s+ freeze.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, verify_password, plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password (synchronous)."""
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    else:
        password_bytes = password
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode('utf-8')


async def async_get_password_hash(password: str) -> str:
    """Async bcrypt hash — runs in thread pool so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_password_hash, password)

def create_short_lived_access_token(data: dict):
    """Create a short-lived JWT access token (default 2 hours, cannot be auto-refreshed)."""
    to_encode = data.copy()
    # Short-lived token: Configurable hours (Facebook-like)
    expire = datetime.utcnow() + timedelta(hours=settings.short_lived_token_hours)
    to_encode.update({"exp": expire, "type": "short_access"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def create_long_lived_access_token(data: dict):
    """Create a long-lived JWT access token (default 60 days, can be refreshed/extended before expiry)."""
    to_encode = data.copy()
    # Long-lived token: Configurable days (Facebook-like: can be refreshed/extended)
    expire = datetime.utcnow() + timedelta(days=settings.long_lived_token_days)
    to_encode.update({"exp": expire, "type": "long_access"})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token_payload(token: str) -> Optional[dict]:
    """Verify and decode a JWT token, returning the full payload."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return dict(payload)  # Convert to dict to satisfy type checker
    except JWTError:
        return None

def verify_long_lived_token(token: str) -> Optional[dict]:
    """Verify and decode a long-lived access token."""
    payload = verify_token_payload(token)
    if not payload:
        return None
    token_type = payload.get("type")
    if token_type != "long_access":
        return None
    return payload

def verify_token(token: str) -> Optional[str]:
    """Verify a JWT and return the username, but only for employee tokens.

    Callers resolve this against the ``users`` table. ``sub`` is not unique
    across tables, so a parent token must not be accepted here or it would be
    served the employee account sharing that username.
    """
    payload = verify_token_payload(token)
    if not payload:
        return None
    role = payload.get("role")
    numeric_employee_role = isinstance(role, int) or (
        isinstance(role, str) and role.isdigit()
    )
    if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
        return None
    username = payload.get("sub")
    if isinstance(username, str):
        return username
    return None

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = credentials.credentials
    username = verify_token(token)
    if username is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get the current active user."""
    # Access the actual attribute value (SQLAlchemy returns the value, not Column when accessed)
    # Use getattr with default to safely get the value, then convert to int
    status_value = getattr(current_user, 'status', None)
    user_status = int(status_value) if status_value is not None else 0
    if user_status == 1:  # 1 = active, 0 = inactive
        return current_user
    raise HTTPException(status_code=400, detail="Inactive user")

def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Get the current admin user."""
    # Access the actual attribute value (SQLAlchemy returns the value, not Column when accessed)
    # Use getattr with default to safely get the value, then convert to int
    role_value = getattr(current_user, 'role', None)
    user_role = int(role_value) if role_value is not None else 0
    if user_role == 1:  # 1 = admin, other numbers for different roles
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions"
    )

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user with username and password."""
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    # Convert SQLAlchemy column to string - handle None case properly
    user_password_str: str = ""
    if user.password is not None:
        user_password_str = str(user.password)
    if not user_password_str or not verify_password(password, user_password_str):
        return None
    return user

async def async_authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user asynchronously with username and password."""
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    user_password_str: str = ""
    if user.password is not None:
        user_password_str = str(user.password)
        
    db.expunge(user)
    db.rollback()
    
    if not user_password_str:
        return None
    is_valid = await async_verify_password(password, user_password_str)
    if not is_valid:
        return None
    return user


def authenticate_student(db: Session, username: str, password: str) -> Optional[Student]:
    """Authenticate a student with username and password."""
    from sqlalchemy.orm import defer
    student = db.query(Student).options(defer(Student.image)).filter(Student.username == username).first()
    if student is None:
        return None
    # Convert SQLAlchemy column to string - handle None case properly
    student_password_str: str = ""
    if student.password is not None:
        student_password_str = str(student.password)
    # Note: students might rely on plain text matching if legacy, but ideally use verify_password
    # Assuming hashed passwords for consistency with User
    if not student_password_str or not verify_password(password, student_password_str):
        return None
    return student

async def async_authenticate_student(db: Session, username: str, password: str) -> Optional[Student]:
    """Authenticate a student asynchronously with username and password."""
    from sqlalchemy.orm import defer
    student = db.query(Student).options(defer(Student.image)).filter(Student.username == username).first()
    if student is None:
        return None
    student_password_str: str = ""
    if student.password is not None:
        student_password_str = str(student.password)
        
    db.expunge(student)
    db.rollback()
    
    if not student_password_str:
        return None
    is_valid = await async_verify_password(password, student_password_str)
    if not is_valid:
        return None
    return student

def authenticate_parent(db: Session, username: str, password: str) -> Optional[Parent]:
    """Authenticate a parent with username and password."""
    parent = db.query(Parent).filter(Parent.username == username).first()
    if parent is None:
        return None
    # Convert SQLAlchemy column to string - handle None case properly
    parent_password_str: str = ""
    if parent.password is not None:
        parent_password_str = str(parent.password)
    if not parent_password_str or not verify_password(password, parent_password_str):
        return None
    return parent

async def async_authenticate_parent(db: Session, username: str, password: str) -> Optional[Parent]:
    """Authenticate a parent asynchronously with username and password."""
    parent = db.query(Parent).filter(Parent.username == username).first()
    if parent is None:
        return None
    parent_password_str: str = ""
    if parent.password is not None:
        parent_password_str = str(parent.password)
        
    db.expunge(parent)
    db.rollback()
    
    if not parent_password_str:
        return None
    is_valid = await async_verify_password(password, parent_password_str)
    if not is_valid:
        return None
    return parent


import os
import uuid
from fastapi import UploadFile

def save_upload_file(file_data: bytes, folder: str = "misc") -> Optional[str]:
    """
    Save uploaded bytes to disk and return the relative URL/path.
    
    Args:
        file_data: The binary data of the file.
        folder: The subfolder within 'uploads/' to save the file.
    
    Returns:
        str: The relative path to the saved file (e.g., '/uploads/avatars/uuid.jpg').
    """
    if not file_data:
        return None

    # Base upload directory
    base_upload_dir = "uploads"
    target_dir = os.path.join(base_upload_dir, folder)
    
    # Create directory if it doesn't exist
    os.makedirs(target_dir, exist_ok=True)
    
    # Generate unique filename
    # We don't know the extension from raw bytes easily without python-magic, 
    # but for now we can default to .jpg or try to infer, or just save without extension?
    # Better to assume it's an image if usage is for avatar.
    # Let's use a generic extension or just a UUID. 
    # Browsers often handle images without extensions or we can assume jpg/png.
    # Let's try to be safe and use .jpg as default for now as it's likely image data from the app.
    filename = f"{uuid.uuid4()}.jpg" 
    file_path = os.path.join(target_dir, filename)
    
    try:
        with open(file_path, "wb") as f:
            f.write(file_data)
        
        # Return relative path compatible with static file serving
        return f"/uploads/{folder}/{filename}"
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

