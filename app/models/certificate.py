"""
Certificate management models.

Mirrors the legacy C# `background_cert` and `certificate_settings` tables.
`background_cert` scope is (academic_id + program_id + cer_model) — same JOIN
pattern used in ControlCertificate.cs lines 131–134.

Schema extension: `background_url` VARCHAR column is added to `background_cert`
so the Flutter app can use image URLs instead of legacy BLOB columns.
"""
from sqlalchemy import Column, Integer, String, DateTime, Date, Text
from sqlalchemy.sql import func
from .base import Base


class BackgroundCert(Base):
    """
    Certificate background image settings.
    One record per (academic_id + program_id + cer_model) combination.
    Flutter and desktop both read/write `background_url`, which contains the
    URL/path returned by StorageService. The compatibility column is retained
    only so old installations can be migrated once.
    """
    __tablename__ = "background_cert"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    cer_model = Column(Integer, nullable=False)           # 1–10
    grade_group_ids = Column(String(500), nullable=True) # JSON array of ints
    grade_ids = Column(String(500), nullable=True)       # JSON array of ints

    # Compatibility column name retained, but its value is a resource URL/path.
    background_image = Column(String(1000), nullable=True)

    # New URL column — written by Flutter API, read by Flutter app
    background_url = Column(String(500), nullable=True)
    
    orientation = Column(String(20), nullable=False, default="landscape")

    # New URL columns for Model-level stamp and signature
    signature_url = Column(String(500), nullable=True)
    stamp_url = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class CertificateSettings(Base):
    """
    Per-academic-year certificate number format settings.
    Mirrors the C# `CertificateSettings` form — exactly one row per academic_id.

    Format algorithm (from AddStudentsCertificate.cs L540-542):
        cer_id = prefix + zeroPad(sequence, digit) + year(2-digit) + surfix
    Example with prefix='', digit=4, year=25, surfix='/PAMAIS':
        0001/25PAMAIS
    """
    __tablename__ = "certificate_settings"

    id = Column(Integer, primary_key=True, index=True)
    academic_id = Column(Integer, nullable=False, unique=True, index=True)
    prefix = Column(String(50), nullable=False, default="")
    surfix = Column(String(50), nullable=False, default="")
    digit = Column(Integer, nullable=False, default=4)   # zero-padding width
    year = Column(Integer, nullable=True)                # 2-digit year e.g. 25
    orientation = Column(String(20), nullable=False, default="landscape")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DemoCert(Base):
    """
    Student certificate records.
    Mirrors the existing MySQL `demo_cert` table.

    Snapshot columns freeze the state at issuance so the certificate always
    renders identically even if branch data changes later.
    """
    __tablename__ = "demo_cert"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    cer_id = Column(String(100), nullable=True)          # e.g. "0001/25PAMAIS"
    cer_model = Column(Integer, nullable=False)           # 1–10
    academic_id = Column(Integer, nullable=False, index=True)
    program_id = Column(Integer, nullable=False)
    grade_id = Column(Integer, nullable=False)
    grade_type_id = Column(Integer, nullable=True)
    nittes_id = Column(Integer, nullable=True)
    is_public = Column(Integer, nullable=False, default=0)  # 0: Locked, 1: Public

    # ── Snapshot columns (frozen at issuance) ─────────────────────────────
    # These capture the exact URLs/values used when the certificate was printed
    # so re-printing always reproduces the original certificate faithfully.
    snapshot_background_url = Column(String(500), nullable=True)
    snapshot_signature_url  = Column(String(500), nullable=True)
    snapshot_stamp_url      = Column(String(500), nullable=True)
    snapshot_cert_date      = Column(Date, nullable=True)
    snapshot_director_kname = Column(String(200), nullable=True)
    snapshot_director_ename = Column(String(200), nullable=True)
    snapshot_principal_label = Column(String(200), nullable=True)
    snapshot_address_prefix = Column(String(200), nullable=True)
    snapshot_date_format = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
