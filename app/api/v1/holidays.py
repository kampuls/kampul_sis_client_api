from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import extract
from typing import List, Optional

from ...core import get_db
from ...models.holiday import Holiday
from ...schemas import HolidayBase, HolidayCreate, HolidayUpdate, HolidayResponse

router = APIRouter()

@router.get("", response_model=List[HolidayResponse])
async def get_holidays(
    skip: int = 0,
    limit: int = 100,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get list of holidays.
    Optional filter by year.
    """
    query = db.query(Holiday)
    
    if year:
        query = query.filter(extract('year', Holiday.date) == year)
    
    holidays = query.order_by(Holiday.date).offset(skip).limit(limit).all()
    return holidays

@router.post("", response_model=HolidayResponse)
async def create_holiday(
    holiday: HolidayCreate,
    db: Session = Depends(get_db)
):
    """Create a new holiday."""
    db_holiday = Holiday(**holiday.model_dump())
    db.add(db_holiday)
    db.commit()
    db.refresh(db_holiday)
    return db_holiday

@router.get("/{holiday_id}", response_model=HolidayResponse)
async def get_holiday(
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific holiday by ID."""
    holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return holiday

@router.put("/{holiday_id}", response_model=HolidayResponse)
async def update_holiday(
    holiday_id: int,
    holiday_update: HolidayUpdate,
    db: Session = Depends(get_db)
):
    """Update a holiday."""
    db_holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not db_holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    update_data = holiday_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_holiday, key, value)
    
    db.commit()
    db.refresh(db_holiday)
    return db_holiday

@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Delete a holiday."""
    db_holiday = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not db_holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")
    
    db.delete(db_holiday)
    db.commit()
    return None
