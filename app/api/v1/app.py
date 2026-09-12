"""App-level endpoints (version check, etc.)"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, Field
from ...core import settings, get_db
from ...auth import get_current_active_user
from ...models.user import User
from .websocket import broadcast_public_data_update
from fastapi import UploadFile, File
from io import BytesIO
import json
import os
import uuid
from urllib.parse import urlparse
from PIL import Image, UnidentifiedImageError
from ...services.storage_service import StorageService
from ...models.settings import SystemSettings
from ...utils.file_utils import delete_local_file
from ...services.cache import social_links_cache

router = APIRouter()

DEFAULT_BRANDING = {
    "icon_name": "school_rounded",
    "top_text": "DEMO",
    "bottom_text": "INTERNATIONAL SCHOOL",
    "icon_background_color": "#1E5BD8",
    "icon_color": "#FFFFFF",
    "top_text_color": "#22252A",
    "bottom_text_color": "#6F7280",
    # Dark theme overrides (used when app is in dark mode)
    "icon_background_color_dark": "#1E5BD8",
    "icon_color_dark": "#FFFFFF",
    "top_text_color_dark": "#FFFFFF",
    "bottom_text_color_dark": "#B7C0D1",
    # Optional logo image (if enabled, show image instead of icon)
    "use_logo_image": False,
    "logo_image_url": "",
    "logo_image_url_dark": "",
}

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
QUICK_ACTION_ICON_ALLOWED_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
QUICK_ACTION_ICON_FORMAT_TYPES = {
    "JPEG": {"image/jpeg", "image/jpg"},
    "PNG": {"image/png"},
    "WEBP": {"image/webp"},
}
QUICK_ACTION_ICON_MAX_PIXELS = 16_000_000

TOP_STUDENTS_DISPLAY_TABLE = "results_top_students_display_settings"
LEGACY_TOP_STUDENTS_DISPLAY_TABLE = "top_students_display_settings"

DEFAULT_TOP_STUDENTS_DISPLAY = {
    "avatar_chip_mode": "rank",  # rank | grade
    "hide_section": False,
    "hide_medals_section": False,
}

QUICK_ACTIONS_TABLE = "app_quick_action_settings"
QUICK_ACTION_BUILT_IN_IDS = {"contact", "admissions", "fees"}
DEFAULT_QUICK_ACTIONS = [
    {
        "id": "contact",
        "kind": "contact",
        "title_en": "Contact & map",
        "title_km": "ទំនាក់ទំនង និងផែនទី",
        "title_zh": "联系与地图",
        "url": None,
        "icon_name": "contact_phone",
        "color_hex": "#1677F2",
        "visible": True,
        "sort_order": 0,
        "open_mode": "embedded",
        "highlight_new": False,
    },
    {
        "id": "admissions",
        "kind": "admissions",
        "title_en": "Admissions",
        "title_km": "ចុះឈ្មោះសិស្ស",
        "title_zh": "招生",
        "url": None,
        "icon_name": "assignment",
        "color_hex": "#1677F2",
        "visible": True,
        "sort_order": 1,
        "open_mode": "embedded",
        "highlight_new": False,
    },
    {
        "id": "fees",
        "kind": "fees",
        "title_en": "Fees",
        "title_km": "ថ្លៃសិក្សា",
        "title_zh": "费用",
        "url": None,
        "icon_name": "payments",
        "color_hex": "#1677F2",
        "visible": True,
        "sort_order": 2,
        "open_mode": "embedded",
        "highlight_new": False,
    },
]


class AppBrandingResponse(BaseModel):
    icon_name: str
    top_text: str
    bottom_text: str
    icon_background_color: str
    icon_color: str
    top_text_color: str
    bottom_text_color: str
    icon_background_color_dark: str
    icon_color_dark: str
    top_text_color_dark: str
    bottom_text_color_dark: str
    use_logo_image: bool
    logo_image_url: str
    logo_image_url_dark: str


class AppBrandingUpdate(BaseModel):
    icon_name: str = Field(..., min_length=1, max_length=120)
    top_text: str = Field(..., min_length=1, max_length=80)
    bottom_text: str = Field(..., min_length=1, max_length=120)
    icon_background_color: str = Field(..., min_length=4, max_length=20)
    icon_color: str = Field(..., min_length=4, max_length=20)
    top_text_color: str = Field(..., min_length=4, max_length=20)
    bottom_text_color: str = Field(..., min_length=4, max_length=20)
    icon_background_color_dark: str = Field(..., min_length=4, max_length=20)
    icon_color_dark: str = Field(..., min_length=4, max_length=20)
    top_text_color_dark: str = Field(..., min_length=4, max_length=20)
    bottom_text_color_dark: str = Field(..., min_length=4, max_length=20)
    use_logo_image: bool = False
    logo_image_url: str = ""
    logo_image_url_dark: str = ""


def _is_admin(user: User) -> bool:
    role_id = getattr(user, "role", None)
    return role_id is not None and int(role_id) == 1


def _read_or_create_branding_row(db: Session) -> dict:
    # Ensure new dark-theme columns exist (idempotent).
    # This keeps the endpoint compatible even if migrations weren't run yet.
    try:
        cols = {
            "icon_background_color_dark": "VARCHAR(20) NULL",
            "icon_color_dark": "VARCHAR(20) NULL",
            "top_text_color_dark": "VARCHAR(20) NULL",
            "bottom_text_color_dark": "VARCHAR(20) NULL",
            "use_logo_image": "TINYINT(1) NOT NULL DEFAULT 0",
            "logo_image_url": "VARCHAR(255) NULL",
            "logo_image_url_dark": "VARCHAR(255) NULL",
        }
        for col, ddl in cols.items():
            exists = db.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'app_branding_settings'
                      AND COLUMN_NAME = :col
                    LIMIT 1
                    """
                ),
                {"col": col},
            ).fetchone()
            if not exists:
                db.execute(
                    text(f"ALTER TABLE app_branding_settings ADD COLUMN {col} {ddl}")
                )
        db.commit()
    except Exception:
        # If we can't alter (permissions), we still try to read using legacy columns.
        pass

    row = db.execute(
        text(
            """
            SELECT
                icon_name,
                top_text,
                bottom_text,
                icon_background_color,
                icon_color,
                top_text_color,
                bottom_text_color,
                icon_background_color_dark,
                icon_color_dark,
                top_text_color_dark,
                bottom_text_color_dark,
                use_logo_image,
                logo_image_url,
                logo_image_url_dark
            FROM app_branding_settings
            WHERE id = 1
            LIMIT 1
            """
        )
    ).fetchone()

    if row:
        return {
            "icon_name": row[0] or DEFAULT_BRANDING["icon_name"],
            "top_text": row[1] or DEFAULT_BRANDING["top_text"],
            "bottom_text": row[2] or DEFAULT_BRANDING["bottom_text"],
            "icon_background_color": row[3]
            or DEFAULT_BRANDING["icon_background_color"],
            "icon_color": row[4] or DEFAULT_BRANDING["icon_color"],
            "top_text_color": row[5] or DEFAULT_BRANDING["top_text_color"],
            "bottom_text_color": row[6] or DEFAULT_BRANDING["bottom_text_color"],
            "icon_background_color_dark": row[7]
            or DEFAULT_BRANDING["icon_background_color_dark"],
            "icon_color_dark": row[8] or DEFAULT_BRANDING["icon_color_dark"],
            "top_text_color_dark": row[9] or DEFAULT_BRANDING["top_text_color_dark"],
            "bottom_text_color_dark": row[10]
            or DEFAULT_BRANDING["bottom_text_color_dark"],
            "use_logo_image": bool(row[11])
            if row[11] is not None
            else bool(DEFAULT_BRANDING["use_logo_image"]),
            "logo_image_url": row[12] or DEFAULT_BRANDING["logo_image_url"],
            "logo_image_url_dark": row[13] or DEFAULT_BRANDING["logo_image_url_dark"],
        }

    db.execute(
        text(
            """
            INSERT INTO app_branding_settings (
                id,
                icon_name,
                top_text,
                bottom_text,
                icon_background_color,
                icon_color,
                top_text_color,
                bottom_text_color,
                icon_background_color_dark,
                icon_color_dark,
                top_text_color_dark,
                bottom_text_color_dark,
                use_logo_image,
                logo_image_url,
                logo_image_url_dark
            ) VALUES (
                1,
                :icon_name,
                :top_text,
                :bottom_text,
                :icon_background_color,
                :icon_color,
                :top_text_color,
                :bottom_text_color,
                :icon_background_color_dark,
                :icon_color_dark,
                :top_text_color_dark,
                :bottom_text_color_dark,
                :use_logo_image,
                :logo_image_url,
                :logo_image_url_dark
            )
            """
        ),
        DEFAULT_BRANDING,
    )
    db.commit()
    return dict(DEFAULT_BRANDING)


def _table_exists(db: Session, table_name: str) -> bool:
    row = db.execute(
        text(
            """
            SELECT 1
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
            LIMIT 1
            """
        ),
        {"table_name": table_name},
    ).fetchone()
    return row is not None


def _ensure_top_students_display_table(db: Session) -> None:
    # MySQL-compatible DDL. Keeps this deployable without running migrations.
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS results_top_students_display_settings (
                id INT PRIMARY KEY,
                avatar_chip_mode VARCHAR(10) NULL,
                hide_section TINYINT(1) NOT NULL DEFAULT 0,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.commit()

    # Auto-add hide_medals_section column if it doesn't exist yet (idempotent migration).
    try:
        col_exists = db.execute(
            text(
                """
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'results_top_students_display_settings'
                  AND COLUMN_NAME = 'hide_medals_section'
                LIMIT 1
                """
            )
        ).fetchone()
        if not col_exists:
            db.execute(
                text(
                    "ALTER TABLE results_top_students_display_settings "
                    "ADD COLUMN hide_medals_section TINYINT(1) NOT NULL DEFAULT 0"
                )
            )
            db.commit()
    except Exception:
        pass  # If ALTER fails due to permissions, we still try to proceed.

    # Auto-migrate legacy table (if any) into the new table.
    # This runs safely even if legacy table doesn't exist.
    if _table_exists(db, LEGACY_TOP_STUDENTS_DISPLAY_TABLE):
        db.execute(
            text(
                """
                INSERT INTO results_top_students_display_settings (id, avatar_chip_mode, hide_section)
                SELECT 1, avatar_chip_mode, hide_section
                FROM top_students_display_settings
                WHERE id = 1
                ON DUPLICATE KEY UPDATE
                    avatar_chip_mode = VALUES(avatar_chip_mode),
                    hide_section = VALUES(hide_section)
                """
            )
        )
        db.commit()


def _read_or_create_top_students_display_row(db: Session) -> dict:
    _ensure_top_students_display_table(db)
    # Try to read including the new hide_medals_section column.
    # Fall back gracefully if DB hasn't migrated yet.
    try:
        row = db.execute(
            text(
                """
                SELECT avatar_chip_mode, hide_section, hide_medals_section
                FROM results_top_students_display_settings
                WHERE id = 1
                LIMIT 1
                """
            )
        ).fetchone()
    except Exception:
        row = None

    if row:
        mode = (
            (row[0] or DEFAULT_TOP_STUDENTS_DISPLAY["avatar_chip_mode"]).strip().lower()
        )
        mode = "grade" if mode == "grade" else "rank"
        hide = (
            bool(row[1])
            if row[1] is not None
            else bool(DEFAULT_TOP_STUDENTS_DISPLAY["hide_section"])
        )
        hide_medals = (
            bool(row[2])
            if row[2] is not None
            else bool(DEFAULT_TOP_STUDENTS_DISPLAY["hide_medals_section"])
        )
        return {
            "avatar_chip_mode": mode,
            "hide_section": hide,
            "hide_medals_section": hide_medals,
        }

    db.execute(
        text(
            """
            INSERT INTO results_top_students_display_settings
                (id, avatar_chip_mode, hide_section, hide_medals_section)
            VALUES (1, :avatar_chip_mode, :hide_section, :hide_medals_section)
            """
        ),
        {
            "avatar_chip_mode": DEFAULT_TOP_STUDENTS_DISPLAY["avatar_chip_mode"],
            "hide_section": 1 if DEFAULT_TOP_STUDENTS_DISPLAY["hide_section"] else 0,
            "hide_medals_section": 1
            if DEFAULT_TOP_STUDENTS_DISPLAY["hide_medals_section"]
            else 0,
        },
    )
    db.commit()
    return dict(DEFAULT_TOP_STUDENTS_DISPLAY)


def _default_quick_actions() -> "list[QuickActionItem]":
    return [QuickActionItem(**item) for item in DEFAULT_QUICK_ACTIONS]


def _normalize_quick_actions(
    items: "list[QuickActionItem]",
    *,
    strict: bool,
) -> "list[QuickActionItem]":
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        if strict:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Quick action IDs must be unique",
            )
        return _default_quick_actions()

    if not QUICK_ACTION_BUILT_IN_IDS.issubset(ids):
        if strict:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact, admissions, and fees actions are required",
            )
        return _default_quick_actions()

    normalized: "list[QuickActionItem]" = []
    for index, item in enumerate(items):
        title_en = item.title_en.strip()
        title_km = item.title_km.strip()
        title_zh = item.title_zh.strip()
        url = item.url.strip() if item.url else None
        icon_image_url = item.icon_image_url.strip()

        if icon_image_url:
            parsed_icon = urlparse(icon_image_url)
            is_https = (
                parsed_icon.scheme.lower() == "https"
                and bool(parsed_icon.hostname)
            )
            is_managed_upload = icon_image_url.startswith("/uploads/")
            if not is_https and not is_managed_upload:
                if strict:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Icon image URL must use HTTPS",
                    )
                icon_image_url = ""

        if item.id in QUICK_ACTION_BUILT_IN_IDS:
            if item.kind != item.id:
                if strict:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"Built-in action '{item.id}' cannot change type",
                    )
                return _default_quick_actions()
            url = None
        else:
            if item.kind != "website" or not title_en or not url:
                if strict:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Website actions require an English title and HTTPS URL",
                    )
                return _default_quick_actions()
            parsed = urlparse(url)
            if parsed.scheme.lower() != "https" or not parsed.hostname:
                if strict:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Website URL must be a valid HTTPS address",
                    )
                return _default_quick_actions()

        normalized.append(
            item.model_copy(
                update={
                    "title_en": title_en,
                    "title_km": title_km,
                    "title_zh": title_zh,
                    "url": url,
                    "icon_image_url": icon_image_url,
                    "sort_order": index,
                }
            )
        )
    return normalized


def _preserve_quick_action_compatibility_fields(
    incoming: "list[QuickActionItem]",
    existing: "list[QuickActionItem]",
) -> "list[QuickActionItem]":
    """Keep newer presentation fields when an older client omits them."""
    existing_by_id = {item.id: item for item in existing}
    merged: "list[QuickActionItem]" = []
    for item in incoming:
        current = existing_by_id.get(item.id)
        if current is not None:
            compatibility_updates = {}
            if "highlight_new" not in item.model_fields_set:
                compatibility_updates["highlight_new"] = current.highlight_new
            if "icon_image_url" not in item.model_fields_set:
                compatibility_updates["icon_image_url"] = current.icon_image_url
            if compatibility_updates:
                item = item.model_copy(update=compatibility_updates)
        merged.append(item)
    return merged


def _validate_quick_action_icon_upload(data: bytes, content_type: str) -> str:
    """Validate a square shortcut icon and return its trusted extension."""
    normalized_type = (content_type or "").strip().lower()
    if normalized_type not in QUICK_ACTION_ICON_ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JPEG, PNG, and WebP images are allowed",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image file is empty",
        )
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be 5 MB or smaller",
        )

    try:
        with Image.open(BytesIO(data)) as image:
            detected_format = str(image.format or "").upper()
            width, height = image.size
            if (
                width <= 0
                or height <= 0
                or width * height > QUICK_ACTION_ICON_MAX_PIXELS
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Image dimensions are invalid or too large",
                )
            if width != height:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Shortcut icon must use a square 1:1 crop",
                )
            if normalized_type not in QUICK_ACTION_ICON_FORMAT_TYPES.get(
                detected_format,
                set(),
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File content does not match its image type",
                )
            image.verify()
    except HTTPException:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not a valid image",
        )

    return {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
    }[detected_format]


def _ensure_quick_actions_table(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS app_quick_action_settings (
                id INT PRIMARY KEY,
                items_json TEXT NOT NULL,
                updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    db.commit()


def _read_or_create_quick_actions(db: Session) -> "list[QuickActionItem]":
    _ensure_quick_actions_table(db)
    row = db.execute(
        text(
            """
            SELECT items_json
            FROM app_quick_action_settings
            WHERE id = 1
            LIMIT 1
            """
        )
    ).fetchone()

    if row:
        try:
            raw_items = json.loads(row[0] or "[]")
            parsed = [QuickActionItem(**item) for item in raw_items]
            return _normalize_quick_actions(parsed, strict=False)
        except Exception:
            defaults = _default_quick_actions()
            _write_quick_actions(db, defaults)
            return defaults

    defaults = _default_quick_actions()
    _write_quick_actions(db, defaults)
    return defaults


def _write_quick_actions(db: Session, items: "list[QuickActionItem]") -> None:
    payload = json.dumps(
        [item.model_dump() for item in items],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    existing = db.execute(
        text("SELECT id FROM app_quick_action_settings WHERE id = 1 LIMIT 1")
    ).fetchone()
    if existing:
        db.execute(
            text(
                """
                UPDATE app_quick_action_settings
                SET items_json = :items_json,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """
            ),
            {"items_json": payload},
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO app_quick_action_settings (id, items_json)
                VALUES (1, :items_json)
                """
            ),
            {"items_json": payload},
        )
    db.commit()


class TopStudentsDisplayResponse(BaseModel):
    avatar_chip_mode: str = Field(..., pattern="^(rank|grade)$")
    hide_section: bool
    hide_medals_section: bool = False


class TopStudentsDisplayUpdate(BaseModel):
    avatar_chip_mode: str = Field(..., pattern="^(rank|grade)$")
    hide_section: bool
    hide_medals_section: bool = False


class QuickActionItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    kind: str = Field(
        ...,
        pattern=r"^(contact|admissions|fees|website)$",
    )
    title_en: str = Field(..., max_length=80)
    title_km: str = Field(default="", max_length=120)
    title_zh: str = Field(default="", max_length=80)
    url: str | None = Field(default=None, max_length=2048)
    icon_name: str = Field(
        default="language",
        pattern=r"^(contact_phone|assignment|payments|language|school|campaign|menu_book|newspaper|play_circle|calendar|storefront|groups|trophy|public|link)$",
    )
    color_hex: str = Field(default="#1677F2", pattern=r"^#[0-9A-Fa-f]{6}$")
    visible: bool = True
    sort_order: int = Field(default=0, ge=0, le=99)
    open_mode: str = Field(default="embedded", pattern=r"^(embedded|external)$")
    highlight_new: bool = False
    icon_image_url: str = Field(default="", max_length=2048)


class QuickActionsResponse(BaseModel):
    items: list[QuickActionItem]


class QuickActionsUpdate(BaseModel):
    items: list[QuickActionItem] = Field(..., min_length=3, max_length=20)


# REMOVED: /version endpoint - Flutter app checks stores directly now
# No backend needed for version checking!


@router.get("/social-links")
async def get_social_links(db: Session = Depends(get_db)):
    """
    Returns global social media links for the application (cached).
    """
    cached = social_links_cache.get("global_social_links")
    if cached is not None:
        return cached

    try:
        check_query = text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'settings'
            AND COLUMN_NAME = 'facebook_url'
        """)

        has_columns = db.execute(check_query).fetchone() is not None

        if not has_columns:
            result = {
                "facebook": None,
                "telegram": None,
                "youtube": None,
                "instagram": None,
                "tiktok": None,
            }
            social_links_cache.set("global_social_links", result)
            return result

        query = text("""
            SELECT facebook_url, telegram_url, youtube_url, instagram_url, tiktok_url
            FROM settings 
            LIMIT 1
        """)
        result_db = db.execute(query).fetchone()

        if result_db:
            result = {
                "facebook": result_db[0],
                "telegram": result_db[1],
                "youtube": result_db[2],
                "instagram": result_db[3],
                "tiktok": result_db[4],
            }
        else:
            result = {
                "facebook": None,
                "telegram": None,
                "youtube": None,
                "instagram": None,
                "tiktok": None,
            }

        social_links_cache.set("global_social_links", result)
        return result
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching global social links: {e}")
        return {
            "facebook": None,
            "telegram": None,
            "youtube": None,
            "instagram": None,
            "tiktok": None,
        }

        # Get settings row
        query = text("""
            SELECT facebook_url, telegram_url, youtube_url, instagram_url, tiktok_url
            FROM settings 
            LIMIT 1
        """)
        result = db.execute(query).fetchone()

        if result:
            return {
                "facebook": result[0],
                "telegram": result[1],
                "youtube": result[2],
                "instagram": result[3],
                "tiktok": result[4],
            }

        return {
            "facebook": None,
            "telegram": None,
            "youtube": None,
            "instagram": None,
            "tiktok": None,
        }
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching global social links: {e}")
        return {
            "facebook": None,
            "telegram": None,
            "youtube": None,
            "instagram": None,
            "tiktok": None,
        }


@router.get("/branding", response_model=AppBrandingResponse)
async def get_app_branding(db: Session = Depends(get_db)):
    """
    Public endpoint for app header branding on home screen.
    """
    try:
        data = _read_or_create_branding_row(db)
        return AppBrandingResponse(**data)
    except Exception:
        return AppBrandingResponse(**DEFAULT_BRANDING)


@router.get("/branding/admin", response_model=AppBrandingResponse)
async def get_app_branding_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    data = _read_or_create_branding_row(db)
    return AppBrandingResponse(**data)


@router.put("/branding/admin", response_model=AppBrandingResponse)
async def update_app_branding_admin(
    payload: AppBrandingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    current = _read_or_create_branding_row(db)
    db.execute(
        text(
            """
            UPDATE app_branding_settings
            SET
                icon_name = :icon_name,
                top_text = :top_text,
                bottom_text = :bottom_text,
                icon_background_color = :icon_background_color,
                icon_color = :icon_color,
                top_text_color = :top_text_color,
                bottom_text_color = :bottom_text_color,
                icon_background_color_dark = :icon_background_color_dark,
                icon_color_dark = :icon_color_dark,
                top_text_color_dark = :top_text_color_dark,
                bottom_text_color_dark = :bottom_text_color_dark,
                use_logo_image = :use_logo_image,
                logo_image_url = :logo_image_url,
                logo_image_url_dark = :logo_image_url_dark
            WHERE id = 1
            """
        ),
        payload.model_dump(),
    )
    db.commit()
    # If admin replaced/cleared logo URLs via settings, remove old files.
    try:
        settings_row = db.query(SystemSettings).first()
        new_light = (payload.logo_image_url or "").strip()
        new_dark = (payload.logo_image_url_dark or "").strip()
        old_light = (current.get("logo_image_url") or "").strip()
        old_dark = (current.get("logo_image_url_dark") or "").strip()

        if old_light and old_light != new_light:
            if settings_row:
                StorageService.delete_file(old_light, settings_row)
            else:
                delete_local_file(old_light)
        if old_dark and old_dark != new_dark:
            if settings_row:
                StorageService.delete_file(old_dark, settings_row)
            else:
                delete_local_file(old_dark)
    except Exception:
        pass

    await broadcast_public_data_update("branding")
    return AppBrandingResponse(**payload.model_dump())


@router.post("/branding/admin/logo", response_model=AppBrandingResponse)
async def upload_branding_logo_admin(
    theme: str = "light",  # light | dark
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, WEBP, GIF are allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Max size is 5 MB.",
        )

    theme = (theme or "light").strip().lower()
    if theme not in {"light", "dark"}:
        theme = "light"

    # Ensure row exists and read current values
    current = _read_or_create_branding_row(db)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ext = ".jpg"
    unique_filename = f"branding_logo_{theme}_{uuid.uuid4().hex[:10]}{ext}"

    logo_url = StorageService.upload_file(
        file_data=contents,
        folder="branding",
        filename=unique_filename,
        content_type=file.content_type,
    )
    if not logo_url:
        raise HTTPException(status_code=500, detail="Failed to upload logo")

    # Delete old file (if any) using StorageService provider logic
    settings_row = db.query(SystemSettings).first()
    old_url = (
        current["logo_image_url_dark"] if theme == "dark" else current["logo_image_url"]
    )
    if old_url:
        if settings_row:
            StorageService.delete_file(old_url, settings_row)
        else:
            delete_local_file(old_url)

    db.execute(
        text(
            """
            UPDATE app_branding_settings
            SET logo_image_url = COALESCE(:logo_image_url, logo_image_url),
                logo_image_url_dark = COALESCE(:logo_image_url_dark, logo_image_url_dark)
            WHERE id = 1
            """
        ),
        {
            "logo_image_url": logo_url if theme == "light" else None,
            "logo_image_url_dark": logo_url if theme == "dark" else None,
        },
    )
    db.commit()

    await broadcast_public_data_update("branding")
    updated = _read_or_create_branding_row(db)
    return AppBrandingResponse(**updated)


@router.get("/top-students-display", response_model=TopStudentsDisplayResponse)
async def get_top_students_display_settings(db: Session = Depends(get_db)):
    """
    Public endpoint for Students of the Month display preferences.
    This is a GLOBAL (everyone) setting.
    """
    data = _read_or_create_top_students_display_row(db)
    return TopStudentsDisplayResponse(**data)


@router.get("/top-students-display/admin", response_model=TopStudentsDisplayResponse)
async def get_top_students_display_settings_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    data = _read_or_create_top_students_display_row(db)
    return TopStudentsDisplayResponse(**data)


@router.put("/top-students-display/admin", response_model=TopStudentsDisplayResponse)
async def update_top_students_display_settings_admin(
    payload: TopStudentsDisplayUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    _read_or_create_top_students_display_row(db)
    db.execute(
        text(
            """
            UPDATE results_top_students_display_settings
            SET avatar_chip_mode = :avatar_chip_mode,
                hide_section = :hide_section,
                hide_medals_section = :hide_medals_section
            WHERE id = 1
            """
        ),
        {
            "avatar_chip_mode": payload.avatar_chip_mode,
            "hide_section": 1 if payload.hide_section else 0,
            "hide_medals_section": 1 if payload.hide_medals_section else 0,
        },
    )
    db.commit()

    await broadcast_public_data_update("top_students_display")

    return TopStudentsDisplayResponse(**payload.model_dump())


@router.get("/quick-actions", response_model=QuickActionsResponse)
async def get_quick_actions(db: Session = Depends(get_db)):
    """Return the visible PAMA home shortcuts in the admin-defined order."""
    items = _read_or_create_quick_actions(db)
    return QuickActionsResponse(items=[item for item in items if item.visible])


@router.get("/quick-actions/admin", response_model=QuickActionsResponse)
async def get_quick_actions_admin(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return QuickActionsResponse(items=_read_or_create_quick_actions(db))


@router.put("/quick-actions/admin", response_model=QuickActionsResponse)
async def update_quick_actions_admin(
    payload: QuickActionsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    compatible_items = _preserve_quick_action_compatibility_fields(
        payload.items,
        _read_or_create_quick_actions(db),
    )
    items = _normalize_quick_actions(compatible_items, strict=True)
    _ensure_quick_actions_table(db)
    _write_quick_actions(db, items)
    await broadcast_public_data_update("quick_actions")
    return QuickActionsResponse(items=items)


@router.post("/quick-actions/admin/icon")
async def upload_quick_action_icon_admin(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )

    contents = await file.read()
    extension = _validate_quick_action_icon_upload(
        contents,
        file.content_type or "",
    )
    filename = f"quick_action_icon_{uuid.uuid4().hex[:16]}{extension}"
    content_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[extension]
    image_url = StorageService.upload_file(
        file_data=contents,
        folder="quick_actions",
        filename=filename,
        content_type=content_type,
    )
    if not image_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload shortcut icon",
        )
    return {"url": image_url}
