"""
School Documents API
====================
Admin-managed PDF documents (policies, handbooks, etc.) shown
in the School Community section of the mobile app.

Public  : GET  /school-documents           – list active docs (sorted)
Public  : GET  /school-documents/{id}      – single doc
Admin   : POST /school-documents           – create + upload PDF
Admin   : PUT  /school-documents/{id}      – update metadata / replace PDF
Admin   : DELETE /school-documents/{id}    – soft-delete (is_active=0)
Admin   : PATCH /school-documents/reorder  – set sort_order for many
"""
import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ...core import get_db
from ...auth import get_current_active_user
from ...models.user import User
from ...services.storage_service import StorageService

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_PDF_TYPES = {"application/pdf"}
MAX_PDF_SIZE = 25 * 1024 * 1024  # 25 MB

ALLOWED_ICONS = {
    "description", "policy", "menu_book", "gavel", "shield",
    "article", "library_books", "folder_open", "school", "rule",
    "assignment", "badge", "verified", "info", "announcement",
}
ALLOWED_AUDIENCES = {"all", "parents", "students", "employees"}
_AUDIENCE_ALIAS = {
    "teacher": "employees",
    "teachers": "employees",
    "admin": "employees",
    "admins": "employees",
    "employee": "employees",
    "employees": "employees",
    "parent": "parents",
    "parents": "parents",
    "student": "students",
    "students": "students",
    "all": "all",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_admin_or_teacher(user: User) -> bool:
    role_id = getattr(user, "role", None)
    return role_id is not None and int(role_id) in {1, 2}  # 1=admin, 2=teacher


def _normalize_target_audience(raw: Optional[str]) -> str:
    if not raw:
        return "all"
    parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    normalized = []
    for part in parts:
        mapped = _AUDIENCE_ALIAS.get(part)
        if mapped and mapped in ALLOWED_AUDIENCES and mapped not in normalized:
            normalized.append(mapped)
    if not normalized:
        return "all"
    if "all" in normalized:
        return "all"
    return ",".join(normalized)


def _row_to_dict(row) -> dict:
    return {
        "id":         row[0],
        "title":      row[1],
        "title_km":   row[2],
        "subtitle":   row[3],
        "subtitle_km":row[4],
        "icon_name":  row[5],
        "pdf_url":    row[6],
        "target_audience": row[7],
        "is_active":  bool(row[8]),
        "sort_order": row[9],
        "created_at": str(row[10]) if row[10] else None,
        "updated_at": str(row[11]) if row[11] else None,
    }


_SELECT = """
    SELECT id, title, title_km, subtitle, subtitle_km,
           icon_name, pdf_url, target_audience, is_active, sort_order, created_at, updated_at
    FROM school_documents
"""


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class SchoolDocumentOut(BaseModel):
    id: int
    title: str
    title_km: Optional[str] = None
    subtitle: Optional[str] = None
    subtitle_km: Optional[str] = None
    icon_name: str = "description"
    pdf_url: str
    target_audience: str = "all"
    is_active: bool = True
    sort_order: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReorderItem(BaseModel):
    id: int
    sort_order: int


# ── Public Endpoints ──────────────────────────────────────────────────────────

@router.get("/school-documents", response_model=List[SchoolDocumentOut])
def list_school_documents(db: Session = Depends(get_db)):
    """Public: list all active school documents sorted by sort_order."""
    rows = db.execute(text(
        _SELECT + "WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
    )).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/school-documents/{doc_id}", response_model=SchoolDocumentOut)
def get_school_document(doc_id: int, db: Session = Depends(get_db)):
    """Public: get a single school document by ID."""
    row = db.execute(
        text(_SELECT + "WHERE id = :id LIMIT 1"),
        {"id": doc_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return _row_to_dict(row)


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@router.post("/school-documents", response_model=SchoolDocumentOut, status_code=201)
async def create_school_document(
    title: str = Form(...),
    title_km: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    subtitle_km: Optional[str] = Form(None),
    icon_name: str = Form("description"),
    target_audience: str = Form("all"),
    sort_order: Optional[int] = Form(None),
    pdf: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: upload a new PDF school document."""
    if not _is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Admin/Teacher only")

    if pdf.content_type not in ALLOWED_PDF_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    contents = await pdf.read()
    if len(contents) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF too large. Max size is 25 MB.")

    icon_name = icon_name.strip() if icon_name.strip() in ALLOWED_ICONS else "description"
    target_audience = _normalize_target_audience(target_audience)

    filename = f"doc_{uuid.uuid4().hex[:12]}.pdf"
    pdf_url = StorageService.upload_file(
        file_data=contents,
        folder="school_documents",
        filename=filename,
        content_type="application/pdf",
    )
    if not pdf_url:
        raise HTTPException(status_code=500, detail="Failed to upload PDF.")

    # Auto-increment sort order by default (append after current max)
    if sort_order is None or int(sort_order) <= 0:
        next_order_row = db.execute(text("""
            SELECT COALESCE(MAX(sort_order), 0) + 1
            FROM school_documents
        """)).fetchone()
        sort_order = int(next_order_row[0]) if next_order_row else 1

    result = db.execute(text("""
        INSERT INTO school_documents
            (title, title_km, subtitle, subtitle_km, icon_name, pdf_url, target_audience, is_active, sort_order)
        VALUES
            (:title, :title_km, :subtitle, :subtitle_km, :icon_name, :pdf_url, :target_audience, 1, :sort_order)
    """), {
        "title": title,
        "title_km": title_km or None,
        "subtitle": subtitle or None,
        "subtitle_km": subtitle_km or None,
        "icon_name": icon_name,
        "pdf_url": pdf_url,
        "target_audience": target_audience,
        "sort_order": sort_order,
    })
    db.commit()

    new_id = result.lastrowid
    row = db.execute(text(_SELECT + "WHERE id = :id"), {"id": new_id}).fetchone()
    return _row_to_dict(row)


@router.put("/school-documents/{doc_id}", response_model=SchoolDocumentOut)
async def update_school_document(
    doc_id: int,
    title: str = Form(...),
    title_km: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(None),
    subtitle_km: Optional[str] = Form(None),
    icon_name: str = Form("description"),
    target_audience: str = Form("all"),
    sort_order: int = Form(0),
    is_active: bool = Form(True),
    pdf: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: update document metadata and optionally replace the PDF."""
    if not _is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Admin/Teacher only")

    existing = db.execute(
        text(_SELECT + "WHERE id = :id LIMIT 1"),
        {"id": doc_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Document not found")

    icon_name = icon_name.strip() if icon_name.strip() in ALLOWED_ICONS else "description"
    target_audience = _normalize_target_audience(target_audience)
    pdf_url = existing[6]  # keep existing URL by default

    if pdf and pdf.filename:
        if pdf.content_type not in ALLOWED_PDF_TYPES:
            raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
        contents = await pdf.read()
        if len(contents) > MAX_PDF_SIZE:
            raise HTTPException(status_code=413, detail="PDF too large.")

        filename = f"doc_{uuid.uuid4().hex[:12]}.pdf"
        new_url = StorageService.upload_file(
            file_data=contents, folder="school_documents",
            filename=filename, content_type="application/pdf",
        )
        if new_url:
            # Delete old file
            try:
                StorageService.delete_file(pdf_url, None)
            except Exception:
                pass
            pdf_url = new_url

    db.execute(text("""
        UPDATE school_documents
        SET title=:title, title_km=:title_km, subtitle=:subtitle,
            subtitle_km=:subtitle_km, icon_name=:icon_name,
            pdf_url=:pdf_url, target_audience=:target_audience,
            is_active=:is_active, sort_order=:sort_order
        WHERE id=:id
    """), {
        "title": title, "title_km": title_km or None,
        "subtitle": subtitle or None, "subtitle_km": subtitle_km or None,
        "icon_name": icon_name, "pdf_url": pdf_url,
        "target_audience": target_audience,
        "is_active": 1 if is_active else 0,
        "sort_order": sort_order, "id": doc_id,
    })
    db.commit()

    row = db.execute(text(_SELECT + "WHERE id = :id"), {"id": doc_id}).fetchone()
    return _row_to_dict(row)


@router.delete("/school-documents/{doc_id}", status_code=200)
def delete_school_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: hard-delete a document and safely remove its PDF file to save space."""
    if not _is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Admin/Teacher only")

    existing = db.execute(
        text("SELECT id, pdf_url FROM school_documents WHERE id = :id LIMIT 1"),
        {"id": doc_id}
    ).fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="Document not found")

    pdf_url = existing[1]
    if pdf_url:
        try:
            StorageService.delete_file(pdf_url, None)
        except Exception as e:
            logger.warning(f"Failed to aggressively delete PDF storage for {doc_id}: {e}")

    db.execute(
        text("DELETE FROM school_documents WHERE id = :id"),
        {"id": doc_id}
    )
    db.commit()
    return {"detail": "Document and attached file deleted successfully"}


@router.patch("/school-documents/reorder", status_code=200)
def reorder_school_documents(
    items: List[ReorderItem],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Admin: update sort_order for multiple documents at once."""
    if not _is_admin_or_teacher(current_user):
        raise HTTPException(status_code=403, detail="Admin/Teacher only")

    for item in items:
        db.execute(
            text("UPDATE school_documents SET sort_order = :o WHERE id = :id"),
            {"o": item.sort_order, "id": item.id}
        )
    db.commit()
    return {"detail": f"Reordered {len(items)} documents"}
