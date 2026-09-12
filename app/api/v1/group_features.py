"""
Advanced Group Features API endpoints for pinned messages, reactions, and more.
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from ...core import get_db
from ...models import MessageGroup, MessageGroupMember, GroupMessage
from ...models.message import PinnedMessage, MessageReaction
from ...auth.dependencies import Principal, get_current_principal

router = APIRouter()


async def _broadcast_chat_moderation(group_id: int, payload: dict) -> None:
    try:
        from .messages import broadcast_group_ws
        await broadcast_group_ws(group_id, payload)
    except Exception:
        pass


# ==================== Schemas ====================

class PinMessageRequest(BaseModel):
    """Request schema for pinning a message."""
    message_id: int


class PinnedMessageResponse(BaseModel):
    """Response schema for pinned message."""
    id: int
    group_id: int
    message_id: int
    pinned_by: int
    pinned_at: datetime
    # Message details
    content: Optional[str] = None
    sender_name: Optional[str] = None


class AddReactionRequest(BaseModel):
    """Request schema for adding a reaction."""
    reaction: str  # Emoji or reaction code


class ReactionResponse(BaseModel):
    """Response schema for reaction."""
    id: int
    message_id: int
    user_id: int
    reaction: str
    created_at: datetime
    # User details
    user_name: Optional[str] = None


class UpdateGroupDescriptionRequest(BaseModel):
    """Request schema for updating group description."""
    description: str


# ==================== Helper Functions ====================

def _check_admin_permission(db: Session, group_id: int, principal: Principal):
    """Check if user is an admin of the group.

    The ID must be matched together with the table it came from — parents,
    students and employees each have their own ID sequence.
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


def _check_membership(db: Session, group_id: int, principal: Principal):
    """Check if user is a member of the group."""
    membership = db.query(MessageGroupMember).filter(
        MessageGroupMember.group_id == group_id,
        MessageGroupMember.user_id == principal.id,
        MessageGroupMember.user_type.in_(principal.member_types)
    ).first()

    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this group")
    return membership


# ==================== Pinned Messages ====================

@router.post("/groups/{group_id}/messages/{message_id}/pin", response_model=PinnedMessageResponse)
async def pin_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Pin a message in a group. Admin only. Idempotent: if already pinned, returns success."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Verify message exists and belongs to group
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    now = datetime.utcnow()
    existing = db.query(PinnedMessage).filter(
        PinnedMessage.group_id == group_id,
        PinnedMessage.message_id == message_id
    ).first()
    
    if existing:
        # Already pinned: keep idempotent, sync messages table and return success
        message.pinned_by = current_user_id
        message.pinned_at = now
        db.commit()
        db.refresh(message)
        await _broadcast_chat_moderation(
            group_id,
            {
                "type": "message_pinned",
                "message_id": message_id,
                "pinned_by": current_user_id,
                "pinned_at": message.pinned_at.isoformat() if message.pinned_at else None,
            },
        )
        return PinnedMessageResponse(
            id=existing.id,
            group_id=existing.group_id,
            message_id=existing.message_id,
            pinned_by=existing.pinned_by,
            pinned_at=existing.pinned_at,
            content=message.content,
            sender_name=None
        )
    
    # Pin message: add to PinnedMessage and sync messages table
    pinned = PinnedMessage(
        group_id=group_id,
        message_id=message_id,
        pinned_by=current_user_id
    )
    db.add(pinned)
    message.pinned_by = current_user_id
    message.pinned_at = now
    db.commit()
    db.refresh(pinned)
    db.refresh(message)

    await _broadcast_chat_moderation(
        group_id,
        {
            "type": "message_pinned",
            "message_id": message_id,
            "pinned_by": current_user_id,
            "pinned_at": message.pinned_at.isoformat() if message.pinned_at else None,
        },
    )

    return PinnedMessageResponse(
        id=pinned.id,
        group_id=pinned.group_id,
        message_id=pinned.message_id,
        pinned_by=pinned.pinned_by,
        pinned_at=pinned.pinned_at,
        content=message.content,
        sender_name=None  # Could add sender lookup
    )


@router.delete("/groups/{group_id}/messages/{message_id}/pin")
async def unpin_message(
    group_id: int,
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Unpin a message. Admin only. Clears both PinnedMessage and messages.pinned_* so re-pin works."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Find pinned message
    pinned = db.query(PinnedMessage).filter(
        PinnedMessage.group_id == group_id,
        PinnedMessage.message_id == message_id
    ).first()
    
    if pinned:
        db.delete(pinned)
    
    # Always clear pin state on the message so list view and re-pin work
    message = db.query(GroupMessage).filter(
        GroupMessage.id == message_id,
        GroupMessage.group_id == group_id
    ).first()
    if message:
        message.pinned_by = None
        message.pinned_at = None

    db.commit()

    await _broadcast_chat_moderation(
        group_id,
        {"type": "message_unpinned", "message_id": message_id},
    )

    return {"message": "Message unpinned successfully"}


@router.get("/groups/{group_id}/pinned", response_model=List[PinnedMessageResponse])
async def get_pinned_messages(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get all pinned messages in a group."""
    # Check membership
    current_user_id = principal.id
    _check_membership(db, group_id, principal)
    
    # Get pinned messages with message content
    query = text("""
        SELECT 
            p.id, p.group_id, p.message_id, p.pinned_by, p.pinned_at,
            m.content, u.username as sender_name
        FROM message_pinned p
        INNER JOIN messages m ON p.message_id = m.id
        LEFT JOIN users u ON m.sender_id = u.id
        WHERE p.group_id = :group_id
        ORDER BY p.pinned_at DESC
    """)
    
    results = db.execute(query, {"group_id": group_id}).fetchall()
    
    return [
        PinnedMessageResponse(
            id=row.id,
            group_id=row.group_id,
            message_id=row.message_id,
            pinned_by=row.pinned_by,
            pinned_at=row.pinned_at,
            content=row.content,
            sender_name=row.sender_name
        )
        for row in results
    ]


# ==================== Message Reactions ====================

@router.post("/messages/{message_id}/reactions", response_model=ReactionResponse)
async def add_reaction(
    message_id: int,
    request: AddReactionRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Add a reaction to a message."""
    # Verify message exists
    message = db.query(GroupMessage).filter(GroupMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check membership
    current_user_id = principal.id
    _check_membership(db, message.group_id, principal)
    
    # Check if user already reacted with this emoji
    existing = db.query(MessageReaction).filter(
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == current_user_id,
        MessageReaction.user_type.in_(principal.member_types),
        MessageReaction.reaction == request.reaction
    ).first()
    
    if existing:
        # Remove reaction (toggle)
        db.delete(existing)
        db.commit()
        return {"message": "Reaction removed", "id": existing.id}
    
    # Add reaction
    reaction = MessageReaction(
        message_id=message_id,
        user_id=current_user_id,
        user_type=principal.kind,
        reaction=request.reaction
    )
    db.add(reaction)
    db.commit()
    db.refresh(reaction)
    
    # Get user name from the table this ID actually belongs to
    if principal.kind == "parent":
        query = text("SELECT p.username as user_name FROM parents p WHERE p.id = :user_id")
    else:
        query = text("SELECT u.username as user_name FROM users u WHERE u.id = :user_id")
    user_result = db.execute(query, {"user_id": current_user_id}).fetchone()
    
    return ReactionResponse(
        id=reaction.id,
        message_id=reaction.message_id,
        user_id=reaction.user_id,
        reaction=reaction.reaction,
        created_at=reaction.created_at,
        user_name=user_result.user_name if user_result else None
    )


@router.get("/messages/{message_id}/reactions", response_model=List[ReactionResponse])
async def get_message_reactions(
    message_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get all reactions for a message."""
    # Verify message exists
    message = db.query(GroupMessage).filter(GroupMessage.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check membership
    current_user_id = principal.id
    _check_membership(db, message.group_id, principal)
    
    # Get reactions with user details
    query = text("""
        SELECT 
            r.id, r.message_id, r.user_id, r.reaction, r.created_at,
            u.username as user_name
        FROM message_reactions r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.message_id = :message_id
        ORDER BY r.created_at ASC
    """)
    
    results = db.execute(query, {"message_id": message_id}).fetchall()
    
    return [
        ReactionResponse(
            id=row.id,
            message_id=row.message_id,
            user_id=row.user_id,
            reaction=row.reaction,
            created_at=row.created_at,
            user_name=row.user_name
        )
        for row in results
    ]


@router.delete("/messages/{message_id}/reactions/{reaction_id}")
async def remove_reaction(
    message_id: int,
    reaction_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Remove a reaction from a message."""
    current_user_id = principal.id
    # Get reaction
    reaction = db.query(MessageReaction).filter(
        MessageReaction.id == reaction_id,
        MessageReaction.message_id == message_id
    ).first()

    if not reaction:
        raise HTTPException(status_code=404, detail="Reaction not found")

    # Only the user who added the reaction can remove it. The ID alone is
    # ambiguous across tables, so the owning table has to match too.
    if (
        reaction.user_id != current_user_id
        or reaction.user_type not in principal.member_types
    ):
        raise HTTPException(status_code=403, detail="You can only remove your own reactions")
    
    db.delete(reaction)
    db.commit()
    
    return {"message": "Reaction removed successfully"}


# ==================== Group Description ====================

@router.put("/groups/{group_id}/description")
async def update_group_description(
    group_id: int,
    request: UpdateGroupDescriptionRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Update group description. Admin only."""
    # Check admin permission
    current_user_id = principal.id
    _check_admin_permission(db, group_id, principal)
    
    # Get group
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Update description
    group.description = request.description
    db.commit()
    
    return {"message": "Group description updated successfully"}


@router.get("/groups/{group_id}/description")
async def get_group_description(
    group_id: int,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db)
):
    """Get group description."""
    # Check membership
    current_user_id = principal.id
    _check_membership(db, group_id, principal)
    
    # Get group
    group = db.query(MessageGroup).filter(MessageGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return {"description": group.description or ""}
