"""
Group Admin API endpoints for managing groups, members, bans, and settings.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ...core import get_db
from ...schemas import (
    AddMemberRequest, RemoveMemberRequest,
    BanUserRequest, BanResponse,
    GroupSettingsResponse, UpdateSettingsRequest,
    MessageGroupMemberResponse
)
from ...models import (
    MessageGroup, MessageGroupMember, MessageGroupBan, MessageGroupSettings,
    GroupMessage
)
from ...models.message import MessageType, UserType
from ...auth.dependencies import Principal, get_current_principal

router = APIRouter()


async def _broadcast_chat_moderation(group_id: int, payload: dict) -> None:
    """Notify all members in the group chat over WebSocket (cross-worker safe)."""
    try:
        from .messages import broadcast_group_ws
        await broadcast_group_ws(group_id, payload)
    except Exception:
        pass


def _check_admin_permission(db: Session, group_id: int, principal: Principal):
    """Check if user is an admin of the group.

    ``user_id`` is only unique *within* a ``user_type``: parents, students and
    employees each have their own ID sequence. Matching without the type would
    hand a parent the group-admin rights of the employee sharing their ID.
    """
    admin_check = db.query(MessageGroupMember).filter(
        MessageGroupMember.group_id == group_id,
        MessageGroupMember.user_id == principal.id,
        MessageGroupMember.user_type.in_(principal.member_types),
        MessageGroupMember.role == 'admin'
    ).first()

    if not admin_check:
        raise HTTPException(status_code=403, detail="You must be a group admin to perform this action")
    return True


def _parse_user_type(value: str) -> UserType:
    """Normalize user_type string to UserType enum (accepts 'parent', 'PARENT', etc.)."""
    if not value:
        return UserType.parent
    s = value.strip().lower()
    try:
        return UserType(s)
    except ValueError:
        return UserType.parent


# ==================== Member Management ====================

@router.post("/groups/{group_id}/members/add", response_model=MessageGroupMemberResponse)
async def add_member(
    group_id: int,
    request: AddMemberRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Add a member to a group. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Check if member already exists
    requested_type = _parse_user_type(request.user_type)
    existing = db.query(MessageGroupMember).filter(
        MessageGroupMember.group_id == group_id,
        MessageGroupMember.user_id == request.user_id,
        MessageGroupMember.user_type == requested_type
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member of this group")
    
    # Add member (normalize user_type so PARENT/parent both work)
    new_member = MessageGroupMember(
        group_id=group_id,
        user_id=request.user_id,
        user_type=requested_type,
        role=request.role
    )
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    
    # Get user details for response
    query = text("""
        SELECT 
            mgm.id, mgm.group_id, mgm.user_id, mgm.user_type, mgm.role, mgm.joined_at,
            CASE 
                WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' THEN u.username
                WHEN mgm.user_type = 'parent' THEN p.username
                ELSE CAST(mgm.user_id AS CHAR)
            END as user_name,
            CASE 
                WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' THEN u.kName
                WHEN mgm.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                ELSE ''
            END as user_k_name,
            CASE 
                WHEN mgm.user_type = 'teacher' OR mgm.user_type = 'employee' THEN u.eName
                WHEN mgm.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                ELSE ''
            END as user_e_name
        FROM message_group_members mgm
        LEFT JOIN users u ON (mgm.user_type IN ('teacher', 'employee') AND mgm.user_id = u.id)
        LEFT JOIN parents p ON (mgm.user_type = 'parent' AND mgm.user_id = p.id)
        WHERE mgm.id = :member_id
    """)
    
    result = db.execute(query, {"member_id": new_member.id}).fetchone()
    
    return MessageGroupMemberResponse(
        id=result.id,
        group_id=result.group_id,
        user_id=result.user_id,
        role=result.role,
        joined_at=result.joined_at,
        user_name=result.user_name,
        user_k_name=result.user_k_name,
        user_e_name=result.user_e_name
    )


@router.delete("/groups/{group_id}/members/{member_id}")
async def remove_member(
    group_id: int,
    member_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Remove/kick a member from a group. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get member
    member = db.query(MessageGroupMember).filter(
        MessageGroupMember.id == member_id,
        MessageGroupMember.group_id == group_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Don't allow removing self (same ID in a different table is a different person)
    if member.user_id == current_user_id and member.user_type in principal.member_types:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the group")
    
    # Delete member
    db.delete(member)
    db.commit()
    
    return {"message": "Member removed successfully"}


# ==================== Ban Management ====================

@router.post("/groups/{group_id}/bans", response_model=BanResponse)
async def ban_user(
    group_id: int,
    request: BanUserRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Ban a user from a group. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Check if ban already exists
    banned_type = _parse_user_type(request.user_type)
    existing_ban = db.query(MessageGroupBan).filter(
        MessageGroupBan.group_id == group_id,
        MessageGroupBan.user_id == request.user_id,
        MessageGroupBan.user_type == banned_type,
        MessageGroupBan.is_active == 1
    ).first()
    
    if existing_ban:
        raise HTTPException(status_code=400, detail="User is already banned from this group")
    
    # Create ban (normalize user_type so PARENT/parent both work)
    new_ban = MessageGroupBan(
        group_id=group_id,
        user_id=request.user_id,
        user_type=banned_type,
        banned_by=current_user_id,
        reason=request.reason,
        expires_at=request.expires_at
    )
    db.add(new_ban)
    db.commit()
    db.refresh(new_ban)
    
    # Get user details for response
    query = text("""
        SELECT 
            b.id, b.group_id, b.user_id, b.user_type, b.banned_by, b.reason,
            b.banned_at, b.expires_at, b.is_active,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.username
                WHEN b.user_type = 'parent' THEN p.username
                ELSE CAST(b.user_id AS CHAR)
            END as user_name,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.kName
                WHEN b.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                ELSE ''
            END as user_k_name,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.eName
                WHEN b.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                ELSE ''
            END as user_e_name
        FROM message_group_bans b
        LEFT JOIN users u ON (b.user_type IN ('teacher', 'employee') AND b.user_id = u.id)
        LEFT JOIN parents p ON (b.user_type = 'parent' AND b.user_id = p.id)
        WHERE b.id = :ban_id
    """)
    
    result = db.execute(query, {"ban_id": new_ban.id}).fetchone()
    
    return BanResponse(
        id=result.id,
        group_id=result.group_id,
        user_id=result.user_id,
        user_type=result.user_type,
        banned_by=result.banned_by,
        reason=result.reason,
        banned_at=result.banned_at,
        expires_at=result.expires_at,
        is_active=bool(result.is_active),
        user_name=result.user_name,
        user_k_name=result.user_k_name,
        user_e_name=result.user_e_name
    )


@router.delete("/groups/{group_id}/bans/{user_id}")
async def unban_user(
    group_id: int,
    user_id: int,
    user_type: Optional[str] = Query(
        None, description="Which table user_id refers to: teacher/employee/parent/student"
    ),
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Unban a user from a group. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)

    # Find active ban. ``user_id`` alone is ambiguous across tables, so callers
    # should pass user_type; without it we can only match the single active ban.
    filters = [
        MessageGroupBan.group_id == group_id,
        MessageGroupBan.user_id == user_id,
        MessageGroupBan.is_active == 1,
    ]
    if user_type:
        filters.append(MessageGroupBan.user_type == _parse_user_type(user_type))
    ban = db.query(MessageGroupBan).filter(*filters).first()

    if not ban:
        raise HTTPException(status_code=404, detail="Active ban not found")
    
    # Deactivate ban
    ban.is_active = 0
    db.commit()
    
    return {"message": "User unbanned successfully"}


@router.get("/groups/{group_id}/bans", response_model=List[BanResponse])
async def get_banned_users(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get list of banned users in a group. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get bans with user details
    query = text("""
        SELECT 
            b.id, b.group_id, b.user_id, b.user_type, b.banned_by, b.reason,
            b.banned_at, b.expires_at, b.is_active,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.username
                WHEN b.user_type = 'parent' THEN p.username
                ELSE CAST(b.user_id AS CHAR)
            END as user_name,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.kName
                WHEN b.user_type = 'parent' THEN COALESCE(p.motherName, p.fatherName, '')
                ELSE ''
            END as user_k_name,
            CASE 
                WHEN b.user_type = 'teacher' OR b.user_type = 'employee' THEN u.eName
                WHEN b.user_type = 'parent' THEN COALESCE(p.fatherName, p.motherName, '')
                ELSE ''
            END as user_e_name
        FROM message_group_bans b
        LEFT JOIN users u ON (b.user_type IN ('teacher', 'employee') AND b.user_id = u.id)
        LEFT JOIN parents p ON (b.user_type = 'parent' AND b.user_id = p.id)
        WHERE b.group_id = :group_id AND b.is_active = 1
        ORDER BY b.banned_at DESC
    """)
    
    results = db.execute(query, {"group_id": group_id}).fetchall()
    
    return [
        BanResponse(
            id=row.id,
            group_id=row.group_id,
            user_id=row.user_id,
            user_type=row.user_type,
            banned_by=row.banned_by,
            reason=row.reason,
            banned_at=row.banned_at,
            expires_at=row.expires_at,
            is_active=bool(row.is_active),
            user_name=row.user_name,
            user_k_name=row.user_k_name,
            user_e_name=row.user_e_name
        )
        for row in results
    ]


# ==================== Group Settings ====================

@router.get("/groups/{group_id}/settings", response_model=GroupSettingsResponse)
async def get_group_settings(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get group settings."""
    # Check if user is a member
    membership = db.query(MessageGroupMember).filter(
        MessageGroupMember.group_id == group_id,
        MessageGroupMember.user_id == principal.id,
        MessageGroupMember.user_type.in_(principal.member_types)
    ).first()

    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    
    # Get settings
    settings = db.query(MessageGroupSettings).filter(
        MessageGroupSettings.group_id == group_id
    ).first()
    
    if not settings:
        # Create default settings if they don't exist
        settings = MessageGroupSettings(group_id=group_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return GroupSettingsResponse(
        id=settings.id,
        group_id=settings.group_id,
        can_send_text=bool(settings.can_send_text),
        can_send_files=bool(settings.can_send_files),
        can_send_images=bool(settings.can_send_images),
        can_send_voice=bool(settings.can_send_voice),
        only_admins_can_post=bool(settings.only_admins_can_post),
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )


@router.put("/groups/{group_id}/settings", response_model=GroupSettingsResponse)
async def update_group_settings(
    group_id: int,
    request: UpdateSettingsRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Update group settings. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get settings
    settings = db.query(MessageGroupSettings).filter(
        MessageGroupSettings.group_id == group_id
    ).first()
    
    if not settings:
        # Create settings if they don't exist
        settings = MessageGroupSettings(group_id=group_id)
        db.add(settings)
    
    # Update settings
    if request.can_send_text is not None:
        settings.can_send_text = int(request.can_send_text)
    if request.can_send_files is not None:
        settings.can_send_files = int(request.can_send_files)
    if request.can_send_images is not None:
        settings.can_send_images = int(request.can_send_images)
    if request.can_send_voice is not None:
        settings.can_send_voice = int(request.can_send_voice)
    if request.only_admins_can_post is not None:
        settings.only_admins_can_post = int(request.only_admins_can_post)
    
    db.commit()
    db.refresh(settings)

    await _broadcast_chat_moderation(
        group_id,
        {
            "type": "group_settings_updated",
            "group_id": group_id,
            "can_send_text": bool(settings.can_send_text),
            "can_send_files": bool(settings.can_send_files),
            "can_send_images": bool(settings.can_send_images),
            "can_send_voice": bool(settings.can_send_voice),
            "only_admins_can_post": bool(settings.only_admins_can_post),
        },
    )

    return GroupSettingsResponse(
        id=settings.id,
        group_id=settings.group_id,
        can_send_text=bool(settings.can_send_text),
        can_send_files=bool(settings.can_send_files),
        can_send_images=bool(settings.can_send_images),
        can_send_voice=bool(settings.can_send_voice),
        only_admins_can_post=bool(settings.only_admins_can_post),
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )


# ==================== Message Moderation ====================

def _normalize_message_type_for_media(raw) -> str:
    """Match ORM enum, raw strings, or legacy values to a lowercase type name."""
    if raw is None:
        return ""
    if isinstance(raw, MessageType):
        return str(raw.value).lower().strip()
    s = str(raw).strip().lower()
    if not s:
        return ""
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s


def _normalize_stored_media_content(content: str) -> str:
    """Ensure local upload paths work with StorageService (leading /uploads/...)."""
    c = (content or "").strip()
    if not c:
        return ""
    if c.startswith("uploads/"):
        return "/" + c
    return c


def _delete_stored_media_for_message(db: Session, message: GroupMessage, message_id: int) -> None:
    """
    Remove uploaded file from local disk or cloud when a message is deleted.
    Content for image/voice/file messages is the storage URL or /uploads/... path.
    """
    import logging
    import json

    mt = _normalize_message_type_for_media(getattr(message, "message_type", None))
    raw_content = getattr(message, "content", None) or ""

    if mt == "image_batch":
        try:
            data = json.loads(raw_content)
            if isinstance(data, list):
                for item in data:
                    url = _normalize_stored_media_content(str(item).strip())
                    if not url:
                        continue
                    if not (
                        url.startswith("http://")
                        or url.startswith("https://")
                        or url.startswith("/uploads/")
                    ):
                        continue
                    try:
                        from ...services.storage_service import StorageService
                        from ...models.settings import SystemSettings

                        settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
                        if settings:
                            StorageService.delete_file(url, settings)
                        elif url.startswith("/uploads/"):
                            StorageService.delete_local_file(url)
                    except Exception as e:
                        logging.getLogger(__name__).error(
                            "Error deleting batch image for message %s: %s", message_id, e
                        )
        except (json.JSONDecodeError, TypeError):
            pass
        return

    if mt not in ("image", "voice", "audio", "file"):
        return
    content = _normalize_stored_media_content(raw_content)
    if not content:
        return
    if not (
        content.startswith("http://")
        or content.startswith("https://")
        or content.startswith("/uploads/")
    ):
        return
    try:
        from ...services.storage_service import StorageService
        from ...models.settings import SystemSettings

        settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
        if settings:
            StorageService.delete_file(content, settings)
        elif content.startswith("/uploads/"):
            # Row may predate settings row, or voice was stored locally: still remove file.
            StorageService.delete_local_file(content)
    except Exception as e:
        logging.getLogger(__name__).error(
            "Error deleting stored media for message %s: %s", message_id, e
        )


@router.delete("/groups/{group_id}/messages/{message_id}")
async def delete_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Delete a message. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get message
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    latest = (
        db.query(GroupMessage)
        .filter(
            GroupMessage.group_id == group_id,
            GroupMessage.deleted_at.is_(None),
        )
        .order_by(GroupMessage.created_at.desc())
        .first()
    )
    was_last_visible = latest is not None and latest.id == message_id

    # Mark as deleted
    message.deleted_by = current_user_id
    message.deleted_at = datetime.utcnow()
    
    _delete_stored_media_for_message(db, message, message_id)

    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {"type": "message_deleted", "message_id": message_id},
    )

    if was_last_visible:
        try:
            from .messages import schedule_inbox_preview_broadcast_for_group

            schedule_inbox_preview_broadcast_for_group(db, group_id)
        except Exception:
            pass

    return {"message": "Message deleted successfully"}


@router.put("/groups/{group_id}/messages/{message_id}/hide")
async def hide_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Hide a message from all users. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get message
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Mark as hidden
    message.is_hidden = 1
    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {"type": "message_hidden", "message_id": message_id},
    )

    return {"message": "Message hidden successfully"}


@router.put("/groups/{group_id}/messages/{message_id}/unhide")
async def unhide_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Unhide a message. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get message
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Unhide
    message.is_hidden = 0
    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {"type": "message_unhidden", "message_id": message_id},
    )

    return {"message": "Message unhidden successfully"}


@router.put("/groups/{group_id}/messages/{message_id}/pin")
async def pin_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Pin a message to the top of the chat. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get message
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Pin the message
    message.pinned_by = current_user_id
    message.pinned_at = datetime.utcnow()
    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {
            "type": "message_pinned",
            "message_id": message_id,
            "pinned_by": current_user_id,
            "pinned_at": message.pinned_at.isoformat() if message.pinned_at else None,
        },
    )

    return {"message": "Message pinned successfully"}


@router.delete("/groups/{group_id}/messages/{message_id}/pin")
async def unpin_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Unpin a message. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get message
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Unpin the message
    message.pinned_by = None
    message.pinned_at = None
    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {"type": "message_unpinned", "message_id": message_id},
    )

    return {"message": "Message unpinned successfully"}


# ==================== Role Management ====================

@router.put("/groups/{group_id}/members/{member_id}/promote")
async def promote_to_admin(
    group_id: int,
    member_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Promote a member to admin. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get member
    member = db.query(MessageGroupMember).filter(
        MessageGroupMember.id == member_id,
        MessageGroupMember.group_id == group_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    if member.role == 'admin':
        raise HTTPException(status_code=400, detail="User is already an admin")
    
    # Promote to admin
    member.role = 'admin'
    db.commit()
    
    return {"message": "Member promoted to admin successfully"}


@router.put("/groups/{group_id}/members/{member_id}/demote")
async def demote_from_admin(
    group_id: int,
    member_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Demote an admin to regular member. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get member
    member = db.query(MessageGroupMember).filter(
        MessageGroupMember.id == member_id,
        MessageGroupMember.group_id == group_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    if member.role != 'admin':
        raise HTTPException(status_code=400, detail="User is not an admin")
    
    # Don't allow demoting self (same ID in a different table is a different person)
    if member.user_id == current_user_id and member.user_type in principal.member_types:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    
    # Demote to member
    member.role = 'member'
    db.commit()
    
    return {"message": "Admin demoted to member successfully"}
