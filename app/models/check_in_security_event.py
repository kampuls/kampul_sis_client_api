"""Persisted check-in / API security observations (rate limits, IP patterns)."""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import relationship

from .base import Base


class CheckInSecurityEvent(Base):
    __tablename__ = "check_in_security_events"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    client_ip = Column(String(64), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="info", index=True)
    message = Column(Text, nullable=False)
    detail_json = Column(Text, nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
