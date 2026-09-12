from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from ...core import get_db
from ...auth import get_current_active_user
from ...models import Branch, User, BranchContact
from ...schemas.attendance import BranchResponse, BranchCreate, BranchUpdate, BranchContactResponse
from .websocket import broadcast_public_data_update

router = APIRouter()


@router.get("", response_model=List[BranchResponse])
async def read_branches(db: Session = Depends(get_db)):
    from ...services.query_cache import query_cache, generate_cache_key
    
    # Generate cache key
    cache_key = generate_cache_key("branches_list")
    
    # Try to get from cache (10 minutes TTL)
    cached_result = query_cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Query database
    branches = db.query(Branch).all()
    
    # Cache the result
    query_cache.set(cache_key, branches, ttl=600)
    
    return branches


@router.post("", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def create_branch(
    body: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    from ...services.query_cache import invalidate_cache
    
    existing = db.query(Branch).filter(Branch.branch_name == body.branch_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Branch with this name already exists",
        )

    branch = Branch(**body.model_dump())
    db.add(branch)
    db.commit()
    db.refresh(branch)
    
    # Invalidate cache
    invalidate_cache("branches_list")

    await broadcast_public_data_update("branches")
    return branch


@router.put("/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: int,
    body: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    if body.branch_name and body.branch_name != branch.branch_name:
        existing = db.query(Branch).filter(Branch.branch_name == body.branch_name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Another branch with this name already exists",
            )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(branch, key, value)

    db.commit()
    db.refresh(branch)

    await broadcast_public_data_update("branches")
    return branch


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    db.delete(branch)
    db.commit()

    await broadcast_public_data_update("branches")
    return None


# ── Branch Contacts ───────────────────────────────────────────────────────────

class BranchContactCreate(BaseModel):
    label: Optional[str] = None
    value: str
    sort_order: Optional[int] = None


class BranchContactUpdate(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    sort_order: Optional[int] = None


@router.get("/{branch_id}/contacts", response_model=List[BranchContactResponse])
async def get_branch_contacts(branch_id: int, db: Session = Depends(get_db)):
    return (
        db.query(BranchContact)
        .filter(BranchContact.branch_id == branch_id)
        .order_by(BranchContact.sort_order)
        .all()
    )


@router.post(
    "/{branch_id}/contacts",
    response_model=BranchContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_branch_contact(
    branch_id: int,
    body: BranchContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    contact = BranchContact(branch_id=branch_id, **body.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    await broadcast_public_data_update("branches")
    return contact


@router.put("/{branch_id}/contacts/{contact_id}", response_model=BranchContactResponse)
async def update_branch_contact(
    branch_id: int,
    contact_id: int,
    body: BranchContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    contact = db.query(BranchContact).filter(
        BranchContact.id == contact_id,
        BranchContact.branch_id == branch_id,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)

    db.commit()
    db.refresh(contact)
    await broadcast_public_data_update("branches")
    return contact


@router.delete("/{branch_id}/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch_contact(
    branch_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    contact = db.query(BranchContact).filter(
        BranchContact.id == contact_id,
        BranchContact.branch_id == branch_id,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    db.delete(contact)
    db.commit()
    await broadcast_public_data_update("branches")
    return None
