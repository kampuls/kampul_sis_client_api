from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum

class TargetRole(str, Enum):
    ALL = "all"
    PARENTS = "parents"
    STUDENTS = "students"
    TEACHERS = "teachers"

class FieldType(str, Enum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    CHECKBOXES = "checkboxes"
    RADIO = "radio"
    DATE = "date"
    TIME = "time"
    CHILD_SELECTOR = "child_selector"
    IMAGE = "image"
    FILE = "file"

# Options
class FormFieldOptionBase(BaseModel):
    label: str
    value: str
    order: int

class FormFieldOptionCreate(FormFieldOptionBase):
    pass

class FormFieldOptionUpdate(FormFieldOptionBase):
    id: Optional[int] = None


class FormFieldOptionResponse(FormFieldOptionBase):
    id: int
    field_id: int
    model_config = ConfigDict(from_attributes=True)

# Fields
class FormFieldBase(BaseModel):
    field_type: FieldType
    label: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    display_only: bool = False
    is_required: bool = False
    order: int = 0

class FormFieldCreate(FormFieldBase):
    options: Optional[List[FormFieldOptionCreate]] = None

class FormFieldUpdate(FormFieldBase):
    id: Optional[int] = None
    options: Optional[List[FormFieldOptionUpdate]] = None

class FormFieldResponse(FormFieldBase):
    id: int
    form_id: int
    options: List[FormFieldOptionResponse] = []
    model_config = ConfigDict(from_attributes=True)

# Forms
class FormBase(BaseModel):
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    target_role: TargetRole = TargetRole.ALL
    allow_multiple_submissions: bool = False
    is_active: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class FormCreate(FormBase):
    fields: Optional[List[FormFieldCreate]] = None

class FormUpdate(FormBase):
    fields: Optional[List[FormFieldUpdate]] = None

class FormResponse(FormBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    fields: List[FormFieldResponse] = []
    has_submissions: bool = False
    model_config = ConfigDict(from_attributes=True)

# Submissions
class FormSubmissionValueBase(BaseModel):
    field_id: int
    value: str

class FormSubmissionValueCreate(FormSubmissionValueBase):
    pass

class FormSubmissionValueResponse(FormSubmissionValueBase):
    id: int
    submission_id: int
    model_config = ConfigDict(from_attributes=True)

class FormSubmissionBase(BaseModel):
    form_id: int
    user_type: TargetRole

class FormSubmissionCreate(FormSubmissionBase):
    # Accepted for backwards compatibility with older app builds but IGNORED by
    # the API: the submitter is taken from the access token, never the body.
    user_id: Optional[int] = None
    values: List[FormSubmissionValueCreate]

class FormSubmissionResponse(FormSubmissionBase):
    id: int
    user_id: int
    submitted_at: datetime
    values: List[FormSubmissionValueResponse] = []
    model_config = ConfigDict(from_attributes=True)
