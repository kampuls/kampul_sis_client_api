"""
Authentication services for different user types.
"""

import asyncio
import bcrypt
from sqlalchemy.orm import Session
from ..models import User, Student, Parent
from .student_auth import authenticate_student
from .parent_auth import authenticate_parent

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (supporting both bcrypt and Kampul scrypt)."""
    if not plain_password or not hashed_password:
        return False

    # Check for Kampul platform scrypt hash format: scrypt$N$r$p$salt_b64$key_b64
    if isinstance(hashed_password, str) and hashed_password.startswith("scrypt$"):
        try:
            import base64
            import hashlib
            import hmac
            parts = hashed_password.split("$")
            if len(parts) == 6:
                n = int(parts[1])
                r = int(parts[2])
                p = int(parts[3])
                salt = base64.b64decode(parts[4])
                expected = base64.b64decode(parts[5])
                actual = hashlib.scrypt(
                    plain_password.encode("utf-8"),
                    salt=salt,
                    n=n,
                    r=r,
                    p=p,
                    maxmem=64 * 1024 * 1024,
                    dklen=len(expected),
                )
                return hmac.compare_digest(actual, expected)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error checking scrypt password: {e}")
            return False

    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_password, hashed_password)
    except ValueError:
        import logging
        logging.getLogger(__name__).warning(
            "Refused login: stored password is not a valid hash"
        )
        return False


async def async_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Async bcrypt verification using thread pool to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, verify_password, plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    if isinstance(password, str):
        password = password.encode('utf-8')
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate a user (teacher/admin) with username and password."""
    from sqlalchemy.orm import defer
    user = db.query(User).options(defer(User.image), defer(User.signature)).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password):
        return None
    return user


async def async_authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Authenticate a user asynchronously (prevents bcrypt from blocking event loop)."""
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


__all__ = [
    "verify_password",
    "async_verify_password",
    "get_password_hash", 
    "authenticate_user",
    "async_authenticate_user",
    "authenticate_student",
    "authenticate_parent",
]
