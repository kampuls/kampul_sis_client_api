import bcrypt
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import User, Student, Teacher, Class

# Password hashing
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token security
security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    return bcrypt.checkpw(plain_password, hashed_password)

async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Async bcrypt verification to avoid blocking the event loop."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, verify_password, plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    if isinstance(password, str):
        password = password.encode('utf-8')
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[str]:
    """Verify a JWT and return the username, but only for employee tokens.

    ``sub`` is not globally unique: a parent may hold a username that also
    exists in ``users``. Resolving any token's ``sub`` against the employee
    table would hand that parent the employee's account, so non-employee roles
    are rejected here rather than at each call site.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            return None
        role = payload.get("role")
        numeric_employee_role = isinstance(role, int) or (
            isinstance(role, str) and role.isdigit()
        )
        if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
            return None
        return username
    except JWTError:
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
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Get the current admin user."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user with username and password."""
    from sqlalchemy.orm import defer
    user = db.query(User).options(defer(User.image), defer(User.signature)).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user

async def async_authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate a user asynchronously with username and password."""
    from sqlalchemy.orm import defer
    user = db.query(User).options(defer(User.image), defer(User.signature)).filter(User.username == username).first()
    if not user:
        return None
        
    db.expunge(user)
    db.rollback()
    
    is_valid = await async_verify_password(password, user.password)
    if not is_valid:
        return None
    return user


def generate_student_id(db: Session) -> str:
    """Generate a unique student ID."""
    last_student = db.query(Student).order_by(Student.id.desc()).first()
    if last_student:
        last_id = int(last_student.student_id.split('S')[-1])
        return f"STU{last_id + 1:04d}"
    return "STU0001"

def generate_teacher_id(db: Session) -> str:
    """Generate a unique teacher ID."""
    last_teacher = db.query(Teacher).order_by(Teacher.id.desc()).first()
    if last_teacher:
        last_id = int(last_teacher.teacher_id.split('T')[-1])
        return f"TCH{last_id + 1:04d}"
    return "TCH0001"

def generate_class_code(db: Session, subject: str) -> str:
    """Generate a unique class code."""
    # Get classes with the same subject in current academic year
    current_year = datetime.now().year
    similar_classes = db.query(Class).filter(
        Class.subject == subject,
        Class.academic_year == str(current_year)
    ).count()
    
    return f"{subject.upper()}{current_year}{similar_classes + 1:02d}"
