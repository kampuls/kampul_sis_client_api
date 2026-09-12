from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class AppAdmin(Base):
    __tablename__ = 'app_admins'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    is_super_admin = Column(Boolean, default=False, nullable=False)
    can_reset_attendance_devices = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    
    # Relationship to user (specify foreign_keys to avoid ambiguity)
    user = relationship('User', foreign_keys=[user_id], backref='app_admin_profile', lazy='joined')
    locker = relationship('User', foreign_keys=[locked_by], lazy='joined')
