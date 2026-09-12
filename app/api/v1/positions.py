from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
import logging
import traceback

from ...core import get_db
from ...auth import get_current_active_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def get_all_positions(
    db: Session = Depends(get_db)
):
    """Get all positions."""
    try:
        query = """
            SELECT id, position, translate, departmentId, created_at, updated_at
            FROM position
            ORDER BY position ASC
        """
        result = db.execute(text(query))
        rows = result.fetchall()
        
        positions = []
        for row in rows:
            positions.append({
                'id': row[0],
                'position': row[1] or '',
                'translate': row[2] or '',
                'departmentId': row[3],
                'created_at': row[4].isoformat() if row[4] else None,
                'updated_at': row[5].isoformat() if row[5] else None,
            })
        
        return positions
    except Exception as e:
        logger.error(f"Error fetching positions: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error fetching positions: {str(e)}")
