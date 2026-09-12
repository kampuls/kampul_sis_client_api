"""
Parent Permission Interaction model for tracking daily permission interactions server-side.
This prevents clients from bypassing restrictions by switching devices.
"""

from sqlalchemy import Column, Integer, Date, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ParentPermissionInteraction(Base):
    __tablename__ = "parent_permission_interactions"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, nullable=False, index=True)  # Removed FK to avoid mapper issues
    student_id = Column(Integer, nullable=False, index=True) # Removed FK to avoid mapper issues
    learning_id = Column(Integer, nullable=False, index=True)
    interaction_date = Column(Date, nullable=False, index=True)
    interaction_type = Column(Enum('requested', 'cancelled', name='interaction_type'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships removed to avoid mapper configuration issues
    # Using raw SQL queries instead for data integrity

    def __repr__(self):
        return f"<ParentPermissionInteraction(parent_id={self.parent_id}, student_id={self.student_id}, learning_id={self.learning_id}, interaction_type={self.interaction_type})>"
