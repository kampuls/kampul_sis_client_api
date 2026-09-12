from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func
from .base import Base

class AttendanceAllowedBranch(Base):
    __tablename__ = "attendance__allowed_branches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
