"""
Schemas for Attendance API endpoints.
"""
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List, Union
from datetime import date, datetime, time, timedelta


# Branch Request Schemas
class BranchBase(BaseModel):
    branch_name: str
    app_display_name: Optional[str] = None
    app_branch_cover: Optional[str] = None
    app_branch_facebook_url: Optional[str] = None
    app_branch_telegram_url: Optional[str] = None
    app_branch_youtube_url: Optional[str] = None
    app_branch_tiktok_url: Optional[str] = None
    app_branch_google_map_url: Optional[str] = None
    map_latitude: Optional[float] = None
    map_longitude: Optional[float] = None
    pickup_radius_meters: Optional[float] = None
    open_at: Optional[time] = None
    close_at: Optional[time] = None

class BranchCreate(BranchBase):
    director_kName: Optional[str] = None
    director_eName: Optional[str] = None

class BranchUpdate(BranchBase):
    branch_name: Optional[str] = None
    director_kName: Optional[str] = None
    director_eName: Optional[str] = None


# Response Schemas
class BranchContactResponse(BaseModel):
    id: int
    label: Optional[str] = None
    value: str
    sort_order: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class BranchResponse(BaseModel):
    id: int
    branch_name: str
    app_display_name: Optional[str] = None
    app_branch_cover: Optional[str] = None
    app_branch_facebook_url: Optional[str] = None
    app_branch_telegram_url: Optional[str] = None
    app_branch_youtube_url: Optional[str] = None
    app_branch_tiktok_url: Optional[str] = None
    app_branch_google_map_url: Optional[str] = None
    map_latitude: Optional[float] = None
    map_longitude: Optional[float] = None
    pickup_radius_meters: Optional[float] = None
    open_at: Optional[time] = None
    close_at: Optional[time] = None

    # Certificate / PDF layout fields
    image_header_path: Optional[str] = None
    director_signature_path: Optional[str] = None
    headTeacher_signature_path: Optional[str] = None
    stamp_path: Optional[str] = None
    director_kName: Optional[str] = None
    director_eName: Optional[str] = None
    headTeacher_kName: Optional[str] = None
    headTeacher_eName: Optional[str] = None

    # URL-based signature & stamp (Migration 37)
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None

    contacts: Optional[List[BranchContactResponse]] = None

    @field_validator("open_at", "close_at", mode="before")
    @classmethod
    def convert_timedelta_to_time(cls, v):
        if isinstance(v, timedelta):
            total_seconds = int(v.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return time(hour=hours % 24, minute=minutes, second=seconds)
        return v

    model_config = ConfigDict(from_attributes=True)


class ProgramResponse(BaseModel):
    id: int
    program_name: str

    model_config = ConfigDict(from_attributes=True)


class GradeResponse(BaseModel):
    id: int
    grade_name: str
    grade_type_id: Union[int, str, None] = None
    grade_type_name: Optional[str] = None
    grade_group_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class GradeTypeResponse(BaseModel):
    id: int
    type_name: str

    model_config = ConfigDict(from_attributes=True)


class ShiftResponse(BaseModel):
    id: int
    shift_name: str
    shift_name_en: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ParentInfoResponse(BaseModel):
    id: int
    pTelegramId: Optional[str] = None
    myChilds: Optional[str] = None
    fatherName: Optional[str] = None
    motherName: Optional[str] = None
    fatherPhone: Optional[str] = None
    motherPhone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class StudentAttendanceResponse(BaseModel):
    id: int
    kName: str
    eName: str
    gender: str
    dob: Optional[date] = None
    academicid: int
    avatar: Optional[str] = None
    attendance_status: Optional[str] = None
    attendance_note: Optional[str] = None
    parent_info: Optional[ParentInfoResponse] = None

    model_config = ConfigDict(from_attributes=True)


class ClassInfoResponse(BaseModel):
    branch_id: int
    branch_name: str
    program_id: int
    program_name: str
    program_name_us: Optional[str] = None
    program_short_code: Optional[str] = None
    grade_id: int
    grade_name: str
    grade_name_us: Optional[str] = None
    grade_group_id: Optional[int] = None
    grade_type_id: Optional[int] = None
    grade_type_name: Optional[str] = None
    shift_id: int
    shift_name: str
    shift_name_en: Optional[str] = None
    student_count: int
    male_count: int
    female_count: int
    teacher_id: Optional[int] = None
    teacher_name: Optional[str] = None
    teacher_kname: Optional[str] = None
    teacher_ename: Optional[str] = None
    teacher_avatar: Optional[str] = None
    academic_id: int
    academic_name: Optional[str] = None
    academic_us_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Request Schemas
class RecordAttendanceRequest(BaseModel):
    student_id: int
    attendance_date: date
    status: Optional[str] = None
    academic_id: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    shift_id: int
    note: Optional[str] = None
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        if v not in ['IsPresent', 'IsLate', 'IsPermission', 'IsAbsent']:
            raise ValueError('status must be one of: IsPresent, IsLate, IsPermission, IsAbsent')
        return v


class RecordAttendanceResponse(BaseModel):
    success: bool
    message: str


class MonthlyAttendanceCounts(BaseModel):
    student_id: str  # Changed to str to support studentid format like 'PAMA-1681009'
    kName: str
    eName: str
    gender: str = ""
    present_count: int = 0
    absent_count: int = 0
    late_count: int = 0
    permission_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class MonthlyAttendanceResponse(BaseModel):
    month: int
    year: int
    total_students: int
    total_present: int
    total_absent: int
    total_late: int
    total_permission: int
    students: List[MonthlyAttendanceCounts]

    model_config = ConfigDict(from_attributes=True)

