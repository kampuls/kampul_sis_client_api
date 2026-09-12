from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class Partner(Base):
    """Partners shown on the PAMA home screen (e.g. Cambridge, Microsoft)."""

    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    short_name = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)  # e.g. curriculum, technology, community
    description = Column(Text, nullable=True)

    # Visual identity
    logo_url = Column(String(255), nullable=True)
    icon_name = Column(String(100), nullable=True)  # Optional Material icon name for mobile

    # Relationships
    images = relationship("PartnerImage", back_populates="partner", cascade="all, delete-orphan")

    # Links / contact
    website_url = Column(String(255), nullable=True)
    contact_email = Column(String(120), nullable=True)
    contact_phone = Column(String(50), nullable=True)

    # Optional branch scoping (if a partner is specific to one campus)
    branch_id = Column(
        Integer,
        ForeignKey("branch.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Ordering & status
    sort_order = Column(Integer, nullable=True, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PartnerImage(Base):
    """Multiple images for a partner."""

    __tablename__ = "partner_images"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    partner = relationship("Partner", back_populates="images")

