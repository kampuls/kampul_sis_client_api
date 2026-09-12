"""
Dynamic Forms API Endpoints
CRUD for forms, fields, options, and submissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
from pathlib import Path

from ....auth.dependencies import Principal, get_current_principal
from ....core.database import get_db
from ....services.storage_service import StorageService
from ....models.form import Form, FormField, FormFieldOption, FormSubmission, FormSubmissionValue
from ....schemas.form import (
    FormCreate, FormUpdate, FormResponse,
    FormSubmissionCreate, FormSubmissionResponse,
)

router = APIRouter()

UPLOAD_DIR = Path("uploads/forms")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _delete_file_if_exists(url: str):
    """Delete a local uploaded file given its URL."""
    StorageService.delete_local_file(url)


def _get_form_or_404(form_id: int, db: Session) -> Form:
    form = db.query(Form).filter(Form.id == form_id).first()
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


def _sync_fields(form: Form, fields_data: list, db: Session, has_submissions: bool = False):
    """Update fields (and their options) for a form, preserving IDs when provided.

    Existing fields keep their IDs so submission answers (FK on field_id) are not
    cascade-deleted. Options are synced by ID when available.
    """
    existing_fields = {f.id: f for f in db.query(FormField).filter(FormField.form_id == form.id).all()}
    seen_field_ids = set()

    for idx, f in enumerate(fields_data or []):
        field_id = getattr(f, 'id', None)

        if field_id and field_id in existing_fields:
            field = existing_fields[field_id]

            if has_submissions and field.field_type != f.field_type:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot change field type for Question {idx + 1} "
                        f"('{field.label}') because the form has existing submissions."
                    ),
                )

            # If image was replaced, delete old image
            if field.image_url and field.image_url != f.image_url:
                _delete_file_if_exists(field.image_url)

            field.label = f.label
            field.description = f.description
            field.image_url = f.image_url
            field.display_only = f.display_only
            field.field_type = f.field_type
            field.is_required = f.is_required
            field.order = f.order
            seen_field_ids.add(field.id)

            _sync_options(field, f.options or [], db)
        else:
            # Insert new field
            field = FormField(
                form_id=form.id,
                field_type=f.field_type,
                label=f.label,
                description=f.description,
                image_url=f.image_url,
                display_only=f.display_only,
                is_required=f.is_required,
                order=f.order,
            )
            db.add(field)
            db.flush()  # get field.id
            seen_field_ids.add(field.id)

            for o in (f.options or []):
                db.add(FormFieldOption(
                    field_id=field.id,
                    label=o.label,
                    value=o.value,
                    order=o.order,
                ))

    # Delete fields that are no longer present
    for existing_id, field in existing_fields.items():
        if existing_id not in seen_field_ids:
            # Protect historical answers: deleting a field CASCADE-deletes
            # form_submission_values for that field_id.
            answer_count = (
                db.query(FormSubmissionValue)
                .filter(FormSubmissionValue.field_id == existing_id)
                .count()
            )
            if answer_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot remove question '{field.label}' because it already "
                        f"has {answer_count} response(s). Hide the form or keep the question."
                    ),
                )
            if field.image_url:
                _delete_file_if_exists(field.image_url)
            db.delete(field)

    db.flush()


def _sync_options(field: FormField, options_data: list, db: Session):
    """Update options for a field, preserving option IDs when provided."""
    existing_options = {
        o.id: o
        for o in db.query(FormFieldOption).filter(FormFieldOption.field_id == field.id).all()
    }
    seen_option_ids = set()

    for o in options_data or []:
        option_id = getattr(o, 'id', None)
        if option_id and option_id in existing_options:
            opt = existing_options[option_id]
            opt.label = o.label
            opt.value = o.value
            opt.order = o.order
            seen_option_ids.add(opt.id)
        else:
            opt = FormFieldOption(
                field_id=field.id,
                label=o.label,
                value=o.value,
                order=o.order,
            )
            db.add(opt)
            db.flush()
            seen_option_ids.add(opt.id)

    for existing_id, opt in existing_options.items():
        if existing_id not in seen_option_ids:
            db.delete(opt)

    db.flush()


# ── Form Image Upload ────────────────────────────────────────────────────────

@router.post("/upload-image")
async def upload_form_image(
    request: Request,
    image: UploadFile = File(...),
    principal: Principal = Depends(get_current_principal),
):
    """
    Upload an image for a form field question or dynamic form graphic.

    Staff only, and authenticated: this writes a file to the server, and the
    endpoint previously accepted anonymous uploads.
    """
    if principal.kind != "teacher":
        raise HTTPException(status_code=403, detail="Staff account required")
    if not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    try:
        # Check size (limit to 5MB optionally)
        content = await image.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image size exceeds 5MB limit.")
            
        url_path = StorageService.upload_file(
            file_data=content,
            folder="forms",
            filename=image.filename,
            content_type=image.content_type
        )
        
        if not url_path:
            raise HTTPException(status_code=500, detail="Failed to upload image")

        if url_path.startswith('/'):
            base = str(request.base_url).rstrip("/")
            url = f"{base}{url_path}"
        else:
            url = url_path
        
        return {"url": url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Form CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[FormResponse])
def list_forms(db: Session = Depends(get_db)):
    """List all forms."""
    forms = db.query(Form).order_by(Form.created_at.desc()).all()
    for form in forms:
        form.has_submissions = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).count() > 0
    return forms


@router.get("/{form_id}", response_model=FormResponse)
def get_form(form_id: int, db: Session = Depends(get_db)):
    """Get a single form with all its fields and options."""
    form = _get_form_or_404(form_id, db)
    form.has_submissions = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).count() > 0
    return form


@router.post("", response_model=FormResponse, status_code=status.HTTP_201_CREATED)
def create_form(payload: FormCreate, db: Session = Depends(get_db)):
    """Create a new form."""
    form = Form(
        title=payload.title,
        description=payload.description,
        image_url=payload.image_url,
        target_role=payload.target_role,
        allow_multiple_submissions=payload.allow_multiple_submissions,
        is_active=payload.is_active,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(form)
    db.flush()  # get form.id before fields

    _sync_fields(form, payload.fields or [], db)
    db.commit()
    db.refresh(form)
    form.has_submissions = False
    return form


@router.put("/{form_id}", response_model=FormResponse)
def update_form(form_id: int, payload: FormUpdate, db: Session = Depends(get_db)):
    """Update an existing form, preserving field IDs when provided."""
    form = _get_form_or_404(form_id, db)

    # Check if there are existing submissions
    has_submissions = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).count() > 0

    # If cover image was replaced, delete old image
    if form.image_url and form.image_url != payload.image_url:
        _delete_file_if_exists(form.image_url)

    form.title = payload.title
    form.description = payload.description
    form.image_url = payload.image_url
    form.target_role = payload.target_role
    form.allow_multiple_submissions = payload.allow_multiple_submissions
    form.is_active = payload.is_active
    form.start_date = payload.start_date
    form.end_date = payload.end_date

    _sync_fields(form, payload.fields or [], db, has_submissions)
    db.commit()
    db.refresh(form)
    form.has_submissions = has_submissions
    return form


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(form_id: int, db: Session = Depends(get_db)):
    """Delete a form and all its fields/submissions."""
    form = _get_form_or_404(form_id, db)
    
    # 1. Delete form cover image
    if form.image_url:
        _delete_file_if_exists(form.image_url)
        
    # 2. Delete all field images
    fields = db.query(FormField).filter(FormField.form_id == form.id).all()
    for f in fields:
        if f.image_url:
            _delete_file_if_exists(f.image_url)
            
    # 3. Delete all submission images
    submissions = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).all()
    for sub in submissions:
        values = db.query(FormSubmissionValue).filter(FormSubmissionValue.submission_id == sub.id).all()
        for val in values:
            if val.value:
                _delete_file_if_exists(val.value)

    db.delete(form)
    db.commit()


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(submission_id: int, db: Session = Depends(get_db)):
    """Delete a specific form submission and clean up any uploaded image files."""
    submission = db.query(FormSubmission).filter(FormSubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Delete any uploaded image files from disk
    values = db.query(FormSubmissionValue).filter(
        FormSubmissionValue.submission_id == submission_id
    ).all()
    for val in values:
        if val.value:
            _delete_file_if_exists(val.value)
    
    db.delete(submission)
    db.commit()


@router.get("/{form_id}/submissions", response_model=List[FormSubmissionResponse])
def list_submissions(
    form_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List all submissions for a form (staff/admin view).

    This returns everybody's answers, so it must not be reachable
    unauthenticated or by a parent.
    """
    if principal.kind != "teacher":
        raise HTTPException(status_code=403, detail="Staff account required")
    _get_form_or_404(form_id, db)
    return (
        db.query(FormSubmission)
        .filter(FormSubmission.form_id == form_id)
        .order_by(FormSubmission.submitted_at.desc())
        .all()
    )


@router.post("/{form_id}/submit", response_model=FormSubmissionResponse, status_code=status.HTTP_201_CREATED)
def submit_form(
    form_id: int,
    payload: FormSubmissionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Submit answers for a form.

    The submitter is taken from the access token. ``payload.user_id`` and
    ``payload.user_type`` are ignored: they used to be trusted, which let a
    caller file a submission under anybody else's identity.
    """
    form = _get_form_or_404(form_id, db)

    if not form.is_active:
        raise HTTPException(status_code=400, detail="This form is no longer accepting responses.")

    submitter_id = principal.id
    submitter_type = principal.kind

    if not form.allow_multiple_submissions:
        # Scope by type as well — the same integer is a different person in the
        # parents table than in users.
        existing = db.query(FormSubmission).filter(
            FormSubmission.form_id == form_id,
            FormSubmission.user_id == submitter_id,
            FormSubmission.user_type == submitter_type,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="You have already submitted this form.")

    submission = FormSubmission(
        form_id=form_id,
        user_id=submitter_id,
        user_type=submitter_type,
    )
    db.add(submission)
    db.flush()

    for v in payload.values:
        db.add(FormSubmissionValue(
            submission_id=submission.id,
            field_id=v.field_id,
            value=v.value,
        ))

    db.commit()
    db.refresh(submission)
    return submission
