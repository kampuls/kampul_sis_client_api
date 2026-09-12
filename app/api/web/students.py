from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import logging

from ...core import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/academics")
async def get_academics(db: Session = Depends(get_db)):
    """Returns all academic years ordered newest first — mirrors C# LoadAllAcademics."""
    try:
        rows = db.execute(text(
            "SELECT id, academic_name, academic_us_name FROM academic ORDER BY academic_name DESC"
        )).fetchall()
        return {
            "data": [
                {
                    "id": r.id,
                    "name": r.academic_us_name or r.academic_name,
                    "name_kh": r.academic_name,
                }
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching academics: {e}")
        return {"data": []}


@router.get("/branches")
async def get_branches(db: Session = Depends(get_db)):
    """Returns all branches — mirrors C# LoadAllBranches (includes All Branches option)."""
    try:
        rows = db.execute(text("SELECT id, branch_name FROM branch ORDER BY branch_name")).fetchall()
        data = [{"id": 0, "name": "All Branches"}]
        data += [{"id": r.id, "name": r.branch_name} for r in rows]
        return {"data": data}
    except Exception as e:
        logger.error(f"Error fetching branches: {e}")
        return {"data": [{"id": 0, "name": "All Branches"}]}

@router.get("/statuses")
async def get_statuses(db: Session = Depends(get_db)):
    """Returns all available student statuses."""
    try:
        rows = db.execute(text("SELECT id, status FROM status ORDER BY id")).fetchall()
        data = [{"id": "all", "name": "All Statuses"}]
        data += [{"id": str(r.id), "name": r.status} for r in rows]
        return {"data": data}
    except Exception as e:
        logger.error(f"Error fetching statuses: {e}")
        return {"data": [{"id": "all", "name": "All Statuses"}]}

@router.get("/")
async def get_all_students(
    academic_id: Optional[int] = Query(None, description="Academic Year ID for learning programs"),
    branch_id: Optional[int] = Query(None, description="Filter by Branch ID"),
    status_id: Optional[str] = Query(None, description="Status filter (1=Active, 0=Inactive, all=All)"),
    db: Session = Depends(get_db)
):
    """
    Returns a comprehensive list of all students matching the criteria.
    Mimics the ControlStudents.cs loading behavior.
    """
    try:
        # We use raw SQL with SQLAlchemy text to directly translate the optimized query
        
        base_query_str = """
            SELECT
                s.id AS student_id, s.studentid, s.optional_id, s.kName, s.eName, s.gender,
                s.dob, s.province, s.district, s.commune, s.village,
                s.previousSchool, s.leaveDate, s.academic, ac.academic_name, ac.academic_us_name,
                s.myparents, s.branch, b.branch_name, st.id AS status_id, st.status AS status_name, s.student_noted,
                s.created_at, s.updated_at, s.child_order, s.is_foreigner, s.student_phone,
                GROUP_CONCAT(DISTINCT pr.program_name) AS student_learning, 
                COUNT(DISTINCT pr.id) AS program_count,
                MAX(CASE WHEN bsi.id IS NOT NULL THEN 1 ELSE 0 END) AS is_using_bus,
                p.id AS parent_id, p.fatherName, p.motherName, p.fatherPhone, p.motherPhone, p.fatherJob, p.motherJob,
                p.pProvince, p.pDistrict, p.pCommune, p.pVillage, p.pEmail, p.pTelegramId,
                p.gHome, p.gStreet, p.gGroup, p.gProvince, p.gDistrict, p.gCommune, p.gVillage,
                p.gName, p.gPhone, p.gIsThe
            FROM students s
            LEFT JOIN parents p ON s.myparents = p.id
            LEFT JOIN learning l ON s.id = l.studentid {academic_condition}
            LEFT JOIN program pr ON l.programid = pr.id
            LEFT JOIN academic ac ON s.academic = ac.id
            LEFT JOIN branch b ON s.branch = b.id
            LEFT JOIN status st ON s.status = st.id
            LEFT JOIN bus_stu_inroll bsi ON s.id = bsi.student_id AND bsi.status = 'active'
            WHERE 1=1 {status_condition} {branch_condition}
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """

        # Build conditions dynamically to avoid syntax issues if None
        academic_condition = "AND l.academicid = :academic_id" if academic_id else ""
        branch_condition = "AND s.branch = :branch_id" if branch_id else ""
        
        if status_id == "1":
            status_condition = "AND s.status = 1"
        elif status_id == "0":
            status_condition = "AND s.status != 1"
        elif status_id is not None and status_id != "all":
            # If a specific numeric status is chosen dynamically
            try:
                numeric_status = int(status_id)
                status_condition = f"AND s.status = {numeric_status}"
            except ValueError:
                status_condition = ""
        else:
            status_condition = ""
        
        final_query = text(base_query_str.format(
            academic_condition=academic_condition,
            branch_condition=branch_condition,
            status_condition=status_condition
        ))

        params = {}
        if academic_id:
            params["academic_id"] = academic_id
        if branch_id:
            params["branch_id"] = branch_id

        results = db.execute(final_query, params).fetchall()

        # Convert to a dict structure suitable for JSON Response
        student_list = []
        for index, row in enumerate(results):
            student_list.append({
                "index": index + 1,
                "id": row.student_id,
                "unique_id": row.studentid,
                "optional_id": row.optional_id,
                "k_name": row.kName,
                "e_name": row.eName,
                "gender": row.gender,
                "dob": row.dob.strftime("%d-%m-%Y") if row.dob else None,
                "age": _calculate_age(row.dob) if row.dob else None,
                "is_foreigner": bool(row.is_foreigner),
                "branch_id": row.branch,
                "branch_name": row.branch_name,
                "academic_id": row.academic,
                "academic_name": row.academic_us_name or row.academic_name,
                "status_id": row.status_id,
                "status_name": row.status_name,
                "student_phone": row.student_phone,
                "program_count": row.program_count,
                "student_learning": row.student_learning,
                "is_using_bus": bool(row.is_using_bus),
                "created_at": row.created_at.strftime("%Y-%m-%dT%H:%M:%S") if row.created_at else None,
            })
            
        return {"data": student_list}

    except Exception as e:
        logger.error(f"Error fetching students: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching students")


@router.get("/class-teacher")
async def get_class_teacher(
    program_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    grade_type_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    academic_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get teacher & assistant info for a specific class (mirrors C# LoadClassTeachers).
    This route MUST be declared before /{student_id} to prevent routing conflicts.
    """
    try:
        row = db.execute(text("""
            SELECT
                ct.teacher_id,
                ct.teacher_assistant_id,
                u1.kName  AS teacher_k_name,
                u1.eName  AS teacher_e_name,
                u1.phone  AS teacher_phone,
                u1.dob    AS teacher_dob,
                COALESCE(u1.isForeigner, 0) AS teacher_is_foreigner,
                ur1.avatar AS teacher_avatar,
                u2.kName  AS assistant_k_name,
                u2.eName  AS assistant_e_name,
                COALESCE(u2.isForeigner, 0) AS assistant_is_foreigner,
                ur2.avatar AS assistant_avatar
            FROM class_teachers ct
            LEFT JOIN users u1 ON ct.teacher_id = u1.id
            LEFT JOIN users_resource ur1 ON ur1.user_id = ct.teacher_id AND ur1.user_type = 'teacher'
            LEFT JOIN users u2 ON ct.teacher_assistant_id = u2.id
            LEFT JOIN users_resource ur2 ON ur2.user_id = ct.teacher_assistant_id AND ur2.user_type = 'teacher'
            WHERE ct.program_id    = :program_id
              AND ct.grade_id      = :grade_id
              AND ct.grade_type_id = :grade_type_id
              AND ct.shift_id      = :shift_id
              AND ct.academic_id   = :academic_id
              AND ct.branch_id     = :branch_id
            LIMIT 1
        """), {
            "program_id": program_id,
            "grade_id": grade_id,
            "grade_type_id": grade_type_id,
            "shift_id": shift_id,
            "academic_id": academic_id,
            "branch_id": branch_id,
        }).first()

        if not row:
            return {"teacher": None, "assistant": None}

        def pick_name(k_name, e_name, is_foreigner):
            """Mirror C# name-picking logic based on isForeigner flag."""
            if is_foreigner == 1:
                return k_name or e_name or ""
            elif is_foreigner == 2:
                return e_name or k_name or ""
            return k_name or e_name or ""

        import datetime as dt
        def fmt_dob(dob_val):
            if not dob_val:
                return None
            if hasattr(dob_val, 'strftime'):
                return dob_val.strftime("%d-%m-%Y")
            return str(dob_val)

        teacher = {
            "id": row.teacher_id,
            "name": pick_name(row.teacher_k_name, row.teacher_e_name, row.teacher_is_foreigner) or "Not assigned",
            "k_name": row.teacher_k_name,
            "e_name": row.teacher_e_name,
            "phone": row.teacher_phone,
            "dob": fmt_dob(row.teacher_dob),
            "avatar": row.teacher_avatar,
        } if row.teacher_id else None

        assistant = {
            "id": row.teacher_assistant_id,
            "name": pick_name(row.assistant_k_name, row.assistant_e_name, row.assistant_is_foreigner),
            "k_name": row.assistant_k_name,
            "e_name": row.assistant_e_name,
            "avatar": row.assistant_avatar,
        } if row.teacher_assistant_id else None

        return {"teacher": teacher, "assistant": assistant}

    except Exception as e:
        logger.error(f"Error fetching class teacher: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching teacher info")


@router.get("/{student_id}")
async def get_student_detail(
    student_id: int,
    db: Session = Depends(get_db)
):
    """
    Returns full details for a single student to populate the Details Sheet.
    Includes personal, parent/guardian, and academic info.
    """
    try:
        query = text("""
            SELECT
                s.id AS student_id, s.studentid, s.optional_id, s.kName, s.eName, s.gender,
                s.dob, s.province, s.district, s.commune, s.village,
                s.previousSchool, s.leaveDate, s.academic, ac.academic_name, ac.academic_us_name,
                s.myparents, s.branch, b.branch_name, st.id AS status_id, st.status AS status_name, s.student_noted,
                s.created_at, s.updated_at, s.child_order, s.is_foreigner, s.student_phone,
                GROUP_CONCAT(DISTINCT pr.program_name) AS student_learning, 
                COUNT(DISTINCT pr.id) AS program_count,
                MAX(CASE WHEN bsi.id IS NOT NULL THEN 1 ELSE 0 END) AS is_using_bus,
                p.id AS parent_id, p.fatherName, p.motherName, p.fatherPhone, p.motherPhone, p.fatherJob, p.motherJob,
                p.pProvince, p.pDistrict, p.pCommune, p.pVillage, p.pEmail, p.pTelegramId,
                p.gHome, p.gStreet, p.gGroup, p.gProvince, p.gDistrict, p.gCommune, p.gVillage,
                p.gName, p.gPhone, p.gIsThe
            FROM students s
            LEFT JOIN parents p ON s.myparents = p.id
            LEFT JOIN learning l ON s.id = l.studentid
            LEFT JOIN program pr ON l.programid = pr.id
            LEFT JOIN academic ac ON s.academic = ac.id
            LEFT JOIN branch b ON s.branch = b.id
            LEFT JOIN status st ON s.status = st.id
            LEFT JOIN bus_stu_inroll bsi ON s.id = bsi.student_id AND bsi.status = 'active'
            WHERE s.id = :student_id
            GROUP BY s.id
        """)
        
        row = db.execute(query, {"student_id": student_id}).first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")

        # Fetch individual program rows for the programs table
        prog_rows = db.execute(text("""
            SELECT
                l.programid,
                l.gradeid,
                l.grade_type_id,
                l.shiftid,
                l.academicid,
                g.branch_id,
                pr.program_name,
                g.grade_name,
                gt.type_name AS grade_type,
                sh.shift_name,
                sh.shift_name_en
            FROM learning l
            LEFT JOIN program pr ON l.programid = pr.id
            LEFT JOIN grade g ON l.gradeid = g.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN shift sh ON l.shiftid = sh.id
            WHERE l.studentid = :student_id
            ORDER BY pr.program_name
        """), {"student_id": student_id}).fetchall()

        programs_list = [
            {
                "program_id": r.programid,
                "grade_id": r.gradeid,
                "grade_type_id": r.grade_type_id,
                "shift_id": r.shiftid,
                "academic_id": r.academicid,
                "branch_id": r.branch_id,
                "program": r.program_name,
                "grade": r.grade_name,
                "grade_type": r.grade_type,
                "shift": r.shift_name_en or r.shift_name,
            }
            for r in prog_rows
        ]

        # Organize into sections
        return {
            "personal_info": {
                "id": row.student_id,
                "unique_id": row.studentid,
                "optional_id": row.optional_id,
                "k_name": row.kName,
                "e_name": row.eName,
                "gender": row.gender,
                "dob": row.dob.strftime("%d-%m-%Y") if row.dob else None,
                "age": _calculate_age(row.dob) if row.dob else None,
                "is_foreigner": bool(row.is_foreigner),
                "phone": row.student_phone,
                "previous_school": row.previousSchool,
                "address": ", ".join(filter(None, [row.village, row.commune, row.district, row.province])),
                "noted": row.student_noted,
                "child_order": row.child_order,
                "created_at": row.created_at.strftime("%Y-%m-%dT%H:%M:%S") if row.created_at else None,
            },
            "academic_info": {
                "branch_id": row.branch,
                "branch_name": row.branch_name,
                "academic_id": row.academic,
                "academic_name": row.academic_us_name or row.academic_name,
                "status_id": row.status_id,
                "status_name": row.status_name,
                "programs": row.student_learning,
                "program_count": row.program_count,
                "is_using_bus": bool(row.is_using_bus),
            },
            "programs": programs_list,
            "parent_info": {
                "parent_id": row.parent_id,
                "father_name": row.fatherName,
                "mother_name": row.motherName,
                "father_phone": row.fatherPhone,
                "mother_phone": row.motherPhone,
                "father_job": row.fatherJob,
                "mother_job": row.motherJob,
                "address": ", ".join(filter(None, [row.pVillage, row.pCommune, row.pDistrict, row.pProvince])),
                "email": row.pEmail,
                "telegram": row.pTelegramId,
            },
            "guardian_info": {
                "name": row.gName,
                "relation": row.gIsThe,
                "phone": row.gPhone,
                "address": ", ".join(filter(None, [row.gVillage, row.gCommune, row.gDistrict, row.gProvince])),
                "home_no": row.gHome,
                "street": row.gStreet,
                "group": row.gGroup,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching student detail: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while fetching details")


from pydantic import BaseModel

class StudentUpdate(BaseModel):
    khmer_name: Optional[str] = None
    english_name: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    phone: Optional[str] = None
    noted: Optional[str] = None

@router.put("/{student_id}")
async def update_student(student_id: int, update_data: StudentUpdate, db: Session = Depends(get_db)):
    """Update a student's basic personal information."""
    try:
        # Verify student exists
        check = db.execute(text("SELECT id FROM students WHERE id = :id"), {"id": student_id}).first()
        if not check:
            raise HTTPException(status_code=404, detail="Student not found")

        # Build update query
        updates = []
        params = {"id": student_id, "updated_at": "datetime('now')"} # Assuming SQLite or similar
        
        if update_data.khmer_name is not None:
            updates.append("kName = :khmer_name")
            params["khmer_name"] = update_data.khmer_name
        if update_data.english_name is not None:
            updates.append("eName = :english_name")
            params["english_name"] = update_data.english_name
        if update_data.gender is not None:
            updates.append("gender = :gender")
            params["gender"] = update_data.gender
        if update_data.dob is not None:
            updates.append("dob = :dob")
            params["dob"] = update_data.dob
        if update_data.phone is not None:
            updates.append("student_phone = :phone")
            params["phone"] = update_data.phone
        if update_data.noted is not None:
            updates.append("student_noted = :noted")
            params["noted"] = update_data.noted

        if not updates:
            return {"status": "success", "message": "No changes provided"}

        # We also need to update the updated_at timestamp. In MySQL it would be NOW(), in SQLite datetime('now')
        updates.append("updated_at = :updated_at")

        set_clause = ", ".join(updates)
        query = text(f"UPDATE students SET {set_clause} WHERE id = :id")
        
        # SQLite vs MySQL handled simply via string timestamp or builtin if possible
        import datetime
        params["updated_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        db.execute(query, params)
        db.commit()

        return {"status": "success", "message": "Student updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating student: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="An error occurred while updating student")




def _calculate_age(dob):
    if not dob:
        return 0
    import datetime
    today = datetime.date.today()
    if isinstance(dob, datetime.datetime):
        dob = dob.date()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return age
