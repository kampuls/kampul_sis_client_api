from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Time
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Department(Base):
    """Department model for organizational structure"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    department = Column(String(100), nullable=False)
    translate = Column(String(100), nullable=True)
    code = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Branch(Base):
    __tablename__ = "branch"
    
    id = Column(Integer, primary_key=True, index=True)
    branch_name = Column(String(100), unique=True, index=True, nullable=False)
    app_display_name = Column(String(150), nullable=True)
    address_english = Column(String(255), nullable=True)
    app_branch_cover = Column(String(255), nullable=True)
    app_branch_facebook_url = Column(String(255), nullable=True)
    app_branch_telegram_url = Column(String(255), nullable=True)
    app_branch_youtube_url = Column(String(255), nullable=True)
    app_branch_tiktok_url = Column(String(255), nullable=True)
    app_branch_google_map_url = Column(String(255), nullable=True)
    map_latitude = Column(DOUBLE(asdecimal=False), nullable=True)
    map_longitude = Column(DOUBLE(asdecimal=False), nullable=True)
    pickup_radius_meters = Column(DOUBLE(asdecimal=False), nullable=True)
    open_at = Column(Time, nullable=True)
    close_at = Column(Time, nullable=True)

    # URL/path resources managed by StorageService.
    image_header = Column(String(1000), nullable=True)
    director_signature = Column(String(1000), nullable=True)
    headTeacher_signature = Column(String(1000), nullable=True)
    stamp = Column(String(1000), nullable=True)

    # New Path fields mapping to uploads/branches/
    image_header_path = Column(String(255), nullable=True)
    director_signature_path = Column(String(255), nullable=True)
    headTeacher_signature_path = Column(String(255), nullable=True)
    stamp_path = Column(String(255), nullable=True)

    # URL fields for Flutter certificate generation
    # These store full uploaded image URLs via the API (Migration 37).
    # Used by Flutter, the PDF service, and desktop certificate rendering.
    signature_url = Column(String(500), nullable=True)
    stamp_url     = Column(String(500), nullable=True)

    # Names for the signees
    director_kName = Column(String(255), nullable=True)
    director_eName = Column(String(255), nullable=True)
    headTeacher_kName = Column(String(255), nullable=True)
    headTeacher_eName = Column(String(255), nullable=True)

    contacts = relationship(
        "BranchContact",
        back_populates="branch",
        cascade="all, delete-orphan",
        lazy="joined",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships removed - database doesn't have foreign key constraints
    # If needed, query users manually: db.query(User).filter(User.workplace == branch.id).all()

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Position(Base):
    """Position model for staff and teacher titles"""
    __tablename__ = "position"

    id = Column(Integer, primary_key=True, index=True)
    position = Column(String(100), nullable=True)
    translate = Column(String(100), nullable=True)
    code = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class BranchContact(Base):
    __tablename__ = "branch_contacts"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(
        Integer,
        ForeignKey("branch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(100), nullable=True)  # e.g. "Admissions", "Office"
    value = Column(String(255), nullable=False)  # actual number/text
    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    branch = relationship("Branch", back_populates="contacts")
