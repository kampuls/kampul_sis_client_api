"""Server-side enforcement of Super Admin feature locks.

`require_feature_unlocked(feature_id)` returns a FastAPI dependency meant to be
attached at `include_router(...)` time in `app/api/v1/__init__.py`. It blocks
WRITE requests (POST/PUT/PATCH/DELETE) to a feature's endpoints while that
feature is locked in `feature_locks` — unless the caller is an active
(unlocked) Super Admin. Reads always pass so parents/teachers can still view
content; locking a feature stops modification, not visibility.

Auth here is best-effort on purpose: the bearer token is optional so public
read endpoints on the same router keep working. Endpoints still do their own
authentication — this guard only ever *adds* a 403, never grants access.
"""

from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from ..models.app_admin import AppAdmin
from ..models.feature_lock import FeatureLock

_bearer = HTTPBearer(auto_error=False)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def require_feature_unlocked(feature_id: str, exempt_suffixes: Tuple[str, ...] = ()):
    """Dependency factory: 403 on writes while `feature_id` is locked.

    `exempt_suffixes` lists path endings that must stay open even when the
    feature is locked — e.g. ad click/view tracking or form submissions that
    regular app users (not admins) perform.
    """

    async def _guard(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
        db: Session = Depends(get_db),
    ):
        if request.method not in WRITE_METHODS:
            return

        path = request.url.path.rstrip("/")
        if any(path.endswith(suffix) for suffix in exempt_suffixes):
            return

        lock = (
            db.query(FeatureLock)
            .filter(
                FeatureLock.feature_id == feature_id,
                FeatureLock.is_locked.in_([True, 1]),
            )
            .first()
        )
        if not lock:
            return

        # Feature is locked: only an active (unlocked) Super Admin may write.
        user_id = None
        if credentials:
            try:
                payload = jwt.decode(
                    credentials.credentials,
                    settings.secret_key,
                    algorithms=[settings.algorithm],
                )
                # Parent ids live in a different table; a parent is never an
                # AppAdmin, so don't let a parent id collide with a user id.
                if payload.get("role") != "parent":
                    user_id = payload.get("user_id")
            except JWTError:
                pass

        if user_id is not None:
            admin = (
                db.query(AppAdmin)
                .filter(
                    AppAdmin.user_id == user_id,
                    AppAdmin.is_super_admin.in_([True, 1]),
                    AppAdmin.is_locked.in_([False, 0]),
                )
                .first()
            )
            if admin:
                return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This feature is locked by the Super Admin",
        )

    return _guard
