from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class FeatureLock(Base):
    __tablename__ = 'feature_locks'
    
    id = Column(Integer, primary_key=True, index=True)
    feature_id = Column(String(100), unique=True, nullable=False, index=True)
    feature_name = Column(String(200), nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False, index=True)
    locked_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    
    # Relationship to user who locked
    locker = relationship('User', foreign_keys=[locked_by], lazy='joined')
    
    __table_args__ = (
        Index('ix_feature_locks_feature_id', 'feature_id'),
        Index('ix_feature_locks_is_locked', 'is_locked'),
    )
