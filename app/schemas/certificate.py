"""
Pydantic schemas for the certificate management system.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# BackgroundCert schemas
# ─────────────────────────────────────────────────────────────────────────────

class BackgroundCertBase(BaseModel):
    program_id: int
    academic_id: int
    cer_model: int          # 1–10
    grade_group_ids: Optional[List[int]] = None
    grade_ids: Optional[List[int]] = None
    orientation: str = "landscape"


class BackgroundCertCreate(BackgroundCertBase):
    """Body for creating a new background_cert record."""
    pass


class BackgroundCertUpdate(BaseModel):
    """Body for updating fields on an existing record."""
    program_id: Optional[int] = None
    academic_id: Optional[int] = None
    cer_model: Optional[int] = None
    grade_group_ids: Optional[List[int]] = None
    grade_ids: Optional[List[int]] = None
    background_url: Optional[str] = None
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None
    orientation: Optional[str] = None


class BackgroundCertResponse(BackgroundCertBase):
    id: int
    background_url: Optional[str] = None
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None
    # Joined fields (populated by the list endpoint)
    program_name: Optional[str] = None
    academic_name: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# CertificateSettings schemas
# ─────────────────────────────────────────────────────────────────────────────

class CertificateSettingsBase(BaseModel):
    academic_id: int
    prefix: str = ""
    surfix: str = ""
    digit: int = 4
    year: Optional[int] = None   # e.g. 25 for 2025


class CertificateSettingsUpsert(CertificateSettingsBase):
    """Create or update certificate number format settings for one academic year."""
    pass


class CertificateSettingsResponse(CertificateSettingsBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Convenience: pre-built sample ID (e.g. "000125/PAMAIS")
    sample_id: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_sample(cls, obj) -> "CertificateSettingsResponse":
        """Build response and compute the sample certificate number."""
        data = {
            "id": obj.id,
            "academic_id": obj.academic_id,
            "prefix": obj.prefix or "",
            "surfix": obj.surfix or "",
            "digit": obj.digit or 4,
            "year": obj.year,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        digit = data["digit"]
        year_str = str(data["year"])[-2:] if data["year"] else ""
        data["sample_id"] = f"{data['prefix']}{'0' * digit}{year_str}{data['surfix']}"
        return cls(**data)


# ─────────────────────────────────────────────────────────────────────────────
# DemoCert student view schemas (joined query result)
# ─────────────────────────────────────────────────────────────────────────────

class DemoCertStudentResponse(BaseModel):
    """
    Full joined view of a demo_cert row — mirrors C# DemoCertView.
    All fields that the PDF generation needs are included.
    """
    id: int
    student_id: int
    cer_id: Optional[str] = None       # certificate number e.g. "0001/25PAMAIS"
    cer_model: int
    academic_id: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    nittes_id: Optional[int] = None
    is_public: bool = False

    # Student info
    studentid: Optional[str] = None    # unique student code
    k_name: Optional[str] = None       # Khmer name
    e_name: Optional[str] = None       # English name
    gender: Optional[str] = None
    dob: Optional[str] = None
    image: Optional[str] = None        # student photo URL

    # Branch info
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    address_english: Optional[str] = None
    director_kname: Optional[str] = None
    director_ename: Optional[str] = None
    director_signature_path: Optional[str] = None
    stamp_path: Optional[str] = None
    # URL-based assets (Migration 37)
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None

    # Academic / Program / Grade info
    academic_name: Optional[str] = None
    academic_us_name: Optional[str] = None
    program_name: Optional[str] = None
    program_name_us: Optional[str] = None
    program_short_code: Optional[str] = None
    grade_name: Optional[str] = None
    grade_name_us: Optional[str] = None
    us_grade: Optional[str] = None      # A, B, C …
    kh_grade: Optional[str] = None

    # Background image URL (from background_cert join)
    background_url: Optional[str] = None
    orientation: str = "landscape"

    # Teacher info
    teacher_kname: Optional[str] = None
    teacher_ename: Optional[str] = None

    # ── Snapshot fields (frozen at issuance; null for un-issued certs) ────────
    snapshot_background_url: Optional[str] = None
    snapshot_signature_url: Optional[str] = None
    snapshot_stamp_url: Optional[str] = None
    snapshot_cert_date: Optional[date] = None
    snapshot_director_kname: Optional[str] = None
    snapshot_director_ename: Optional[str] = None
    snapshot_principal_label: Optional[str] = None
    snapshot_address_prefix: Optional[str] = None
    snapshot_date_format: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("grade_type_id", mode="before")
    @classmethod
    def _coerce_grade_type_id(cls, v):
        """grade_type_id in DB may be a comma-separated string e.g. '1,2,3'."""
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        first = s.split(",")[0].strip()
        try:
            return int(first)
        except ValueError:
            return None

    @field_validator("dob", mode="before")
    @classmethod
    def _coerce_dob(cls, v):
        """dob may come as a Python date/datetime object; convert to ISO string."""
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    @field_validator("image", mode="before")
    @classmethod
    def _coerce_image(cls, v):
        """Return the student's API-managed image URL/path."""
        if v is None:
            return None
        if isinstance(v, (bytes, bytearray)):
            raise ValueError("Binary student media must be migrated to a resource URL")
        return str(v)


# ─────────────────────────────────────────────────────────────────────────────
# Branch Certificate Asset schemas (signature / stamp upload)
# ─────────────────────────────────────────────────────────────────────────────

class BranchCertAssetResponse(BaseModel):
    """Returned after uploading signature or stamp for a branch."""
    branch_id: int
    branch_name: Optional[str] = None
    signature_url: Optional[str] = None
    stamp_url: Optional[str] = None
    director_kname: Optional[str] = None
    director_ename: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Certificate Issue / Re-Issue schemas
# ─────────────────────────────────────────────────────────────────────────────

class CertIssueItem(BaseModel):
    """One student's certificate issuance data."""
    student_id: int
    cer_model: int
    academic_id: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    nittes_id: Optional[int] = None
    is_public: bool = False
    # Snapshot — captured at PDF generation time
    snapshot_background_url: Optional[str] = None
    snapshot_signature_url: Optional[str] = None
    snapshot_stamp_url: Optional[str] = None
    snapshot_cert_date: Optional[date] = None
    snapshot_director_kname: Optional[str] = None
    snapshot_director_ename: Optional[str] = None
    snapshot_principal_label: Optional[str] = None
    snapshot_address_prefix: Optional[str] = None
    snapshot_date_format: Optional[str] = None
    regenerate_cer_id: bool = False


class CertIssueRequest(BaseModel):
    """Issue or re-issue certificates for a batch of students."""
    academic_id: int           # used for cer_id generation
    students: List[CertIssueItem]
    send_push_notification: bool = True  # notify parents (public certs only)
    # Deprecated: image URLs use server PUBLIC_API_BASE_URL only.
    push_public_base_url: Optional[str] = None


class CertIssueResultItem(BaseModel):
    """Result for one student after issue/re-issue."""
    student_id: int
    cer_id: str
    demo_cert_id: int
    was_reissued: bool          # True if a prior demo_cert row existed
    is_public: bool


class CertIssueResponse(BaseModel):
    """Batch result for a CertIssueRequest."""
    issued: List[CertIssueResultItem]
    total: int


# ─────────────────────────────────────────────────────────────────────────────

class CertIdGenerateRequest(BaseModel):
    """Ask the API to generate the next certificate number."""
    academic_id: int
    student_id: int
    cer_model: int
    program_id: int
    grade_id: int
    grade_type_id: Optional[int] = None
    nittes_id: Optional[int] = None


class CertIdGenerateResponse(BaseModel):
    cer_id: str    # e.g. "0001/25PAMAIS"
