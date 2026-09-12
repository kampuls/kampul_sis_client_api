from datetime import datetime, date
from sqlalchemy import Boolean, Column, Integer, String, Text, Date, DateTime
from sqlalchemy.sql import func

from .base import Base


class SchoolEvent(Base):
    __tablename__ = "school_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    title_kh = Column(String(255), nullable=True)    # Khmer title
    event_date = Column(Date, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, default="event")  # 'event' or 'competition'
    round = Column(String(50), nullable=True)         # '1st Round', 'Final', or null
    participant_group = Column(String(150), nullable=True)  # 'UNP (G4-G10)', 'All', etc.
    time_of_day = Column(String(100), nullable=True)  # 'Afternoon 1hour', 'Morning & Afternoon'
    academic_year = Column(String(20), nullable=True, index=True)  # '2025-2026'
    description = Column(Text, nullable=True)
    color_code = Column(String(50), nullable=True)    # Optional row color for UI
    branch_id = Column(Integer, nullable=True)        # Optional branch filter
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
