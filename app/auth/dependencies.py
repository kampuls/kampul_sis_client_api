"""
Authentication dependencies for FastAPI.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Union

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import text
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError

from ..core import get_db, settings
from ..models import User, Parent, DeviceToken

security = HTTPBearer()


# ``users``, ``parents`` and ``students`` are separate tables with independent
# auto-increment IDs, so the same integer identifies three different people.
# Any table that stores a bare ``user_id`` (group membership, bans, avatars…)
# must therefore be filtered by the owning table as well. These are the values
# such ``user_type`` columns use for each kind of principal.
STAFF_MEMBER_TYPES: Tuple[str, ...] = ("teacher", "employee")
PARENT_MEMBER_TYPES: Tuple[str, ...] = ("parent",)
STUDENT_MEMBER_TYPES: Tuple[str, ...] = ("student",)


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, with the table their ID belongs to.

    Passing this around instead of a bare ``int`` is what keeps parent #57 from
    being mistaken for employee #57.
    """

    id: int
    kind: str  # "teacher" | "parent" | "student"
    member_types: Tuple[str, ...]


def principal_from_user(current_user) -> Principal:
    """Build a :class:`Principal` from whatever ``get_current_active_user`` returned."""
    if getattr(current_user, "is_parent", False) or getattr(current_user, "user_type", None) == "parent":
        return Principal(int(current_user.id), "parent", PARENT_MEMBER_TYPES)
    return Principal(int(current_user.id), "teacher", STAFF_MEMBER_TYPES)



def _parent_as_user(parent: Parent):
    """Adapter so Parent can be used where User is expected (id, eName, kName, username)."""
    return type(
        "ParentAsUser",
        (),
        {
            "id": parent.id,
            "eName": parent.fatherName or parent.motherName or "Parent",
            "kName": parent.motherName or parent.fatherName or "",
            "username": parent.username or str(parent.id),
            "is_parent": True,
            "role": "parent",       # needed for permission checks
            "user_type": "parent",
        },
    )()


def get_current_active_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Union[User, object]:
    """Get the current active user from JWT token. Supports both users (teachers) and parents."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # No header version check required; handled purely by client side now.

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("user_id")
        username = payload.get("sub")
        role = payload.get("role")
        token_version = payload.get("token_version")

        # Resolve the token's declared principal type before looking at a
        # numeric ID. IDs overlap across users, students, and parents, so a
        # student/parent token must never fall through to the employee table.
        if role == "parent":
            parent_query = db.query(Parent)
            if user_id is not None:
                parent_query = parent_query.filter(Parent.id == user_id)
            elif username is not None:
                parent_query = parent_query.filter(Parent.username == username)
            else:
                raise credentials_exception
            parent = parent_query.first()
            if parent is not None:
                # Same revocation rule employees already had. A token with no
                # version claim predates the column and stays valid until the
                # parent's number is bumped, so nobody is signed out by the
                # column simply existing.
                db_version = getattr(parent, "token_version", 1) or 1
                if token_version is not None:
                    if int(token_version) != int(db_version):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                elif int(db_version) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                return _parent_as_user(parent)
            raise credentials_exception

        # This dependency intentionally supports employee/admin and parent
        # principals. Student authentication has its own dependency. Rejecting
        # other declared roles prevents cross-table ID/username collisions.
        numeric_employee_role = isinstance(role, int) or (
            isinstance(role, str) and role.isdigit()
        )
        if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
            raise credentials_exception

        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user is None:
                raise credentials_exception

            # "Active" must be enforced from the database on every request.
            # A previously-issued JWT must not keep working after an employee
            # is disabled by an administrator.
            if int(getattr(user, "status", 0) or 0) != 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This employee account is inactive",
                )

            db_version = getattr(user, "token_version", 1) or 1

            # New tokens: must match exact token_version
            if token_version is not None:
                if int(token_version) != int(db_version):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            else:
                # Old tokens issued before token_version existed:
                # if the user has ever been force-logged-out (db_version > 1),
                # treat this legacy token as revoked too.
                if int(db_version) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )



            return user

        if username is not None:
            user = db.query(User).filter(User.username == username).first()
            if user is not None:
                if int(getattr(user, "status", 0) or 0) != 1:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="This employee account is inactive",
                    )
                db_version = getattr(user, "token_version", 1) or 1
                if token_version is not None:
                    if int(token_version) != int(db_version):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                elif int(db_version) > 1:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token has been revoked",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                return user

        raise credentials_exception
    except JWTError:
        raise credentials_exception


def get_current_active_employee(
    current_user: Union[User, object] = Depends(get_current_active_user),
) -> User:
    """Require an authenticated, active row from the employee ``users`` table.

    Parent IDs live in a separate table and may numerically overlap employee
    IDs. Employee attendance and leave endpoints must therefore reject parent
    principals instead of using the shared integer as an employee ID.
    """
    if not isinstance(current_user, User):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee account required",
        )
    return current_user



def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    """Get the current user's ID from JWT token.

    The returned integer is ambiguous on its own — it may be a ``users`` row or a
    ``parents`` row. Anything that queries a table keyed by a bare ``user_id``
    must use :func:`get_current_principal` instead.
    """
    user = get_current_active_user(request, credentials, db)
    return user.id


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> Principal:
    """Get the current caller's ID *and* the table that ID belongs to."""
    return principal_from_user(get_current_active_user(request, credentials, db))


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    """Require that the current user is an admin. Returns user ID.

    SECURITY: Always verifies admin status from the database, not from JWT payload.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        user_id = payload.get("user_id")
        role = payload.get("role")
        token_version = payload.get("token_version")

        if user_id is None:
            raise credentials_exception

        # SECURITY: the ID alone is meaningless — parent #1 and employee #1 are
        # different people. Only an employee token may be resolved against the
        # ``users`` table, or a parent would inherit the admin with their ID.
        numeric_employee_role = isinstance(role, int) or (
            isinstance(role, str) and role.isdigit()
        )
        if role not in (None, "teacher", "employee", "admin") and not numeric_employee_role:
            raise credentials_exception

        # SECURITY: Always verify admin status from database
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise credentials_exception

        # A disabled account must not keep admin rights on an old token.
        if int(getattr(user, "status", 0) or 0) != 1:
            raise credentials_exception

        db_version = getattr(user, "token_version", 1) or 1
        if token_version is not None:
            if int(token_version) != int(db_version):
                raise credentials_exception
        elif int(db_version) > 1:
            raise credentials_exception

        # Check if user has admin role (role == 1 is admin)
        if user.role != 1:
            raise credentials_exception

        return user_id
    except JWTError:
        raise credentials_exception
