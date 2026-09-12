from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, func
from .base import Base

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    user_type = Column(String(50), index=True)  # 'teacher', 'parent', 'student'
    title = Column(String(255))
    body = Column(Text)
    data = Column(Text, nullable=True)  # JSON string
    is_read = Column(Boolean, default=False)
    is_deletable = Column(Boolean, default=True)
    redirect_route = Column(String(100), nullable=True)
    redirect_args = Column(Text, nullable=True)  # JSON string
    
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
