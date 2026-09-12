from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class SchoolEventBase(BaseModel):
    title: str
    title_kh: Optional[str] = None
    event_date: date
    event_type: str = "event"        # 'event' or 'competition'
    round: Optional[str] = None      # '1st Round', 'Final', None
    participant_group: Optional[str] = None
    time_of_day: Optional[str] = None
    academic_year: Optional[str] = None
    description: Optional[str] = None
    color_code: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: bool = True


class SchoolEventCreate(SchoolEventBase):
    pass


class SchoolEventUpdate(BaseModel):
    title: Optional[str] = None
    title_kh: Optional[str] = None
    event_date: Optional[date] = None
    event_type: Optional[str] = None
    round: Optional[str] = None
    participant_group: Optional[str] = None
    time_of_day: Optional[str] = None
    academic_year: Optional[str] = None
    description: Optional[str] = None
    color_code: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None


class SchoolEventResponse(SchoolEventBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
