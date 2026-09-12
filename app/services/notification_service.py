"""
Notification service for sending push notifications via Firebase Cloud Messaging (FCM).
Uses FCM HTTP v1 API (not legacy API).
"""
import os
import json
import logging
import asyncio
import uuid
import hashlib
from typing import List, Optional, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..models import DeviceToken, Notification
from .notification_dedupe import dedupe_device_tokens, logical_notification_key
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

# FCM Configuration - using HTTP v1 API
from ..core.config import settings

FCM_PROJECT_ID = settings.firebase_project_id or os.getenv("FCM_PROJECT_ID", "multischool-pro")
FCM_SERVICE_ACCOUNT_PATH = settings.fcm_service_account_path or os.getenv("FCM_SERVICE_ACCOUNT_PATH", "")
FCM_SERVICE_ACCOUNT_JSON = (
    settings.fcm_service_account_json
    or os.getenv("FCM_SERVICE_ACCOUNT_JSON", "")
)
FCM_URL = f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"

# Log FCM configuration on module load (for debugging)
if FCM_SERVICE_ACCOUNT_JSON:
    logger.info(f"FCM configured: PROJECT_ID={FCM_PROJECT_ID}, CREDENTIAL_SOURCE=environment")
elif FCM_SERVICE_ACCOUNT_PATH:
    logger.info(f"FCM configured: PROJECT_ID={FCM_PROJECT_ID}, SERVICE_ACCOUNT_PATH={FCM_SERVICE_ACCOUNT_PATH}")
else:
    logger.warning("FCM service account not configured - push notifications will not work")

# ── FCM Token Cache ────────────────────────────────────────────────────────────
# Stored in /tmp so ALL Gunicorn workers on the same server share it.
# Uses fcntl file locking to prevent race conditions between workers.
# Avoids 4× duplicate Google OAuth calls (one per worker → 4/hour).
_FCM_TOKEN_CACHE_FILE = "/tmp/pama_fcm_token.json"

_CRITICAL_NOTIFICATION_TYPES = {
    "force_logout",
    "home_permission_updated",
    "parent_registration_approved",
    "parent_registration_rejected",
    "staff_registration_approved",
    "new_user_registration",
}


def notification_preference_category(data: Optional[Dict[str, Any]]) -> Optional[str]:
    """Map a push payload to the user-facing preference category."""
    notification_type = str((data or {}).get("type") or "").strip().lower()
    if notification_type in _CRITICAL_NOTIFICATION_TYPES:
        return None
    if notification_type.startswith("attendance") or notification_type in {
        "schedule_reminder",
    }:
        return "attendance"
    if notification_type.startswith("leave") or notification_type.startswith(
        "permission_"
    ):
        return "leave"
    if (
        "message" in notification_type
        or "chat" in notification_type
        or notification_type.startswith("group_")
        or notification_type == "inbox_updated"
    ):
        return "messages"
    if notification_type.startswith("market") or notification_type in {
        "new_order",
        "new_review",
    }:
        return "marketplace"
    if notification_type in {
        "hot_event",
        "new_ad",
        "new_news",
        "student_certificate",
        "new_form",
    }:
        return "announcements"
    return "other"


def _database_preference_enabled(value: Any) -> bool:
    """Treat legacy NULL as enabled; only a persisted false/zero opts out."""
    return True if value is None else bool(value)


def token_allows_notification(
    token_data: Any,
    data: Optional[Dict[str, Any]],
) -> bool:
    """Apply optional per-device preferences; unknown/legacy tokens stay enabled."""
    if not isinstance(token_data, dict):
        return True
    category = notification_preference_category(data)
    if category is None:  # Account and security events are mandatory.
        return True
    if not _database_preference_enabled(
        token_data.get("notifications_enabled", True)
    ):
        return False
    preference_key = {
        "attendance": "attendance_notifications_enabled",
        "leave": "leave_notifications_enabled",
        "messages": "message_notifications_enabled",
        "announcements": "announcement_notifications_enabled",
        "marketplace": "market_notifications_enabled",
        "other": "other_notifications_enabled",
    }.get(category)
    return preference_key is None or _database_preference_enabled(
        token_data.get(preference_key, True)
    )


def filter_tokens_by_notification_preferences(
    db: Optional[Session],
    device_tokens: List[Any],
    data: Optional[Dict[str, Any]],
) -> List[Any]:
    """Attach current DB preferences and remove opted-out installations."""
    if notification_preference_category(data) is None:
        return device_tokens

    preferences_by_token: Dict[str, DeviceToken] = {}
    if db is not None:
        token_values = {
            str(item.get("token") or "").strip()
            for item in device_tokens
            if isinstance(item, dict) and item.get("token")
        }
        token_values.update(
            str(item).strip() for item in device_tokens if not isinstance(item, dict)
        )
        token_values.discard("")
        if token_values:
            try:
                rows = (
                    db.query(DeviceToken)
                    .filter(DeviceToken.device_token.in_(token_values))
                    .all()
                )
                preferences_by_token = {row.device_token: row for row in rows}
            except Exception:
                # Preferences are optional. A partially migrated schema must not
                # take down attendance reminders and every other FCM category.
                logger.exception(
                    "Could not load device notification preferences; "
                    "failing open for this delivery"
                )
                return device_tokens

    allowed: List[Any] = []
    for item in device_tokens:
        token = (
            str(item.get("token") or "").strip()
            if isinstance(item, dict)
            else str(item).strip()
        )
        row = preferences_by_token.get(token)
        enriched = item
        if row is not None:
            enriched = {
                **(item if isinstance(item, dict) else {"token": token}),
                "notifications_enabled": _database_preference_enabled(
                    row.notifications_enabled
                ),
                "attendance_notifications_enabled": _database_preference_enabled(
                    row.attendance_notifications_enabled
                ),
                "leave_notifications_enabled": _database_preference_enabled(
                    row.leave_notifications_enabled
                ),
                "message_notifications_enabled": _database_preference_enabled(
                    row.message_notifications_enabled
                ),
                "announcement_notifications_enabled": _database_preference_enabled(
                    row.announcement_notifications_enabled
                ),
                "market_notifications_enabled": _database_preference_enabled(
                    row.market_notifications_enabled
                ),
                "other_notifications_enabled": _database_preference_enabled(
                    row.other_notifications_enabled
                ),
            }
        if token_allows_notification(enriched, data):
            allowed.append(enriched)
    return allowed

# Public base for push images (/uploads/...). Set PUBLIC_API_BASE_URL in .env when the domain changes.
_PUBLIC_API_BASE_URL = (
    os.getenv("PUBLIC_API_BASE_URL", "").strip().rstrip("/")
    or "https://pamais.duckdns.org"
)


def get_public_api_base_url() -> str:
    """Single source for resolving push notification image URLs (certificates, news, ads, …)."""
    return _PUBLIC_API_BASE_URL


def send_app_rich_push_notification(
    device_tokens: List[Any],
    title: str,
    body: str,
    data: Dict[str, Any],
    *,
    db: Optional[Session] = None,
    channel_id: str = "message_channel",
    sound: Optional[str] = None,
) -> bool:
    """
    Announcement-style push (ads, news, hot events, certificates).

    Data-only FCM — the Flutter app shows one local notification with optional
    cover/image from data['image_url'] (resolved via ApiConfig.pushNotificationImageBaseUrl).
    Avoids duplicate FCM tray + local notifications.
    """
    return send_notification(
        device_tokens=device_tokens,
        title=title,
        body=body,
        data=data,
        sound=sound,
        channel_id=channel_id,
        android_show_system_notification=False,
        data_only=True,
        db=db,
        image_url=None,
    )


def is_publicly_reachable_url(url: Optional[str]) -> bool:
    """
    FCM/Android notification images must be fetchable from the public internet.
    LAN / localhost URLs break or suppress tray notifications.
    """
    if not url:
        return False
    from urllib.parse import urlparse

    parsed = urlparse(str(url).strip())
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in ("localhost", "127.0.0.1"):
        return False
    if host.startswith("192.168.") or host.startswith("10."):
        return False
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2:
            try:
                if 16 <= int(parts[1]) <= 31:
                    return False
            except ValueError:
                pass
    return True


def resolve_push_image_url(
    image_url: Optional[str],
    *,
    public_base_url: Optional[str] = None,
) -> Optional[str]:
    """
    Return an absolute URL suitable for FCM / in-app notification images.

    Uses [get_public_api_base_url] unless [public_base_url] is passed explicitly.
    """
    if not image_url:
        return None
    u = str(image_url).strip()
    if not u:
        return None
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = (public_base_url or get_public_api_base_url()).strip().rstrip("/")
    if not base:
        return None
    if u.startswith("/"):
        return f"{base}{u}"
    return f"{base}/{u}"


def get_parent_device_tokens(
    db: Session,
    student_id: int
) -> List[Dict[str, Any]]:
    """
    Get FCM device tokens for parents of a student.

    Args:
        db: Database session
        student_id: Student ID

    Returns:
        List of dicts with 'token', 'device_type', and 'id'
    """
    try:
        # Use parents table's myChilds field to find parents
        # Parents have myChilds field which contains comma-separated student IDs
        query = text("""
            SELECT dt.id, dt.device_token, dt.device_type,
                   dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
            FROM device_tokens dt
            INNER JOIN parents p ON p.id = dt.user_id
            INNER JOIN (
                SELECT user_id, MAX(COALESCE(last_used_at, created_at)) AS max_used
                FROM device_tokens
                WHERE user_type = 'parent'
                  AND is_active = 1
                GROUP BY user_id
            ) latest ON latest.user_id = dt.user_id
                AND COALESCE(dt.last_used_at, dt.created_at) = latest.max_used
            WHERE FIND_IN_SET(:student_id, p.myChilds) > 0
              AND dt.user_type = 'parent'
              AND dt.is_active = 1
            ORDER BY dt.id DESC
        """)

        result = db.execute(query, {"student_id": str(student_id)})
        seen_tokens: set[str] = set()
        tokens: List[Dict[str, Any]] = []
        for row in result.fetchall():
            token = row[1]
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)
            tokens.append({
                "id": row[0],
                "token": token,
                "device_type": row[2] or "unknown",
                "user_id": row[3],
                "user_type": row[4] or "parent",
                "device_name": row[5],
                "last_used_at": row[6],
            })

        tokens = dedupe_device_tokens(tokens)

        logger.info(
            f"Query for student {student_id}: Found {len(tokens)} parent device token(s)"
        )
        return tokens
    except Exception as e:
        logger.error(f"Error getting parent device tokens for student {student_id}: {e}", exc_info=True)
        return []


def get_parent_user_device_tokens(
    db: Session,
    parent_id: int,
) -> List[Dict[str, Any]]:
    """Active FCM tokens for a parent account (self-registration / approval pushes)."""
    try:
        query = text("""
            SELECT DISTINCT dt.id, dt.device_token, dt.device_type,
                   dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
            FROM device_tokens dt
            WHERE dt.user_id = :parent_id
              AND dt.user_type = 'parent'
              AND (dt.is_active = 1 OR dt.is_active = TRUE)
        """)
        result = db.execute(query, {"parent_id": parent_id})
        tokens = dedupe_device_tokens([
            {
                "id": row[0],
                "token": row[1],
                "device_type": row[2] or "unknown",
                "user_id": row[3],
                "user_type": row[4] or "parent",
                "device_name": row[5],
                "last_used_at": row[6],
            }
            for row in result.fetchall()
            if row[1]
        ])
        logger.info(
            "Parent %s device tokens: %s",
            parent_id,
            len(tokens),
        )
        return tokens
    except Exception as e:
        logger.error(
            "Error getting parent device tokens for parent %s: %s",
            parent_id,
            e,
            exc_info=True,
        )
        return []


def get_teacher_device_tokens(
    db: Session,
    teacher_id: int
) -> List[Dict[str, Any]]:
    """
    Get FCM device tokens for a teacher.

    Args:
        db: Database session
        teacher_id: Teacher ID

    Returns:
        List of dicts with 'token', 'device_type', and 'id'
    """
    try:
        query = text("""
            SELECT DISTINCT dt.id, dt.device_token, dt.device_type,
                   dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
            FROM device_tokens dt
            WHERE dt.user_id = :teacher_id
            AND dt.user_type = 'teacher'
            AND dt.is_active = 1
        """)

        result = db.execute(query, {"teacher_id": teacher_id})
        tokens = dedupe_device_tokens([{
            "id": row[0],
            "token": row[1],
            "device_type": row[2] or "unknown",
            "user_id": row[3],
            "user_type": row[4] or "teacher",
            "device_name": row[5],
            "last_used_at": row[6],
        } for row in result.fetchall()])
        
        logger.info(f"Query for teacher {teacher_id}: Found {len(tokens)} device token(s)")
        return tokens
    except Exception as e:
        logger.error(f"Error getting teacher device tokens for teacher {teacher_id}: {e}", exc_info=True)
        return []



def get_message_group_member_tokens(
    db: Session,
    group_id: int,
    exclude_user_id: int,
) -> List[Dict[str, Any]]:
    """
    Get FCM device tokens for all members of a message group except one user.
    Returns de-duplicated token rows with recipient and device metadata.
    """
    try:
        # Get all device tokens for users who are in this group (except sender).
        # Join on user_id only; is_active can be 1 or TRUE depending on DB.
        query = text("""
            SELECT DISTINCT dt.id, dt.device_token, dt.device_type,
                   dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
            FROM device_tokens dt
            INNER JOIN message_group_members mgm ON dt.user_id = mgm.user_id
            WHERE mgm.group_id = :group_id
              AND mgm.user_id != :exclude_user_id
              AND (dt.is_active = 1 OR dt.is_active = TRUE)
        """)
        result = db.execute(query, {"group_id": group_id, "exclude_user_id": exclude_user_id})
        rows = result.fetchall()
        tokens = dedupe_device_tokens([
            {
                "id": r[0],
                "token": r[1],
                "device_type": r[2] or "unknown",
                "user_id": r[3],
                "user_type": r[4] or "teacher",
                "device_name": r[5],
                "last_used_at": r[6],
            }
            for r in rows
            if r[1]
        ])
        logger.info(f"Group {group_id} member tokens (excl. {exclude_user_id}): {len(tokens)}")
        return tokens
    except Exception as e:
        logger.error(f"Error getting message group member tokens: {e}", exc_info=True)
        return []


def get_app_admin_user_ids(
    db: Session,
    *,
    super_admin_only: bool = False,
) -> List[Dict[str, Any]]:
    """Active app admins (unlocked) who can receive admin push notifications."""
    try:
        super_filter = ""
        if super_admin_only:
            super_filter = " AND (aa.is_super_admin = 1 OR aa.is_super_admin = TRUE) "
        rows = db.execute(
            text(
                f"""
                SELECT aa.user_id
                FROM app_admins aa
                INNER JOIN users u ON u.id = aa.user_id
                WHERE (aa.is_locked = 0 OR aa.is_locked = FALSE)
                  AND u.status = 1
                {super_filter}
                """
            )
        ).fetchall()
        return [{"id": int(r[0]), "user_type": "teacher"} for r in rows if r[0]]
    except Exception as e:
        logger.error(f"Error loading app admin user ids: {e}", exc_info=True)
        return []


def get_role_permission_user_ids(
    db: Session,
    permission_name: str,
) -> List[Dict[str, Any]]:
    """Active desktop users whose assigned role owns one permission."""
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT u.id
                FROM users u
                INNER JOIN role_permissions rp ON rp.role_id = u.role
                INNER JOIN permissions p ON p.id = rp.permission_id
                WHERE u.status = 1
                  AND p.permission_name = :permission_name
                """
            ),
            {"permission_name": permission_name},
        ).fetchall()
        return [
            {"id": int(row[0]), "user_type": "teacher"}
            for row in rows
            if row[0]
        ]
    except Exception as e:
        logger.error(
            "Error loading user ids for permission %s: %s",
            permission_name,
            e,
            exc_info=True,
        )
        return []


def get_app_admin_device_tokens(
    db: Session,
    *,
    super_admin_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    FCM tokens for unlocked app admins (same people who can approve parent registrations).
    """
    try:
        super_filter = ""
        if super_admin_only:
            super_filter = " AND (aa.is_super_admin = 1 OR aa.is_super_admin = TRUE) "
        query = text(
            f"""
            SELECT DISTINCT dt.id, dt.device_token, dt.device_type,
                   dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
            FROM device_tokens dt
            INNER JOIN app_admins aa ON aa.user_id = dt.user_id
            INNER JOIN users u ON u.id = aa.user_id
            WHERE (aa.is_locked = 0 OR aa.is_locked = FALSE)
              AND u.status = 1
              AND dt.user_type = 'teacher'
              AND (dt.is_active = 1 OR dt.is_active = TRUE)
            {super_filter}
            """
        )
        result = db.execute(query).fetchall()
        tokens = dedupe_device_tokens([
            {
                "id": r[0],
                "token": r[1],
                "device_type": r[2] or "unknown",
                "user_id": r[3],
                "user_type": r[4] or "teacher",
                "device_name": r[5],
                "last_used_at": r[6],
            }
            for r in result
            if r[1]
        ])
        logger.info(
            "App admin device tokens: %s (super_admin_only=%s)",
            len(tokens),
            super_admin_only,
        )
        return tokens
    except Exception as e:
        logger.error(f"Error getting app admin device tokens: {e}", exc_info=True)
        return []


def resolve_device_tokens_for_users(
    db: Session,
    user_ids: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Load active FCM tokens for [{id, user_type}, ...] (typically teachers)."""
    if not user_ids:
        return []
    tokens: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for info in user_ids:
        uid = info.get("id")
        if uid is None:
            continue
        utype = (info.get("user_type") or "teacher").lower()
        if utype == "parent":
            rows = get_parent_user_device_tokens(db, int(uid))
        elif utype == "student":
            continue
        else:
            rows = get_teacher_device_tokens(db, int(uid))
        for row in rows:
            tok = row.get("token")
            if tok and tok not in seen:
                seen.add(tok)
                tokens.append(row)
    return tokens


def get_device_tokens_by_audience(
    db: Session,
    audience: str
) -> List[Dict[str, Any]]:
    """
    Get FCM device tokens for a specific audience.
    Audience can be comma-separated: 'teacher,parent', 'all', etc.
    """
    try:
        audience_list = [a.strip().lower() for a in (audience or "").split(",")]
        
        def token_rows(result_rows) -> List[Dict[str, Any]]:
            return dedupe_device_tokens([
                {
                    "id": r[0],
                    "token": r[1],
                    "device_type": r[2] or "unknown",
                    "user_id": r[3],
                    "user_type": r[4] or "teacher",
                    "device_name": r[5],
                    "last_used_at": r[6],
                }
                for r in result_rows
                if r[1]
            ])

        # If 'all' is present, get everything
        if "all" in audience_list:
            query = text("""
                SELECT id, device_token, device_type, user_id, user_type,
                       device_name, last_used_at
                FROM device_tokens
                WHERE is_active = 1
            """)
            result = db.execute(query).fetchall()
            tokens = token_rows(result)
            logger.info(f"Audience 'all': Found {len(tokens)} tokens")
            return tokens

        # Specific roles
        conditions = []
        if "teacher" in audience_list:
            conditions.append("dt.user_type = 'teacher'")
        if "parent" in audience_list:
            conditions.append("dt.user_type = 'parent'")
        if "employee" in audience_list:
            conditions.append("dt.user_type = 'employee'")
        if "student" in audience_list:
            conditions.append("dt.user_type = 'student'")
        if "admin" in audience_list:
            conditions.append("""
                u.role = 1 OR u.role IN (
                    SELECT rp.role_id 
                    FROM role_permissions rp 
                    JOIN permissions p ON rp.permission_id = p.id 
                    WHERE p.permission_name IN ('AdminViewApp', 'AdminUpdateApp', 'AdminDeleteApp')
                )
            """)
        
        if not conditions:
            # Fallback/Empty
            return []

        where_clause = " OR ".join(conditions)
        
        if "admin" in audience_list:
            sql = f"""
                SELECT dt.id, dt.device_token, dt.device_type,
                       dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
                FROM device_tokens dt
                LEFT JOIN users u ON dt.user_id = u.id
                WHERE dt.is_active = 1 AND ({where_clause})
            """
        else:
            sql = f"""
                SELECT dt.id, dt.device_token, dt.device_type,
                       dt.user_id, dt.user_type, dt.device_name, dt.last_used_at
                FROM device_tokens dt
                WHERE dt.is_active = 1 AND ({where_clause})
            """
            
        query = text(sql)
        
        result = db.execute(query).fetchall()
        tokens = token_rows(result)
        
        logger.info(f"Audience '{audience}': Found {len(tokens)} tokens")
        return tokens

    except Exception as e:
        logger.error(f"Error getting tokens for audience {audience}: {e}", exc_info=True)
        return []


def get_access_token() -> Optional[str]:
    """
    Get OAuth 2.0 access token for FCM HTTP v1 API.
    Token is cached in /tmp/pama_fcm_token.json (shared across all Gunicorn workers).
    Uses fcntl file locking to prevent duplicate token fetches under concurrency.
    """
    import fcntl
    import json as _json
    import time as _time

    now = _time.time()
    lock_path = _FCM_TOKEN_CACHE_FILE + ".lock"

    try:
        # Open (or create) a lock file — shared across all processes on this machine
        with open(lock_path, "w") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)  # Exclusive lock — only one worker at a time

            # Check if another worker already refreshed the token while we waited
            try:
                with open(_FCM_TOKEN_CACHE_FILE, "r") as f:
                    cached = _json.load(f)
                if cached.get("token") and now < cached.get("expiry", 0):
                    return cached["token"]
            except (FileNotFoundError, _json.JSONDecodeError, KeyError):
                pass  # Cache miss — fetch a new token below

            # Fetch fresh token from Google
            scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
            if FCM_SERVICE_ACCOUNT_JSON:
                service_account_info = _json.loads(FCM_SERVICE_ACCOUNT_JSON)
                if "private_key" in service_account_info:
                    service_account_info["private_key"] = service_account_info[
                        "private_key"
                    ].replace("\\n", "\n")
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=scopes,
                )
            elif FCM_SERVICE_ACCOUNT_PATH:
                service_account_path = Path(FCM_SERVICE_ACCOUNT_PATH)
                if not service_account_path.exists():
                    logger.error(
                        f"Service account file not found: {FCM_SERVICE_ACCOUNT_PATH}"
                    )
                    return None
                credentials = service_account.Credentials.from_service_account_file(
                    str(service_account_path),
                    scopes=scopes,
                )
            else:
                logger.error("FCM service account not configured")
                return None

            credentials.refresh(Request())

            token = credentials.token
            expiry = now + (50 * 60)  # Cache for 50 minutes

            # Write to shared cache file
            with open(_FCM_TOKEN_CACHE_FILE, "w") as f:
                _json.dump({"token": token, "expiry": expiry}, f)

            logger.info("FCM access token refreshed and written to shared cache")
            return token

    except Exception as e:
        logger.error(f"Error getting FCM access token: {e}")
        return None


def mark_as_unread(db: Session, notification_id: int, user_id: int, user_type: str):
    """
    Mark a notification as unread.

    ``user_type`` is required: notification rows are keyed by (user_id, user_type)
    and the ID alone is shared between an employee, a parent and a student.
    """
    try:
        if user_type not in ['teacher', 'parent', 'student']:
            user_type = 'teacher'
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.user_type == user_type
        ).first()

        if notification:
            notification.is_read = False
            db.commit()
            db.refresh(notification)
        return notification
    except Exception as e:
        logger.error(f"Error marking notification as unread: {e}")
        return None


def save_notification(
    db: Session,
    user_id: int,
    user_type: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    is_deletable: bool = True,
    redirect_route: Optional[str] = None,
    redirect_args: Optional[Dict[str, Any]] = None
) -> Optional[Notification]:
    """
    Save notification to database.
    """
    try:
        # Normalize user_type
        if user_type not in ['teacher', 'parent', 'student']:
            user_type = 'teacher'

        # Do not duplicate the in-app inbox row when an identified logical
        # event is retried. Keep this portable across MySQL/SQLite by parsing a
        # small recent window instead of relying on vendor JSON SQL functions.
        notification_key = str((data or {}).get("notification_key") or "").strip()
        if notification_key:
            recent_rows = (
                db.query(Notification)
                .filter(
                    Notification.user_id == user_id,
                    Notification.user_type == user_type,
                )
                .order_by(Notification.id.desc())
                .limit(100)
                .all()
            )
            for recent in recent_rows:
                try:
                    recent_data = json.loads(recent.data or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if str(recent_data.get("notification_key") or "") == notification_key:
                    return recent
            
        notification = Notification(
            user_id=user_id,
            user_type=user_type,
            title=title,
            body=body,
            data=json.dumps(data) if data else None,
            is_deletable=is_deletable,
            redirect_route=redirect_route,
            redirect_args=json.dumps(redirect_args) if redirect_args else None
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification
    except Exception as e:
        logger.error(f"Error saving notification: {e}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            logger.exception("Failed to roll back notification inbox write")
        return None


def _delete_invalid_device_token(token_data: Any, token: str) -> None:
    """Remove one rejected FCM token using a worker-owned DB session.

    [send_notification] delivers tokens in parallel.  A SQLAlchemy Session is
    not thread-safe, so FCM workers must never reuse the caller's session for
    cleanup.
    """

    from ..core.database import SessionLocal

    cleanup_db = SessionLocal()
    try:
        if isinstance(token_data, dict) and token_data.get("id"):
            cleanup_db.execute(
                text("DELETE FROM device_tokens WHERE id = :tid"),
                {"tid": token_data["id"]},
            )
        else:
            cleanup_db.execute(
                text("DELETE FROM device_tokens WHERE device_token = :token"),
                {"token": token},
            )
        cleanup_db.commit()
        logger.info("Cleaned up invalid FCM token")
    except Exception:
        cleanup_db.rollback()
        logger.exception("Error cleaning invalid FCM token")
    finally:
        cleanup_db.close()


def _send_single_fcm(
    token_data: Any,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]],
    color: Optional[str],
    icon: Optional[str],
    actions: Optional[List[Dict[str, str]]],
    vibrate: bool,
    sound: Optional[str],
    channel_id: Optional[str],
    android_show_system_notification: bool,
    db: Optional[Session],
    image_url: Optional[str] = None,
    data_only: bool = False,
    collapse_id: Optional[str] = None,
) -> bool:
    """
    Send a single FCM push notification to one device token.
    Designed to be called from a ThreadPoolExecutor for parallel sending.
    Returns True on success, False on failure.

    collapse_id: notifications sharing the same id REPLACE each other in the
    device tray (Android notification tag + collapse_key, iOS
    apns-collapse-id) instead of stacking. Used for reminders where only the
    latest one is meaningful.
    """
    access_token = get_access_token()
    if not access_token:
        return False
    try:
        if isinstance(token_data, dict):
            token = token_data.get("token")
            device_type = token_data.get("device_type", "unknown").lower()
        else:
            token = str(token_data)
            device_type = "unknown"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        sound_name = sound or "default"
        android_channel = channel_id or "attendance_channel"
        android_notification = {
            "sound": sound_name,
            "channel_id": android_channel,
            "color": color or "#1976D2",
            "default_sound": True,
            "click_action": "FLUTTER_NOTIFICATION_CLICK"
        }
        if icon:
            android_notification["icon"] = icon
        if vibrate:
            android_notification["default_vibrate_timings"] = True

        resolved_image = resolve_push_image_url(image_url)
        # Never attach private/LAN images to FCM notification payload (can block delivery).
        fcm_image = (
            resolved_image if is_publicly_reachable_url(resolved_image) else None
        )

        message = {
            "message": {
                "token": token,
                "android": {"priority": "high"},
                "apns": {
                    "headers": {"apns-priority": "10"},
                    "payload": {
                        "aps": {
                            "sound": sound_name if sound else "default",
                            "badge": 1,
                            "alert": {"title": title, "body": body}
                        }
                    }
                },
                "fcm_options": {"analytics_label": "attendance_notification"}
            }
        }

        if collapse_id:
            # Same-id notifications replace each other instead of piling up.
            message["message"]["android"]["collapse_key"] = collapse_id
            android_notification["tag"] = collapse_id
            message["message"]["apns"]["headers"]["apns-collapse-id"] = collapse_id

        notification_block: Dict[str, Any] = {"title": title, "body": body}
        if fcm_image:
            notification_block["image"] = fcm_image

        if device_type != "android" and not data_only:
            message["message"]["notification"] = notification_block
            aps_dict = message["message"]["apns"]["payload"]["aps"]
            if fcm_image:
                aps_dict["mutable-content"] = 1
                apns_fcm_opts = message["message"]["apns"].setdefault(
                    "fcm_options", {}
                )
                apns_fcm_opts["image"] = fcm_image
            if actions:
                requested_category = str(
                    (data or {}).get("notification_category") or ""
                ).strip()
                aps_dict["category"] = (
                    requested_category or "ATTENDANCE_CATEGORY"
                )
            if data and data.get("student_id"):
                aps_dict["thread-id"] = str(data.get("student_id"))
        elif data_only and device_type != "android":
            aps_dict = message["message"]["apns"]["payload"]["aps"]
            aps_dict["content-available"] = 1

        if device_type == "android" and android_show_system_notification and not data_only:
            message["message"]["notification"] = notification_block
            if fcm_image:
                android_notification["image"] = fcm_image
            message["message"]["android"]["notification"] = android_notification
        elif device_type != "android":
            if fcm_image:
                android_notification["image"] = fcm_image
            message["message"]["android"]["notification"] = android_notification

        if not message["message"].get("data"):
            message["message"]["data"] = {}
        if data:
            for k, v in data.items():
                message["message"]["data"][k] = str(v)
        if fcm_image:
            message["message"]["data"]["image_url"] = fcm_image
        elif resolved_image and data and data.get("image_url"):
            # Keep client-relative paths (e.g. /uploads/push/...) for the app on LAN.
            pass
        elif resolved_image:
            message["message"]["data"]["image_url"] = resolved_image
        if device_type == "android" or data_only:
            message["message"]["data"]["title"] = title
            message["message"]["data"]["body"] = body
            if icon:
                message["message"]["data"]["icon"] = icon
        if actions:
            message["message"]["data"]["actions"] = json.dumps(actions)
            message["message"]["data"]["has_actions"] = "true"
            for idx, action in enumerate(actions):
                message["message"]["data"][f"action_{idx}_id"] = action.get("id", "")
                message["message"]["data"][f"action_{idx}_title"] = action.get("title", "")
                message["message"]["data"][f"action_{idx}_action"] = action.get("action", "")
        if actions and message["message"]["apns"]["payload"]["aps"].get("category"):
            message["message"]["data"]["ios_actions"] = json.dumps(actions)

        response = requests.post(FCM_URL, headers=headers, json=message, timeout=10)

        if response.status_code == 200:
            return True
        else:
            logger.error(f"FCM API error: {response.status_code} - {response.text}")
            # Auto-clean invalid/unregistered tokens
            try:
                error_data = None
                try:
                    error_data = response.json()
                except Exception:
                    pass
                is_unregistered = response.status_code == 404
                if not is_unregistered and error_data:
                    details = error_data.get("error", {}).get("details", [])
                    if any(d.get("errorCode") == "UNREGISTERED" for d in details):
                        is_unregistered = True
                if is_unregistered:
                    _delete_invalid_device_token(token_data, token)
            except Exception as pe:
                logger.error(f"Error processing FCM cleanup: {pe}")
            return False
    except Exception as e:
        logger.error(f"Error in _send_single_fcm: {e}")
        return False


# Maximum concurrent FCM HTTP calls. 20 is safe and fast for FCM v1.
_FCM_MAX_WORKERS = 20


def send_notification(
    device_tokens: List[Any],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    actions: Optional[List[Dict[str, str]]] = None,
    vibrate: bool = True,
    sound: Optional[str] = None,
    channel_id: Optional[str] = None,
    android_show_system_notification: bool = False,
    db: Optional[Session] = None,
    user_ids: Optional[List[Dict[str, Any]]] = None,
    is_deletable: bool = True,
    redirect_route: Optional[str] = None,
    redirect_args: Optional[Dict[str, Any]] = None,
    image_url: Optional[str] = None,
    data_only: bool = False,
    collapse_id: Optional[str] = None,
) -> bool:
    """
    Send push notifications to multiple devices in PARALLEL using ThreadPoolExecutor.
    Up to _FCM_MAX_WORKERS concurrent HTTP calls instead of sequential one-by-one.
    This dramatically reduces total time for large recipient lists.
    """
    # Every logical send gets one shared key across all of its FCM token
    # deliveries. Newer clients use it to ignore a duplicate delivery caused
    # by token rotation or a retried FCM request.
    data = dict(data or {})
    # A redirect supplied for the server-owned inbox must also ride in the FCM
    # data payload; otherwise tapping the system notification cannot use it.
    if redirect_route:
        data.setdefault("redirect_route", redirect_route)
    if redirect_args:
        for key, value in redirect_args.items():
            if value is not None:
                data.setdefault(str(key), str(value))
    data.setdefault(
        "notification_key",
        logical_notification_key(title, body, data) or uuid.uuid4().hex,
    )

    # Give every logical push a stable tray identity. If the same FCM message
    # is delivered through two stale token rows, Android/iOS replaces the first
    # system notification instead of stacking a visually identical second one.
    if not collapse_id:
        key_digest = hashlib.sha256(
            str(data["notification_key"]).encode("utf-8")
        ).hexdigest()[:32]
        collapse_id = f"notification_{key_digest}"

    # Persist one notification row per recipient account even if a caller
    # accidentally supplied that account more than once.
    if db and user_ids:
        unique_user_targets: List[Dict[str, Any]] = []
        seen_user_targets: set[tuple[Any, str]] = set()
        for user_info in user_ids:
            user_id = user_info.get("id")
            raw_user_type = str(
                user_info.get("user_type") or "teacher"
            ).lower()
            user_type = (
                raw_user_type
                if raw_user_type in {"teacher", "parent", "student"}
                else "teacher"
            )
            key = (user_id, user_type)
            if user_id is None or key in seen_user_targets:
                continue
            seen_user_targets.add(key)
            unique_user_targets.append(
                {**user_info, "id": user_id, "user_type": user_type}
            )
        user_ids = unique_user_targets
        for user_info in unique_user_targets:
            save_notification(
                db=db,
                user_id=user_info.get("id"),
                user_type=user_info.get("user_type"),
                title=title,
                body=body,
                data=data,
                is_deletable=is_deletable,
                redirect_route=redirect_route,
                redirect_args=redirect_args,
            )

    if not device_tokens and db and user_ids:
        device_tokens = resolve_device_tokens_for_users(db, user_ids)

    if not device_tokens:
        logger.warning(
            "No device tokens for push (user_ids=%s); in-app notification may still be saved",
            len(user_ids or []),
        )
        return False

    # Avoid duplicate pushes from exact duplicate rows and rotated tokens that
    # still point at the same known physical device.
    device_tokens = dedupe_device_tokens(device_tokens)
    device_tokens = filter_tokens_by_notification_preferences(db, device_tokens, data)
    if not device_tokens:
        logger.info(
            "All target devices disabled this notification category (%s)",
            notification_preference_category(data),
        )
        return False

    access_token = get_access_token()
    if not access_token:
        logger.warning("Could not get FCM access token, skipping notification")
        return False

    success_count = 0
    failure_count = 0
    total = len(device_tokens)

    logger.info(f"Sending notifications to {total} devices with up to {_FCM_MAX_WORKERS} parallel workers")

    try:
        with ThreadPoolExecutor(max_workers=_FCM_MAX_WORKERS) as executor:
            futures = {
                executor.submit(
                    _send_single_fcm,
                    token_data,
                    title, body, data, color, icon, actions,
                    vibrate, sound, channel_id,
                    android_show_system_notification, db,
                    image_url, data_only, collapse_id,
                ): token_data
                for token_data in device_tokens
            }
            for future in as_completed(futures):
                try:
                    if future.result():
                        success_count += 1
                    else:
                        failure_count += 1
                except Exception as e:
                    logger.error(f"FCM future raised: {e}")
                    failure_count += 1

    except Exception as e:
        logger.error(f"ThreadPoolExecutor error: {e}")
        return False

    logger.info(
        f"[FCM] Done: {success_count}/{total} sent, {failure_count} failed "
        f"(~{total / _FCM_MAX_WORKERS:.0f} rounds instead of {total} sequential calls)"
    )
    return success_count > 0


async def send_notification_async(*args, **kwargs) -> bool:
    """
    Async wrapper for send_notification that offloads to a thread.
    Use this from async route handlers to avoid blocking the event loop
    when sending push notifications to 100+ users.
    """
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: send_notification(*args, **kwargs)
    )



def send_attendance_notification(
    db: Session,
    student_id: int,
    student_name: str,
    attendance_status: str,
    attendance_date: str,
    class_info: Optional[str] = None,
    teacher_id: Optional[int] = None,
    action_type: str = "marked"  # "marked", "updated", or "cancelled"
) -> bool:
    """
    Send attendance notification to parents with action buttons, colors, and icons.
    
    Args:
        db: Database session
        student_id: Student ID
        student_name: Student name
        attendance_status: Attendance status (IsPresent, IsLate, IsAbsent, IsPermission)
        attendance_date: Attendance date (YYYY-MM-DD)
        class_info: Optional class information
        teacher_id: Teacher ID who marked attendance (for comment action)
        
    Returns:
        True if notification sent successfully
    """
    # Map attendance status to user-friendly text
    status_map = {
        "IsPresent": "Present",
        "IsLate": "Late",
        "IsAbsent": "Absent",
        "IsPermission": "Permission",
        "cancelled": "Cancelled",
    }
    
    status_text = status_map.get(attendance_status, attendance_status)
    
    # Get full student name (kName and eName) from database
    student_kname = ""
    student_ename = ""
    try:
        student_query = text("SELECT kName, eName FROM students WHERE id = :student_id")
        student_result = db.execute(student_query, {"student_id": student_id})
        student_row = student_result.fetchone()
        
        if student_row:
            student_kname = student_row[0] or ""
            student_ename = student_row[1] or ""
            # Build full name: kName (eName) or just one if the other is missing
            if student_kname and student_ename:
                full_name = f"{student_kname} ({student_ename})"
            elif student_kname:
                full_name = student_kname
            elif student_ename:
                full_name = student_ename
            else:
                full_name = student_name  # Fallback to provided name
        else:
            full_name = student_name
    except Exception as e:
        logger.warning(f"Error fetching student names: {e}, using provided name")
        full_name = student_name
        student_kname = ""
        student_ename = ""
    
    # Create notification title and body with full name
    title_map = {
        "marked": "Attendance Marked",
        "updated": "Attendance Updated",
        "cancelled": "Attendance Cancelled",
    }
    title = title_map.get(action_type, "Attendance Marked")
    if action_type == "cancelled":
        body = f"{full_name}'s attendance has been cancelled on {attendance_date}"
    else:
        body = f"{full_name} is marked as {status_text} on {attendance_date}"
    if class_info:
        body += f" ({class_info})"
    
    # Get parent device tokens
    device_tokens = get_parent_device_tokens(db, student_id)
    
    if not device_tokens:
        logger.warning(f"No device tokens found for parents of student {student_id}")
        return False
    
    logger.info(f"Found {len(device_tokens)} device token(s) for parents of student {student_id}")
    
    # Identify parents for saving notification (one row per parent account).
    parent_ids = []
    try:
        p_query = text("""
            SELECT DISTINCT p.id
            FROM parents p
            WHERE FIND_IN_SET(:student_id, p.myChilds) > 0
        """)
        p_result = db.execute(p_query, {"student_id": str(student_id)})
        parent_ids = [{"id": row[0], "user_type": "parent"} for row in p_result.fetchall()]
    except Exception as e:
        logger.error(f"Error identifying parents for notification save: {e}")
    
    # Determine color and icon based on attendance status
    color_map = {
        "IsPresent": "#4CAF50",  # Green
        "IsLate": "#FF9800",      # Orange
        "IsAbsent": "#F44336",    # Red
        "IsPermission": "#2196F3" # Blue
    }
    
    icon_map = {
        "IsPresent": "ic_check_circle",  # Icons.check_circle (matches attendance screen)
        "IsLate": "ic_access_time",     # Icons.access_time (matches attendance screen)
        "IsAbsent": "ic_cancel",        # Icons.cancel (matches attendance screen)
        "IsPermission": "ic_verified_user"  # Icons.verified_user (matches attendance screen)
    }
    
    color = color_map.get(attendance_status, "#1976D2")
    icon = icon_map.get(attendance_status, "ic_notification")
    
    # Define action buttons
    actions = [
        {
            "id": "comment",
            "title": "Comment",
            "action": "COMMENT"
        },
        {
            "id": "noted",
            "title": "Mark as read",
            "action": "NOTED"
        }
    ]
    
    # Prepare data payload with both kName and eName
    data = {
        "type": "attendance",
        "student_id": str(student_id),
        "student_name": full_name,  # Use full name with both kName and eName
        "student_kname": student_kname,
        "student_ename": student_ename,
        "attendance_status": attendance_status,
        "attendance_date": attendance_date,
        "teacher_id": str(teacher_id) if teacher_id else "",
        "has_actions": "true" # Indicate that notification has actions
    }
    
    # Send notification with enhanced features
    return send_notification(
        device_tokens=device_tokens,
        title=title,
        body=body,
        data=data,
        color=color,
        icon=icon,
        actions=actions,
        vibrate=True,
        # Persistence args
        db=db,
        user_ids=parent_ids,
        is_deletable=True, # Attendance can be deleted? Maybe yes.
        redirect_route="attendance", # Redirect to attendance screen
        redirect_args={"student_id": student_id}
    )
