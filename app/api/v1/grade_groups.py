from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from pydantic import BaseModel

from ...core import get_db

router = APIRouter()

class GradeGroupResponse(BaseModel):
    id: int
    group_name: str
    program_id: Optional[int] = None
    noted: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("/", response_model=List[GradeGroupResponse])
async def read_grade_groups(
    academic_id: Optional[int] = None,
    program_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get grade groups, optionally filtered by academic year.
    """
    try:
        # Base query
        # Query to get grade groups with their associated grade type
        # We join with grade and grade_type tables to get the type name
        # We use DISTINCT or GROUP BY to ensure unique grade groups
        query_parts = [
            "SELECT gg.id, gg.group_name, gg.program_id, gg.noted, MAX(gt.type_name) as type_name",
            "FROM grade_group gg",
            "LEFT JOIN grade g ON g.group_Id = gg.id",
            "LEFT JOIN grade_type gt ON g.grade_type_id = gt.id"
        ]
        
        where_conditions = []
        params = {}
        
        # Filter directly on grade_group table columns
        if academic_id is not None:
            where_conditions.append("gg.academic_id = :academic_id")
            params["academic_id"] = academic_id
            
        if program_id is not None:
            where_conditions.append("gg.program_id = :program_id")
            params["program_id"] = program_id
        
        if where_conditions:
            query_parts.append("WHERE " + " AND ".join(where_conditions))
        
        query_parts.append("GROUP BY gg.id, gg.group_name, gg.program_id, gg.noted")
        query_parts.append("ORDER BY gg.id ASC")
        
        query = text(" ".join(query_parts))
        result = db.execute(query, params).fetchall()
        
        groups = []
        for row in result:
            group_name = row[1]
                
            groups.append({
                "id": row[0],
                "group_name": group_name,
                "program_id": row[2],
                "noted": row[3]
            })
            
        return groups
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching grade groups: {str(e)}")
