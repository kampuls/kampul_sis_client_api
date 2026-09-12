"""
Message models for group messaging system.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, TypeDecorator
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from .base import Base


def _enum_from_name_or_value(enum_cls, value):
    """Convert DB string to enum: accept both name (TEACHER) and value (teacher)."""
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    s = (value or "").strip()
    if not s:
        return None
    try:
        return enum_cls(s.lower())  # by value
    except ValueError:
        pass
    try:
        return enum_cls[s.upper()]  # by name
    except KeyError:
        raise LookupError(f"{s!r} is not a valid {enum_cls.__name__}")


class GroupType(str, enum.Enum):
    """Enum for message group types."""
    CLASS = "class"
    CUSTOM = "custom"


# Accept both DB formats: names (CLASS) and values (class)
class GroupTypeColumn(TypeDecorator):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, GroupType):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return _enum_from_name_or_value(GroupType, value)


class MemberRole(str, enum.Enum):
    """Enum for group member roles."""
    ADMIN = "admin"
    MEMBER = "member"


# Accept both DB formats: names (ADMIN) and values (admin)
class MemberRoleColumn(TypeDecorator):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, MemberRole):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return _enum_from_name_or_value(MemberRole, value)


class UserType(str, enum.Enum):
    """Enum for user type in message group members."""
    TEACHER = "teacher"
    PARENT = "parent"
    STUDENT = "student"
    EMPLOYEE = "employee"


# Accept both DB formats: names (TEACHER) and values (teacher)
class UserTypeColumn(TypeDecorator):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, UserType):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return _enum_from_name_or_value(UserType, value)


class MessageType(str, enum.Enum):
    """Enum for message types."""
    TEXT = "text"
    ANNOUNCEMENT = "announcement"
    FILE = "file"
    IMAGE = "image"
    IMAGE_BATCH = "image_batch"
    VOICE = "voice"


# Accept both DB formats: names (TEXT) and values (text)
class MessageTypeColumn(TypeDecorator):
    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, MessageType):
            return value.value
        return value

    def process_result_value(self, value, dialect):
        return _enum_from_name_or_value(MessageType, value)


class MessageGroup(Base):
    """Message group model for class and custom groups."""
    
    __tablename__ = "message_groups"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    type = Column(GroupTypeColumn(), nullable=False, default=GroupType.CLASS)
    academic_year_id = Column(Integer, nullable=True)  # Link to academic year
    grade_id = Column(Integer, nullable=True)  # Link to grade (nullable for custom groups)
    grade_type_id = Column(Integer, nullable=True)  # Link to grade type
    program_id = Column(Integer, nullable=True)  # Link to program
    branch_id = Column(Integer, nullable=True)  # Link to branch
    description = Column(Text, nullable=True)
    group_image = Column(String(255), nullable=True)  # Group cover photo
    created_by = Column(Integer, nullable=False)  # User ID who created the group
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    def __repr__(self):
        return f"<MessageGroup(id={self.id}, name='{self.name}', type='{self.type}')>"


class MessageGroupMember(Base):
    """Message group member model for tracking group membership."""
    
    __tablename__ = "message_group_members"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('message_groups.id'), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)  # References users, parents, or students table
    user_type = Column(UserTypeColumn(), nullable=False, default=UserType.TEACHER)  # Specifies which table
    role = Column(MemberRoleColumn(), nullable=False, default=MemberRole.MEMBER)
    joined_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<MessageGroupMember(id={self.id}, group_id={self.group_id}, user_id={self.user_id}, role='{self.role}')>"


class GroupMessage(Base):
    """Message model for storing group messages."""
    
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('message_groups.id'), nullable=False, index=True)
    sender_id = Column(Integer, nullable=False, index=True)  # User ID of sender
    content = Column(Text, nullable=False)
    message_type = Column(MessageTypeColumn(), nullable=False, default=MessageType.TEXT)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    # For read receipts: storing as JSON array of user IDs who have read the message
    # Alternative: create separate read_receipts table for better normalization
    read_by = Column(Text, nullable=True, default='[]')  # JSON array string
    
    # Moderation fields
    deleted_by = Column(Integer, nullable=True)  # Admin who deleted the message
    deleted_at = Column(DateTime, nullable=True)
    is_hidden = Column(Integer, nullable=False, server_default='0')  # Boolean as INT
    
    # Pin fields
    pinned_by = Column(Integer, nullable=True)  # Admin who pinned the message
    pinned_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Message(id={self.id}, group_id={self.group_id}, sender_id={self.sender_id})>"


class MessageGroupBan(Base):
    """Ban model for temporarily or permanently banning users from groups."""
    
    __tablename__ = "message_group_bans"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('message_groups.id'), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    user_type = Column(UserTypeColumn(), nullable=False)
    banned_by = Column(Integer, nullable=False)
    reason = Column(String(500), nullable=True)
    banned_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)  # NULL means permanent ban
    is_active = Column(Integer, nullable=False, server_default='1')  # Can be manually deactivated
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<MessageGroupBan(id={self.id}, group_id={self.group_id}, user_id={self.user_id})>"


class MessageGroupSettings(Base):
    """Settings model for controlling group permissions and behavior."""
    
    __tablename__ = "message_group_settings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('message_groups.id'), nullable=False, unique=True)
    can_send_text = Column(Integer, nullable=False, server_default='1')  # Boolean as INT
    can_send_files = Column(Integer, nullable=False, server_default='1')
    can_send_images = Column(Integer, nullable=False, server_default='1')
    can_send_voice = Column(Integer, nullable=False, server_default='1')
    only_admins_can_post = Column(Integer, nullable=False, server_default='0')
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<MessageGroupSettings(id={self.id}, group_id={self.group_id})>"


class PinnedMessage(Base):
    """Model for pinned messages in groups."""
    
    __tablename__ = "message_pinned"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey('message_groups.id'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    pinned_by = Column(Integer, nullable=False)
    pinned_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<PinnedMessage(id={self.id}, group_id={self.group_id}, message_id={self.message_id})>"


class MessageReaction(Base):
    """Model for message reactions (emoji reactions)."""
    
    __tablename__ = "message_reactions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    # Which table user_id points at. Parents, students and employees have
    # independent ID sequences, so the integer alone names three people.
    user_type = Column(UserTypeColumn(), nullable=False, default=UserType.TEACHER)
    reaction = Column(String(10), nullable=False)  # Emoji or reaction code
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<MessageReaction(id={self.id}, message_id={self.message_id}, reaction={self.reaction})>"
