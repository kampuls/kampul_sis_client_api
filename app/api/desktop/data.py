"""Always-online, staff-authenticated data transport for the WinForms app."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from ...core import get_db, settings
from ...core.database import SessionLocal, engine, resolve_tenant_db_name, get_tenant_session_factory
from ...models import User
from ...services.desktop_sql import (
    DesktopSqlRejected,
    bind_named_parameters,
    blank_desktop_media_value,
    decode_desktop_parameters,
    encode_desktop_value,
    extract_mutation_tables,
    is_mutation,
    is_sensitive_credential_column,
    requires_admin_privilege,
    rewrite_student_image_reads,
    statement_kind,
    translate_sqlite_compatibility,
    validate_desktop_sql,
    validate_safe_mutation,
)
from ...services.legacy_student_image import (
    publish_legacy_student_image,
    remember_legacy_student_image_resource,
    resource_text_from_bytes,
)
from ...services.storage_service import StorageService


logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()

_SAFE_FOLDER_RE = re.compile(r"[^A-Za-z0-9_-]+")

# Certificate media is shared with Flutter. Desktop uploads for these folders
# must land in the same StorageService path Flutter already uses.
_FLUTTER_SHARED_FOLDERS = {
    "certificates-backgrounds": "certificates/backgrounds",
    "certificates-stamps": "certificates/stamps",
    "certificates-signatures": "certificates/signatures",
}


def _detect_resource_content_type(content: bytes) -> str | None:
    """Identify the supported resource type from bytes, never client metadata."""

    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if content.startswith(b"%PDF"):
        return "application/pdf"
    return None


class DesktopCommandRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=250_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    dialect: str = Field(default="mysql", pattern="^(mysql|sqlite)$")


class DesktopColumn(BaseModel):
    name: str


class DesktopCommandResponse(BaseModel):
    columns: list[DesktopColumn] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    affected_rows: int = 0
    last_insert_id: int | None = None


def _decode_desktop_token(token: str, db: Session) -> User:
    if not getattr(settings, "desktop_api_enabled", True):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Desktop API is disabled")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid desktop token") from exc

    if payload.get("scope") != "desktop":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A desktop-scoped token is required")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop token has no user")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or int(getattr(user, "status", 0) or 0) != 1:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop user is not active")
    token_version = int(payload.get("token_version") or 1)
    current_version = int(getattr(user, "token_version", 1) or 1)
    if token_version != current_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop session has been revoked")
    return user


async def get_current_desktop_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    user = _decode_desktop_token(credentials.credentials, db)
    if not request.url.path.startswith('/api/desktop/integrations/update/') and not request.url.path.endswith('/required-version'):
        from ...services.kampul_releases import enforce_version
        await enforce_version(db, request.headers)
    return user


def _find_matching_paren(text: str, start_idx: int) -> int:
    depth = 0
    in_quote = None
    for i in range(start_idx, len(text)):
        ch = text[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"', '`'):
            in_quote = ch
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def rewrite_parent_token_version_inserts(sql: str) -> str:
    match = re.search(r"^\s*insert\s+into\s+`?parents`?\s*\(", sql, re.IGNORECASE)
    if not match:
        return sql

    col_start = match.end() - 1
    col_end = _find_matching_paren(sql, col_start)
    if col_end == -1:
        return sql

    columns_str = sql[col_start + 1:col_end]
    if re.search(r"\btoken_version\b", columns_str, re.IGNORECASE):
        return sql

    values_match = re.search(r"\bvalues\s*\(", sql[col_end:], re.IGNORECASE)
    if not values_match:
        return sql

    val_start = col_end + values_match.end() - 1
    val_end = _find_matching_paren(sql, val_start)
    if val_end == -1:
        return sql

    before_cols = sql[:col_start + 1]
    between = sql[col_end:val_start + 1]
    values_str = sql[val_start + 1:val_end]
    after_vals = sql[val_end:]

    new_cols = columns_str.rstrip() + ", token_version"
    new_vals = values_str.rstrip() + ", 1"

    return f"{before_cols}{new_cols}{between}{new_vals}{after_vals}"


def _prepare_request(
    body: DesktopCommandRequest,
) -> tuple[str, dict[str, Any], dict[str, str | None]]:
    if len(body.parameters) > 5_000:
        raise DesktopSqlRejected("Too many desktop SQL parameters")
    sql = translate_sqlite_compatibility(body.sql) if body.dialect == "sqlite" else body.sql
    sql = validate_desktop_sql(sql)
    sql = rewrite_student_image_reads(sql)
    sql = rewrite_parent_token_version_inserts(sql)
    parameters, student_resources = decode_desktop_parameters(sql, body.parameters)
    bound_sql, bound_parameters = bind_named_parameters(sql, parameters)
    return bound_sql, bound_parameters, student_resources


def _reads_legacy_student_image(sql: str, column_name: str) -> bool:
    if str(column_name).lower() not in {"image", "student_image", "studentimage"}:
        return False
    return bool(
        re.search(r"\b(?:from|join)\s+`?students`?(?:\s+(?:as\s+)?[A-Za-z_][A-Za-z0-9_]*)?\b", sql, re.I)
        and re.search(r"\b(?:students\s*\.\s*)?image\b|\b[A-Za-z_][A-Za-z0-9_]*\s*\.\s*image\b", sql, re.I)
    )


def _encode_result_value(value: Any, column_name: str, sql: str) -> Any:
    if is_sensitive_credential_column(column_name):
        return "[REDACTED]"
    if blank_desktop_media_value(column_name, value):
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)) and _reads_legacy_student_image(sql, column_name):
        existing_resource = resource_text_from_bytes(bytes(value))
        if existing_resource:
            return existing_resource
        try:
            return publish_legacy_student_image(bytes(value))
        except (ValueError, RuntimeError) as exc:
            logger.warning(
                "Ignoring an invalid legacy students.image value in a desktop read: %s",
                exc,
            )
            return None
    return encode_desktop_value(value)


def _parameter_value(parameters: dict[str, Any], name: str) -> Any:
    for key, value in parameters.items():
        if str(key).lower() == name.lower():
            return value
    return None


def _written_student_id(
    sql: str,
    parameters: dict[str, Any],
    last_insert_id: Any,
) -> int | None:
    if re.match(r"^\s*(?:insert\s+into|replace\s+into)\s+`?students`?\b", sql, re.I):
        candidate = last_insert_id or _parameter_value(parameters, "id")
    else:
        match = re.search(
            r"\bwhere\s+(?:`?students`?\s*\.\s*)?`?id`?\s*=\s*:([A-Za-z_][A-Za-z0-9_]*)",
            sql,
            re.I,
        )
        candidate = _parameter_value(parameters, match.group(1)) if match else None
    try:
        parsed = int(candidate)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _upsert_student_avatar(connection: Connection, student_id: int, resource_url: str) -> None:
    connection.execute(text("""
        INSERT INTO users_resource (
            user_id, user_type, avatar, cover_focus_y,
            status, created_at, updated_at
        ) VALUES (
            :student_id, 'student', :resource_url, 0,
            1, NOW(), NOW()
        )
        ON DUPLICATE KEY UPDATE
            avatar = VALUES(avatar),
            status = 1,
            updated_at = NOW()
    """), {"student_id": student_id, "resource_url": resource_url})


def _clear_student_avatar(connection: Connection, student_id: int) -> None:
    connection.execute(text("""
        UPDATE users_resource
        SET avatar = NULL, updated_at = NOW()
        WHERE user_id = :student_id AND user_type = 'student'
    """), {"student_id": student_id})


_STUDENTS_IMAGE_IS_BINARY: bool | None = None
_STUDENTS_IMAGE_LOCK = threading.Lock()


def _is_students_image_binary_column(connection: Connection) -> bool:
    global _STUDENTS_IMAGE_IS_BINARY
    if _STUDENTS_IMAGE_IS_BINARY is not None:
        return _STUDENTS_IMAGE_IS_BINARY
    with _STUDENTS_IMAGE_LOCK:
        if _STUDENTS_IMAGE_IS_BINARY is not None:
            return _STUDENTS_IMAGE_IS_BINARY
        try:
            row = connection.execute(text("""
                SELECT DATA_TYPE FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'students'
                  AND COLUMN_NAME = 'image'
            """)).fetchone()
            if row and row[0]:
                data_type = str(row[0]).lower()
                _STUDENTS_IMAGE_IS_BINARY = "blob" in data_type or "binary" in data_type
            else:
                _STUDENTS_IMAGE_IS_BINARY = False
        except Exception:
            _STUDENTS_IMAGE_IS_BINARY = False
        return _STUDENTS_IMAGE_IS_BINARY


def _execute_on_connection(connection: Connection, body: DesktopCommandRequest, finance_user=None) -> DesktopCommandResponse:
    sql, parameters, student_resources = _prepare_request(body)
    stock_before = None
    if finance_user is not None:
        from ...services.desktop_finance_guard import guard_finance_mutation, FinanceMutationRejected
        try:
            guard_finance_mutation(connection, sql, parameters, finance_user)
            from ...services.desktop_finance_guard import inventory_snapshot
            stock_before = inventory_snapshot(connection, sql, parameters)
        except FinanceMutationRejected as exc:
            raise DesktopSqlRejected(str(exc)) from exc
    if "image" in student_resources and not _is_students_image_binary_column(connection):
        # The database column students.image is VARCHAR/TEXT (e.g. converted by migration 53).
        # Binding raw binary bytes to a VARCHAR column triggers MySQL DataError 1366.
        # Use the managed resource URL/path string instead.
        image_param_key = next((k for k in parameters if str(k).lower() == "image"), None)
        if image_param_key:
            parameters[image_param_key] = student_resources["image"]
    try:
        result = connection.execute(text(sql), parameters)
    except DBAPIError as exc:
        if "token_version" in str(exc).lower() and ("1364" in str(exc) or "default value" in str(exc).lower()):
            logger.info("Attempting auto-repair of parents.token_version column default...")
            try:
                connection.execute(text("ALTER TABLE parents MODIFY COLUMN token_version INT NULL DEFAULT 1"))
                result = connection.execute(text(sql), parameters)
            except Exception:
                raise exc
        else:
            raise exc

    columns: list[DesktopColumn] = []
    rows: list[list[Any]] = []


    if result.returns_rows:
        keys = [str(key) for key in result.keys()]
        columns = [DesktopColumn(name=key) for key in keys]
        max_rows = int(getattr(settings, "desktop_api_max_rows", 100_000))
        for index, row in enumerate(result):
            if index >= max_rows:
                raise DesktopSqlRejected(
                    f"Desktop query exceeded {max_rows} rows; add a filter or pagination"
                )
            rows.append([
                _encode_result_value(value, keys[column_index], sql)
                for column_index, value in enumerate(row)
            ])

    last_insert_id = getattr(result, "lastrowid", None)
    affected_rows = max(int(result.rowcount or 0), 0)
    if finance_user is not None and affected_rows:
        from ...services.desktop_finance_guard import record_inventory_change
        record_inventory_change(connection, sql, parameters, stock_before, last_insert_id, finance_user)
    if "image" in student_resources:
        student_resource_url = student_resources["image"]
        student_id = _written_student_id(sql, parameters, last_insert_id)
        if student_id is None:
            raise DesktopSqlRejected(
                "A students.image compatibility write must identify the student by id"
            )
        legacy_bytes = _parameter_value(parameters, "image")
        if isinstance(legacy_bytes, (bytes, bytearray, memoryview)):
            student_resource_url = remember_legacy_student_image_resource(
                bytes(legacy_bytes),
                student_resource_url,
            )
        if student_resource_url:
            _upsert_student_avatar(connection, student_id, student_resource_url)
        else:
            _clear_student_avatar(connection, student_id)
    return DesktopCommandResponse(
        columns=columns,
        rows=rows,
        affected_rows=affected_rows,
        last_insert_id=int(last_insert_id) if last_insert_id is not None else None,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DesktopSqlRejected):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, DBAPIError):
        logger.warning("Desktop database command failed: %s", exc.orig)
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc.orig))
    logger.exception("Desktop API command failed")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Desktop command failed")


@router.post("/command", response_model=DesktopCommandResponse)
def execute_desktop_command(
    request: Request,
    body: DesktopCommandRequest,
    current_user: User = Depends(get_current_desktop_user),
    db: Session = Depends(get_db),
):
    """Execute one authenticated desktop operation immediately against MySQL."""

    validate_safe_mutation(body.sql)
    if requires_admin_privilege(body.sql) and int(getattr(current_user, "role", 0) or 0) != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privilege is required to modify user accounts or system security settings.",
        )
    try:
        # A transaction is used for every command so CTE mutations and future
        # compatibility statements cannot be accidentally rolled back.
        bind_engine = db.get_bind()
        with bind_engine.begin() as connection:
            response = _execute_on_connection(connection, body, current_user)
            if is_mutation(body.sql):
                client_ip = getattr(request.client, "host", "unknown") if request.client else "unknown"
                tables = extract_mutation_tables(body.sql)
                logger.info(
                    "AUDIT: desktop_mutation user_id=%s username=%s ip=%s kind=%s tables=%s affected=%s",
                    current_user.id,
                    current_user.username,
                    client_ip,
                    statement_kind(body.sql),
                    ",".join(tables) or "unknown",
                    response.affected_rows,
                )
            return response
    except (DesktopSqlRejected, SQLAlchemyError) as exc:
        raise _http_error(exc) from exc


@router.post("/resources")
async def upload_desktop_resource(
    file: UploadFile = File(...),
    folder: str = Form(default="general"),
    current_user: User = Depends(get_current_desktop_user),
):
    """Store desktop media as a URL resource; database BLOBs are forbidden."""

    del current_user
    max_bytes = int(getattr(settings, "desktop_resource_max_mb", 20)) * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Desktop resource is too large")
    if not content:
        raise HTTPException(status_code=400, detail="Desktop resource is empty")
    content_type = _detect_resource_content_type(content)
    if content_type is None:
        raise HTTPException(
            status_code=400,
            detail="Desktop resources must be valid PNG, JPEG, GIF, WebP, BMP, TIFF, or PDF files",
        )

    clean_folder = _SAFE_FOLDER_RE.sub("-", folder).strip("-")[:60] or "general"
    storage_folder = _FLUTTER_SHARED_FOLDERS.get(
        clean_folder, f"desktop/{clean_folder}"
    )
    url = await asyncio.to_thread(
        StorageService.upload_file,
        content,
        storage_folder,
        None,
        content_type,
    )
    if not url:
        raise HTTPException(status_code=500, detail="Desktop resource upload failed")
    return {"url": url}


def _is_managed_resource_url(url: str) -> bool:
    value = (url or "").strip()
    return value.startswith(("http://", "https://", "/uploads/", "uploads/"))


@router.delete("/resources")
async def delete_desktop_resource(
    url: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_desktop_user),
):
    """Delete a StorageService file. Same path Flutter uses for certificate media."""

    del current_user
    resource_url = url.strip()
    if not _is_managed_resource_url(resource_url):
        raise HTTPException(
            status_code=400,
            detail="The resource URL is not a managed storage path",
        )
    deleted = await asyncio.to_thread(StorageService.delete_file, resource_url)
    return {"ok": True, "deleted": bool(deleted)}


@router.websocket("/transaction")
async def desktop_transaction_socket(websocket: WebSocket):
    """Keep one DB transaction on one API worker for the socket lifetime."""

    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    db_name = resolve_tenant_db_name(websocket)
    factory = get_tenant_session_factory(db_name)
    db = factory()
    connection: Connection | None = None
    transaction = None
    try:
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A desktop bearer token is required",
            )
        user = _decode_desktop_token(token, db)
        from ...services.kampul_releases import enforce_version
        await enforce_version(db, websocket.headers)
        await websocket.accept()
        tenant_engine = factory.kw.get("bind") or engine
        connection = tenant_engine.connect()
        transaction = connection.begin()
        await websocket.send_json({"type": "ready"})

        while True:
            message = await websocket.receive_json()
            action = str(message.get("action") or "command").lower()
            if action == "commit":
                transaction.commit()
                transaction = None
                await websocket.send_json({"type": "committed"})
                break
            if action == "rollback":
                transaction.rollback()
                transaction = None
                await websocket.send_json({"type": "rolled_back"})
                break
            if action != "command":
                raise DesktopSqlRejected("Unknown desktop transaction action")

            body = DesktopCommandRequest.model_validate(message.get("command") or {})
            validate_safe_mutation(body.sql)
            if requires_admin_privilege(body.sql) and int(getattr(user, "role", 0) or 0) != 1:
                raise DesktopSqlRejected(
                    "Administrative privilege is required to modify user accounts or system security settings."
                )
            response = _execute_on_connection(connection, body, user)
            if is_mutation(body.sql):
                client_ip = getattr(websocket.client, "host", "unknown") if websocket.client else "unknown"
                tables = extract_mutation_tables(body.sql)
                logger.info(
                    "AUDIT: desktop_transaction_mutation user_id=%s username=%s ip=%s kind=%s tables=%s affected=%s",
                    user.id,
                    user.username,
                    client_ip,
                    statement_kind(body.sql),
                    ",".join(tables) or "unknown",
                    response.affected_rows,
                )
            await websocket.send_json({"type": "result", "result": response.model_dump(mode="json")})
    except WebSocketDisconnect:
        logger.info("Desktop transaction socket disconnected")
    except HTTPException as exc:
        logger.warning("Desktop transaction authentication failed: %s", exc.detail)
        try:
            await websocket.close(code=1008, reason=str(exc.detail)[:120])
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Desktop transaction socket failed: %s", exc)
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass
    finally:
        if transaction is not None:
            try:
                transaction.rollback()
            except Exception:
                pass
        if connection is not None:
            connection.close()
        db.close()
        try:
            await websocket.close()
        except Exception:
            pass
