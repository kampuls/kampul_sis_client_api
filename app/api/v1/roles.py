from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ...core import get_db
from ...models import Role
from ...schemas import RoleResponse

router = APIRouter()

@router.get("/", response_model=List[RoleResponse])
async def read_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).all()
    return roles
