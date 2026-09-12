from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

from ...core import get_db
from ...schemas.attendance import GradeResponse

router = APIRouter()

@router.get("", response_model=List[GradeResponse])
async def read_grades(
    academic_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    program_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Get grades with optional filtering by academic year, branch, program, and shift.
    Includes grade_type information for display.
    """
    try:
        # Build query with JOIN to grade_type and conditional JOIN to learning for filtering
        query_parts = [
            "SELECT g.id, g.grade_name, g.grade_type_id, gt.type_name, g.group_Id",
            "FROM grade g",
            "LEFT JOIN grade_type gt ON g.grade_type_id = gt.id"
        ]
        
        # Add conditions if filters are provided
        conditions = []
        params = {}
        
        # If filtering by academic/program/shift, need to join with learning table
        if academic_id is not None or program_id is not None or shift_id is not None:
            query_parts.append("INNER JOIN learning l ON g.id = l.gradeid")
            
            if academic_id is not None:
                conditions.append("l.academicid = :academic_id")
                params["academic_id"] = academic_id
            
            if program_id is not None:
                conditions.append("l.programid = :program_id")
                params["program_id"] = program_id
                
            if shift_id is not None:
                conditions.append("l.shiftid = :shift_id")
                params["shift_id"] = shift_id
        
        # Branch filter is directly on grade table
        if branch_id is not None:
            conditions.append("g.branch_id = :branch_id")
            params["branch_id"] = branch_id
        
        # Combine conditions
        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))
        
        # Use GROUP BY to avoid duplicates when joining with learning
        query_parts.append("GROUP BY g.id, g.grade_name, g.grade_type_id, gt.type_name, g.group_Id")
        query_parts.append("ORDER BY g.id ASC")
        
        query = text(" ".join(query_parts))
        result = db.execute(query, params).fetchall()
        
        grades = []
        for row in result:
            # Handle comma-separated grade_type_id from database (e.g., "1,2,3" -> 1)
            grade_type_id_raw = row[2]
            if grade_type_id_raw is not None:
                # If it's a string with commas, take the first ID
                if isinstance(grade_type_id_raw, str) and ',' in grade_type_id_raw:
                    try:
                        grade_type_id = int(grade_type_id_raw.split(',')[0].strip())
                    except (ValueError, IndexError):
                        grade_type_id = None
                else:
                    try:
                        grade_type_id = int(grade_type_id_raw)
                    except (ValueError, TypeError):
                        grade_type_id = None
            else:
                grade_type_id = None
            
            grades.append({
                "id": row[0],
                "grade_name": row[1],
                "grade_type_id": grade_type_id,
                "grade_type_name": row[3] if row[3] else None,
                "grade_group_id": row[4] if len(row) > 4 and row[4] is not None else None
            })
            
        return grades
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching grades: {str(e)}")
