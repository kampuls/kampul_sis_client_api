from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
from datetime import date as dt_date

class AskPermissionRequest(BaseModel):
    student_id: int
    learning_id: int = Field(..., description="ID from the learning table to identify the class")
    dates: List[dt_date] = Field(..., description="List of dates to request permission for (max 7 days)")
    reason: str = Field(..., min_length=1, description="Reason for the permission request")

    model_config = ConfigDict(from_attributes=True)

class PermissionSelection(BaseModel):
    student_id: int
    learning_id: int

class AskPermissionBatchRequest(BaseModel):
    selections: List[PermissionSelection] = Field(..., description="List of student/class combinations")
    dates: List[dt_date] = Field(..., description="List of dates to request permission for (max 7 days)")
    reason: str = Field(..., min_length=1, description="Reason for the permission request")

    model_config = ConfigDict(from_attributes=True)

class CancelPermissionRequest(BaseModel):
    attendance_ids: List[int] = Field(..., description="List of daily_attendance IDs to cancel")

    model_config = ConfigDict(from_attributes=True)

class CheckAttendanceStatusRequest(BaseModel):
    student_id: int = Field(..., description="Student ID to check attendance for")
    attendance_date: dt_date = Field(..., description="Date to check attendance for (YYYY-MM-DD)")

    model_config = ConfigDict(from_attributes=True)

class CancelPermissionResponse(BaseModel):
    success: bool
    message: str
    cancelled_count: int

class AskPermissionResponse(BaseModel):
    success: bool
    message: str
    created_count: int

class AttendanceSummaryResponse(BaseModel):
    present: int
    absent: int
    permission: int
    late: int
    not_marked: int = 0
    total_records: int = 0
    attendance_percentage: float = 0.0

class UpdateMyChildRequest(BaseModel):
    """Fields a parent is allowed to update for their child. All optional (partial update)."""
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, max_length=255)
    kName: Optional[str] = Field(None, max_length=100)
    eName: Optional[str] = Field(None, max_length=100)
    gender: Optional[str] = Field(None, max_length=100)
    dob: Optional[dt_date] = Field(None)
    is_foreigner: Optional[int] = Field(None, description="1 for local, 2 for foreigner")
    student_phone: Optional[str] = Field(None, max_length=50)
    province: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    commune: Optional[str] = Field(None, max_length=100)
    village: Optional[str] = Field(None, max_length=100)
    previousSchool: Optional[str] = Field(None, max_length=100)
    student_noted: Optional[str] = Field(None)
    # Admin-only — ignored for non-admin requests in the endpoint
    branch: Optional[str] = Field(None, max_length=50, description="Branch ID (admin only)")

    model_config = ConfigDict(from_attributes=True)



class StudentAttendanceSummaryRequest(BaseModel):
    student_id: int = Field(..., description="Student ID to fetch stats for")
    date: Optional[dt_date] = Field(None, description="Specific date (optional)")
    start_date: Optional[dt_date] = Field(None, description="Start date for custom range (optional)")
    end_date: Optional[dt_date] = Field(None, description="End date for custom range (optional)")
    month: Optional[int] = Field(None, description="Month (1-12) (optional)")
    year: Optional[int] = Field(None, description="Year (YYYY) (optional)")
    program_id: Optional[int] = Field(None, description="Filter by program ID")
    grade_id: Optional[int] = Field(None, description="Filter by grade ID")
    grade_type_id: Optional[int] = Field(None, description="Filter by grade type ID")
    grade_type_id_is_null: Optional[bool] = Field(
        None, description="When True, filter for grade_type_id IS NULL (class has no grade type)"
    )
    shift_id: Optional[int] = Field(None, description="Filter by shift ID")
    academic_id: Optional[int] = Field(None, description="Filter by academic ID")

    model_config = ConfigDict(from_attributes=True)


class DailyAttendanceRecord(BaseModel):
    """Single daily attendance record for calendar/detail view."""
    id: int
    attendance_date: str  # YYYY-MM-DD
    status: str
    note: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    marked_by: Optional[str] = None  # teacher name or created_by_type
    created_by_type: Optional[str] = None


class StudentAttendanceDailyResponse(BaseModel):
    """Daily attendance records for a student in a date range (for calendar + details)."""
    records: List[DailyAttendanceRecord] = []


class ParentRegisterResponse(BaseModel):
    """Returned after parent self-registration (includes token while pending approval)."""

    access_token: Optional[str] = None
    token_type: str = "bearer"
    username: str
    parent_id: Optional[int] = None
    pending_approval: bool = True
    password: Optional[str] = Field(
        None,
        description="Plain password only when the server generated it (user skipped choosing one).",
    )


class LinkedStudentSummary(BaseModel):
    id: int
    kName: Optional[str] = None
    eName: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    status: Optional[int] = None
    studentPhone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminPendingParentRegistrationItem(BaseModel):
    id: int
    username: Optional[str] = None
    fatherName: Optional[str] = None
    motherName: Optional[str] = None
    gName: Optional[str] = None
    fatherPhone: Optional[str] = None
    motherPhone: Optional[str] = None
    gPhone: Optional[str] = None
    fatherJob: Optional[str] = None
    motherJob: Optional[str] = None
    pEmail: Optional[str] = None
    pTelegramId: Optional[str] = None
    pProvince: Optional[str] = None
    pDistrict: Optional[str] = None
    pCommune: Optional[str] = None
    pVillage: Optional[str] = None
    myChilds: Optional[str] = None
    children_count: int = 0
    students: List[LinkedStudentSummary] = []
    status: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    avatar: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdminParentRegistrationHistoryItem(BaseModel):
    id: int
    parent_id: int
    action: str
    admin_user_id: Optional[int] = None
    admin_display: Optional[str] = None
    display_name: str
    username: Optional[str] = None
    students_count: int = 0
    students: List[LinkedStudentSummary] = []
    fatherPhone: Optional[str] = None
    motherPhone: Optional[str] = None
    gPhone: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class AdminParentRegistrationAction(BaseModel):
    action: str = Field(..., description="Action: 'approve' or 'reject'")

    model_config = ConfigDict(from_attributes=True)


class ParentCreate(BaseModel):
    """Schema for parent registration.
    
    All name/phone fields are Optional because the required fields depend on parentRole:
    - father: fatherName + fatherPhone required (motherName may be empty)
    - mother: motherName required (fatherPhone may be empty)  
    - guardian: gName + gPhone required (father/mother fields may be empty)
    The Flutter app sends empty strings for unused roles; the validator converts them to None.
    """
    username: Optional[str] = Field(None, max_length=25)
    password: Optional[str] = Field(None, max_length=100)
    fatherName: Optional[str] = Field(None, max_length=100)
    motherName: Optional[str] = Field(None, max_length=100)
    fatherPhone: Optional[str] = Field(None, max_length=100)
    motherPhone: Optional[str] = Field(None, max_length=100)
    fatherJob: Optional[str] = Field(None, max_length=100)
    motherJob: Optional[str] = Field(None, max_length=100)
    pProvince: Optional[str] = Field(None, max_length=100)
    pDistrict: Optional[str] = Field(None, max_length=100)
    pCommune: Optional[str] = Field(None, max_length=100)
    pVillage: Optional[str] = Field(None, max_length=100)
    pEmail: Optional[str] = Field(None, max_length=100)
    pTelegramId: Optional[str] = Field(None, max_length=50)
    parentRole: str = Field("father", max_length=20)  # father, mother, guardian

    # Guardian Info
    gName: Optional[str] = Field(None, max_length=255)
    gPhone: Optional[str] = Field(None, max_length=50)
    gIsThe: Optional[str] = Field(None, max_length=100)
    gHome: Optional[str] = Field(None, max_length=100)
    gStreet: Optional[str] = Field(None, max_length=100)
    gGroup: Optional[str] = Field(None, max_length=100)
    gProvince: Optional[str] = Field(None, max_length=100)
    gDistrict: Optional[str] = Field(None, max_length=100)
    gCommune: Optional[str] = Field(None, max_length=100)
    gVillage: Optional[str] = Field(None, max_length=100)

    myChilds: Optional[str] = Field(None, max_length=255)
    image: Optional[str] = Field(None, description="Base64 encoded image for profile")

    @field_validator(
        "username", "password", "fatherName", "motherName",
        "fatherPhone", "motherPhone", "fatherJob", "motherJob",
        "pProvince", "pDistrict", "pCommune", "pVillage", "pEmail", "pTelegramId",
        "gName", "gPhone", "gIsThe", "gHome", "gStreet", "gGroup",
        "gProvince", "gDistrict", "gCommune", "gVillage", "myChilds",
        mode="before"
    )
    @classmethod
    def empty_str_to_none(cls, v):
        """Convert empty/whitespace strings to None for all optional string fields."""
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    model_config = ConfigDict(from_attributes=True)


class LinkChildRequest(BaseModel):
    """Schema for a parent requesting to link an existing child to their account."""
    student_id: str = Field(..., description="ID of the student to link (can be string format like PAMA-082221)")

    model_config = ConfigDict(from_attributes=True)


class LinkChildResponse(BaseModel):
    success: bool
    message: str

class PendingLinkRequestItem(BaseModel):
    id: int
    student_id: int
    student_string_id: Optional[str] = None
    kName: Optional[str] = None
    eName: Optional[str] = None
    program_name: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class AdminPendingLinkRequestItem(PendingLinkRequestItem):
    parent_id: int
    parent_name: Optional[str] = None
    parent_phone: Optional[str] = None

class AdminProcessLinkRequest(BaseModel):
    action: str = Field(..., description="Action to perform: 'approve' or 'reject'")
    
    model_config = ConfigDict(from_attributes=True)
