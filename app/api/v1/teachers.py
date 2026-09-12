from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status
from sqlalchemy.orm import Session
from sqlalchemy import or_, text, func
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
import traceback
import logging

from ...core import get_db
from ...schemas import TeacherCreate, TeacherUpdate, TeacherResponse, TeacherWithClasses, TeacherClassSummary
from ...services import (
    create_teacher, get_teacher, get_teachers, update_teacher, 
    delete_teacher, get_teacher_by_teacher_id
)
from ...auth import get_current_active_user
from ...models import User, Teacher, DailyAttendance
from ...utils.academic_year import get_current_academic_id, is_historical_academic_year

router = APIRouter()
logger = logging.getLogger(__name__)

def _get_academic_id_from_settings(db: Session) -> Optional[int]:
    """
    Current academic year for teacher dashboards/reports.
    Delegates to the canonical resolver (academic.status=1 ->
    settings.academicid -> newest) so all modules agree on the year.
    """
    return get_current_academic_id(db)
    
@router.get("/dashboard/classes", response_model=List[TeacherClassSummary])
async def get_dashboard_classes(
    branch_id: Optional[int] = Query(None, description="Branch ID to filter by"),
    program_id: Optional[int] = Query(None, description="Program ID to filter by"),
    shift_id: Optional[int] = Query(None, description="Shift ID to filter by"),
    academic_id: Optional[int] = Query(None, description="Academic year ID to filter by"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID to filter by"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get classes for dashboard (Active classes/assignments), filtered by branch/program/academic/teacher."""
    try:
        # Get current academic year from settings if not provided
        active_academic_id = academic_id
        
        if active_academic_id is None:
            active_academic_id = _get_academic_id_from_settings(db)

        if active_academic_id is None:
             try:
                # Fallback to most recent
                latest_query = text("SELECT id FROM academic ORDER BY id DESC LIMIT 1")
                latest_res = db.execute(latest_query).fetchone()
                if latest_res:
                    active_academic_id = latest_res[0]
             except: pass
        
        logger.info(f"Dashboard Classes Debug: active_academic_id={active_academic_id}, teacher_id={teacher_id}")

        # Build Query - Undoing temporary 0 count, restoring logic
        query = text("""
            SELECT DISTINCT
                g.id as grade_id,
                g.grade_name,
                g.grade_name AS grade_code,
                g.program_id,
                p.program_name,
                p.short_code as program_short_code,
                b.id as branch_id,
                b.branch_name,
                ct.academic_id,
                ct.shift_id,
                s.shift_name,
                ay.academic_name as academic_year,
                gt.type_name as grade_type_name,
                ct.teacher_id,
                 (SELECT COUNT(*) FROM students st
                 JOIN learning l ON st.id = l.studentid
                 WHERE l.gradeid = g.id AND l.academicid = ct.academic_id
                 AND (st.status = 1 OR :historical = 1)) as student_count
            FROM class_teachers ct
            JOIN grade g ON ct.grade_id = g.id
            LEFT JOIN program p ON ct.program_id = p.id
            LEFT JOIN branch b ON ct.branch_id = b.id
            LEFT JOIN shift s ON ct.shift_id = s.id
            LEFT JOIN academic ay ON ct.academic_id = ay.id
            LEFT JOIN grade_type gt ON ct.grade_type_id = gt.id
            WHERE 1=1
        """ + (
            " AND ct.academic_id = :academic_id" if active_academic_id else ""
        ) + (
            " AND ct.branch_id = :branch_id" if branch_id else ""
        ) + (
            " AND ct.program_id = :program_id" if program_id else ""
        ) + (
            " AND ct.shift_id = :shift_id" if shift_id else ""
        ) + (
            " AND ct.teacher_id = :teacher_id" if teacher_id else ""
        ) + " ORDER BY g.grade_name")
        
        params = {}
        params['historical'] = (
            1 if active_academic_id and is_historical_academic_year(db, active_academic_id) else 0
        )
        if active_academic_id: params['academic_id'] = active_academic_id
        if branch_id: params['branch_id'] = branch_id
        if program_id: params['program_id'] = program_id
        if shift_id: params['shift_id'] = shift_id
        if teacher_id: params['teacher_id'] = teacher_id
        
        result = db.execute(query, params)
        
        classes = []
        for c_row in result:
             # Determine isActive (dynamic based on active_academic_id)
             is_active = False
             if active_academic_id and c_row.academic_id:
                  is_active = (c_row.academic_id == active_academic_id)
             elif not c_row.academic_id:
                  is_active = True # Fallback if no active_academic_id associated

             # Convert student_count to int safely
             s_count = 0
             if hasattr(c_row, 'student_count') and c_row.student_count is not None:
                 try:
                     s_count = int(c_row.student_count)
                 except: pass

             classes.append({
                'id': c_row.grade_id,
                'class_code': c_row.grade_code or '',
                'class_name': c_row.grade_name or '',
                'subject': c_row.program_name or c_row.branch_name or '', 
                'teacher_id': c_row.teacher_id,
                'semester': '',
                'academic_year': c_row.academic_year or '',
                'is_active': is_active,
                'branch_id': c_row.branch_id,
                'branch_name': c_row.branch_name,
                'program_id': c_row.program_id,
                'program_name': c_row.program_name,
                'program_short_code': c_row.program_short_code,
                'grade_id': c_row.grade_id,
                'grade_name': c_row.grade_name,
                'grade_type_name': c_row.grade_type_name,
                'shift_id': c_row.shift_id,
                'shift': c_row.shift_name,
                'academic_id': c_row.academic_id,
                'student_count': s_count, 
            })
            
        logger.info(f"Dashboard Classes: Found {len(classes)} classes for teacher {teacher_id}")
        return classes

    except Exception as e:
        logger.error(f"Error fetching dashboard classes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/me/pending-permissions")
async def get_my_pending_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns count of parent permission requests in daily_attendance that match
    the current teacher's classes (via class_teachers). Used by the app to show
    the hot event banner. Does not touch or replace notification logic.
    """
    try:
        teacher_id = current_user.id
        academic_id = _get_academic_id_from_settings(db)

        # Check if current user is an App Admin or Super Admin
        is_admin = False
        from app.models.organization import Role
        from app.models.app_admin import AppAdmin
        user_role = db.query(Role).filter(Role.id == current_user.role).first()
        if user_role and ("admin" in user_role.role_name.lower() or "super" in user_role.role_name.lower()):
            is_admin = True
        else:
            admin_check = db.query(AppAdmin).filter(AppAdmin.user_id == current_user.id).first()
            if admin_check:
                is_admin = True

        if not is_admin:
            # 1) Get this teacher's (program_id, grade_id, grade_type_id, shift_id) from class_teachers
            ct_query = text("""
                SELECT program_id, grade_id, grade_type_id, shift_id
                FROM class_teachers
                WHERE teacher_id = :teacher_id
                AND (academic_id = :academic_id OR :academic_id IS NULL)
            """)
            ct_result = db.execute(
                ct_query,
                {"teacher_id": teacher_id, "academic_id": academic_id},
            )
            teacher_classes = set()
            for row in ct_result:
                teacher_classes.add((row.program_id, row.grade_id, row.grade_type_id, row.shift_id))

            if not teacher_classes:
                return {"count": 0, "items": []}

        # 2) Pending permissions: daily_attendance where status = 'permission', created_by_type = 'parent'
        #    Current day only: once the day passes, it will not show (even if unread)
        today = date.today()
        perms = (
            db.query(DailyAttendance)
            .filter(
                DailyAttendance.status.ilike("%permission%"),
                DailyAttendance.created_by_type.ilike("parent"),
                DailyAttendance.attendance_date == today,
            )
            .all()
        )
        if is_admin:
            matched = perms
        else:
            matched = [
                p for p in perms
                if (p.program_id, p.grade_id, p.grade_type_id, p.shift_id) in teacher_classes
            ]
        if not matched:
            return {"count": 0, "items": []}

        ids = [p.id for p in matched]
        id_placeholders = ", ".join(str(i) for i in ids)
        enrich_query = text(f"""
            SELECT da.id, da.student_id, da.attendance_date, da.note,
                   COALESCE(
                        (SELECT NULLIF(TRIM(COALESCE(NULLIF(TRIM(p.fatherName),''), NULLIF(TRIM(p.motherName),''))),'')
                         FROM parents p WHERE FIND_IN_SET(da.student_id, p.myChilds) > 0 LIMIT 1),
                        'Parent') as parent_name,
                   TRIM(CONCAT(COALESCE(s.eName,''), ' ', COALESCE(s.kName,''))) as student_name,
                   COALESCE(g.grade_name,'') as grade_name,
                   COALESCE(gt.type_name,'') as grade_type_name
            FROM daily_attendance da
            LEFT JOIN students s ON da.student_id = s.id
            LEFT JOIN grade g ON da.grade_id = g.id
            LEFT JOIN grade_type gt ON da.grade_type_id = gt.id
            WHERE da.id IN ({id_placeholders})
        """)
        try:
            enrich_result = db.execute(enrich_query)
            rowmap = {r.id: r for r in enrich_result}
        except Exception:
            rowmap = {}

        items = []
        for p in matched:
            date_str = p.attendance_date.isoformat() if p.attendance_date is not None else ""
            r = rowmap.get(p.id) if rowmap else None
            items.append({
                "id": p.id,
                "student_id": p.student_id,
                "attendance_date": date_str,
                "note": p.note,
                "parent_name": (r.parent_name or "").strip() or "Parent" if r else "Parent",
                "student_name": (r.student_name or "").strip() or "Student" if r else "Student",
                "grade_name": (r.grade_name or "").strip() if r else "",
                "grade_type_name": (r.grade_type_name or "").strip() if r else "",
            })
        return {"count": len(items), "items": items}
    except Exception as e:
        logger.exception("Error in get_my_pending_permissions")
        return {"count": 0, "items": []}


@router.get("/{teacher_id}/classes", response_model=TeacherWithClasses)
async def get_teacher_classes(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get a specific teacher by ID with their classes.
    Queries the Users table (role=2) to match read_teachers logic.
    """
    # 1. Fetch Teacher Details from Users table
    query = text("""
        SELECT DISTINCT
            u.id, u.uniqueId, u.eName as first_name, u.kName as last_name, u.email, u.phone,
            u.education as subject, u.departmentId, 
            u.startWork as hire_date, 
            0.0 as salary, 
            u.status as is_active,
            u.created_at, u.updated_at,
            u.workplace as branch_id,
            b.branch_name,
            u.departmentId,
            d.id as dept_id, d.department as dept_name, d.translate as dept_translate, d.code as dept_code,
            u.positionId,
            p.id as pos_id, p.position as pos_name, p.translate as pos_translate,
            (SELECT COUNT(DISTINCT ct_sub.id) FROM class_teachers ct_sub WHERE ct_sub.teacher_id = u.id) as class_count,
            u.kName, u.eName,
            u.gender, u.dob,
            u.isForeigner,
            u.username, u.height, u.nationality, u.religion,
            u.province, u.district, u.commune, u.village,
            u.pProvince, u.pDistrict, u.pCommune, u.pVillage,
            u.identityNumber, u.identityRegDate, u.identityEndDate, u.identityRegPlace,
            u.fatherName, u.motherName, u.startWork, u.endWork, u.telegramId, u.education,
            COALESCE(ur_teacher.avatar, ur_employee.avatar) as avatar
        FROM users u
        LEFT JOIN branch b ON u.workplace = b.id
        LEFT JOIN department d ON u.departmentId = d.id
        LEFT JOIN position p ON u.positionId = p.id
        LEFT JOIN users_resource ur_teacher ON u.id = ur_teacher.user_id AND ur_teacher.user_type = 'teacher'
        LEFT JOIN users_resource ur_employee ON u.id = ur_employee.user_id AND ur_employee.user_type = 'employee'
        WHERE u.id = :teacher_id
    """) # Removed u.role = 2 check to ensure we find the user if they exist, validation can happen later if needed
    
    result = db.execute(query, {"teacher_id": teacher_id})
    row = result.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Helper functions (duplicated from read_teachers for isolation)
    def format_date(val):
        if val is None: return None
        if isinstance(val, str): return val
        if hasattr(val, 'isoformat'): return val.isoformat()
        return str(val)

    def safe_get(row, index, default=None):
        try:
            if index < len(row):
                val = row[index]
                return val if val is not None else default
            return default
        except: return default

    # Map row to dictionary
    dept_id = safe_get(row, 16) or safe_get(row, 15) or safe_get(row, 7)
    dept_name = safe_get(row, 17)
    dept_translate = safe_get(row, 18)
    dept_code = safe_get(row, 19)
    
    pos_id = safe_get(row, 21) or safe_get(row, 20)
    pos_name = safe_get(row, 22)
    pos_translate = safe_get(row, 23)

    teacher_dict = {
        'id': safe_get(row, 0),
        'teacher_id': safe_get(row, 1) or '',
        'first_name': safe_get(row, 2) or '',
        'last_name': safe_get(row, 3) or '',
        'email': safe_get(row, 4) or '',
        'phone': safe_get(row, 5),
        'subject': safe_get(row, 6) or '',
        'department': dept_name or '',
        'hire_date': None,
        'salary': 0.0,
        'is_active': safe_get(row, 10) == 1,
        'created_at': format_date(safe_get(row, 11)),
        'updated_at': format_date(safe_get(row, 12)),
        'branch_id': safe_get(row, 13),
        'branch_name': safe_get(row, 14),
        'department_id': dept_id,
        'department_info': {
            'id': dept_id,
            'department': dept_name,
            'translate': dept_translate,
            'code': dept_code,
        } if dept_id is not None else None,
        'position_id': pos_id,
        'position_info': {
            'id': pos_id,
            'position': pos_name,
            'translate': pos_translate,
        } if pos_id is not None else None,
        'class_count': safe_get(row, 24, 0),
        'kName': safe_get(row, 25),
        'eName': safe_get(row, 26),
        'fullName': f"{safe_get(row, 26) or ''} {safe_get(row, 25) or ''}".strip(),
        'gender': safe_get(row, 27),
        'dob': format_date(safe_get(row, 28)),
        'isForeigner': safe_get(row, 29, 0),
        # Extra fields mapping
        'username': safe_get(row, 30),
        'height': safe_get(row, 31),
        'nationality': safe_get(row, 32),
        'religion': safe_get(row, 33),
        'province': safe_get(row, 34),
        'district': safe_get(row, 35),
        'commune': safe_get(row, 36),
        'village': safe_get(row, 37),
        'pProvince': safe_get(row, 38),
        'pDistrict': safe_get(row, 39),
        'pCommune': safe_get(row, 40),
        'pVillage': safe_get(row, 41),
        'identityNumber': safe_get(row, 42),
        'identityRegDate': format_date(safe_get(row, 43)),
        'identityEndDate': format_date(safe_get(row, 44)),
        'identityRegPlace': safe_get(row, 45),
        'fatherName': safe_get(row, 46),
        'motherName': safe_get(row, 47),
        'startWork': format_date(safe_get(row, 48)),
        'endWork': format_date(safe_get(row, 49)),
        'telegramId': safe_get(row, 50),
        'education': safe_get(row, 51),
        'avatar': safe_get(row, 52),
    }

    # 2. Fetch Classes
    # 2. Fetch Classes
    classes_query = text("""
        SELECT DISTINCT
            g.id as grade_id,
            g.grade_name,
            g.grade_name AS grade_code,
            g.program_id,
            p.program_name,
            p.short_code as program_short_code,
            b.id as branch_id,
            b.branch_name,
            ct.academic_id,
            ct.shift_id,
            s.shift_name,
            ay.academic_name as academic_year,
            ay.academic_us_name,
            gt.type_name as grade_type_name
        FROM class_teachers ct
        JOIN grade g ON ct.grade_id = g.id
        LEFT JOIN program p ON ct.program_id = p.id
        LEFT JOIN branch b ON ct.branch_id = b.id
        LEFT JOIN shift s ON ct.shift_id = s.id
        LEFT JOIN academic ay ON ct.academic_id = ay.id
        LEFT JOIN grade_type gt ON ct.grade_type_id = gt.id
        WHERE ct.teacher_id = :teacher_id
        ORDER BY g.grade_name
    """)
    
    classes_result = db.execute(classes_query, {"teacher_id": teacher_id})
    classes = []

    # Current academic year via the canonical resolver (previously this
    # mistakenly read attendance_system_settings.id — a settings-row PK,
    # not an academic year).
    active_academic_id = get_current_academic_id(db)
    logger.info(f"Active Academic ID determined as: {active_academic_id}")

    
    for c_row in classes_result:
        # Determine if class is active based on current academic year
        is_class_active = False
        if active_academic_id and c_row.academic_id:
             is_class_active = (c_row.academic_id == active_academic_id)
        elif not c_row.academic_id:
             # If class has no academic_id, assume active? Or inactive? 
             # Usually classes should have academic_id. If missing, maybe it's timeless? 
             # Let's assume True if we can't determine, or False? 
             # User said "make sure never duplicate load of comfuse". 
             is_class_active = True 
        # DEBUG: Log row keys/values for first class (REMOVED)


        classes.append({
            'id': c_row.grade_id,
            'classCode': c_row.grade_code or '',
            'className': c_row.grade_name or '',
            'subject': c_row.program_name or c_row.branch_name or '', 
            'teacherId': teacher_id,
            'semester': '',
            'academicYear': c_row.academic_year or '',
            'isActive': is_class_active,
            'branchId': c_row.branch_id,
            'branchName': c_row.branch_name,
            'programId': c_row.program_id,
            'programName': c_row.program_name,
            'programShortCode': c_row.program_short_code,
            'gradeId': c_row.grade_id,
            'gradeName': c_row.grade_name,
            'gradeTypeName': c_row.grade_type_name,
            'shiftId': c_row.shift_id,
            'shift': c_row.shift_name,
            'academic_id': c_row.academic_id,
            'academic_us_name': c_row.academic_us_name,
            'studentCount': 0,
        })
    
    teacher_dict['classes'] = classes
    teacher_dict['class_ids'] = [c['id'] for c in classes]
    teacher_dict['class_count'] = len(classes)
    
    # Debug log for missing fields
    logger.info(f"Teacher Detail Response for ID {teacher_id}: dob={teacher_dict.get('dob')}, startWork={teacher_dict.get('startWork')}, kName={teacher_dict.get('kName')}")
    
    return teacher_dict



@router.post("/", response_model=TeacherResponse)
async def create_new_teacher(
    teacher: TeacherCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a new teacher."""
    return create_teacher(db=db, teacher=teacher)

@router.get("/")
async def read_teachers(
    branch_id: Optional[int] = Query(None),
    status: Optional[int] = Query(None),  # 1 = active, 0 or other = inactive
    is_active: Optional[bool] = Query(None),  # Accept is_active for Flutter compatibility
    search: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=1000),  # Compromise: default 100, max 1000 for Flutter compatibility
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all teachers - CACHED for 2 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    
    # Generate cache key based on query parameters
    cache_key = generate_cache_key("teachers_list", branch_id, status, search, department, page, limit)
    
    # Try to get from cache
    cached_result = query_cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    try:
        # Convert is_active to status if status is not provided
        if status is None and is_active is not None:
            status = 1 if is_active else 0
        
        # SIMPLIFIED QUERY: Focus on Users table primarily for "Teachers = Users" requirement
        # We process filters cleanly to avoid duplication and complex joins that might inadvertently filter out users.
        
        # Base selection
        select_clause = """
            SELECT DISTINCT
                u.id, u.uniqueId, u.eName as first_name, u.kName as last_name, u.email, u.phone,
                u.education as subject, u.departmentId, 
                u.startWork as hire_date, 
                0.0 as salary, 
                u.status as is_active,
                u.created_at, u.updated_at,
                u.workplace as branch_id,
                b.branch_name,
                u.departmentId,
                d.id as dept_id, d.department as dept_name, d.translate as dept_translate, d.code as dept_code,
                u.positionId,
                p.id as pos_id, p.position as pos_name, p.translate as pos_translate,
                (SELECT COUNT(DISTINCT ct_sub.id) FROM class_teachers ct_sub WHERE ct_sub.teacher_id = u.id) as class_count,
                u.kName, u.eName,
                u.gender, u.dob,
                u.isForeigner,
                COALESCE(ur_teacher.avatar, ur_employee.avatar) as avatar
        """
        
        from_clause = """
            FROM users u
            LEFT JOIN branch b ON u.workplace = b.id
            LEFT JOIN department d ON u.departmentId = d.id
            LEFT JOIN position p ON u.positionId = p.id
            LEFT JOIN users_resource ur_teacher ON u.id = ur_teacher.user_id AND ur_teacher.user_type = 'teacher'
            LEFT JOIN users_resource ur_employee ON u.id = ur_employee.user_id AND ur_employee.user_type = 'employee'
        """
        
        where_conditions = [] # Removed u.role = 2 to list all users as per request
        params: Dict[str, Any] = {}
        
        # Apply filters
        # 1. Status
        if status is not None:
            if status == 1:
                where_conditions.append("u.status = 1")
            else:
                where_conditions.append("u.status != 1")
        else:
            where_conditions.append("u.status = 1")
            
        # 2. Branch (Strictly filter by Workplace as requested "teachers = users")
        if branch_id is not None:
            where_conditions.append("u.workplace = :branch_id")
            params["branch_id"] = branch_id
            
        # 3. Department
        if department is not None and department.strip():
            where_conditions.append("(d.department LIKE :department OR d.translate LIKE :department OR d.code LIKE :department)")
            params["department"] = f"%{department}%"
            
        # 4. Search
        if search is not None and search.strip():
            search_regex = f"%{search}%"
            where_conditions.append("""(
                u.eName LIKE :search OR 
                u.kName LIKE :search OR 
                u.email LIKE :search OR
                u.uniqueId LIKE :search OR
                u.education LIKE :search OR
                d.department LIKE :search OR
                d.translate LIKE :search OR
                p.position LIKE :search OR
                p.translate LIKE :search
            )""")
            params["search"] = search_regex

        # Construct WHERE clause
        where_clause = " WHERE " + " AND ".join(where_conditions)
        
        # Final Query Assembly
        # Added u.id to ORDER BY to ensure deterministic results across pages
        query = select_clause + from_clause + where_clause + " ORDER BY class_count DESC, u.eName ASC, u.id ASC"
        
        # Count Query Assembly
        base_count_query = "SELECT COUNT(DISTINCT u.id) " + from_clause + where_clause
        
        
        
        try:
            count_result = db.execute(text(base_count_query), params)
            total_count = count_result.scalar() or 0
        except Exception as count_error:
            logger.error(f"Count query error: {str(count_error)}")
            total_count = 0
            
        # Pagination
        final_query = query 
        offset = (page - 1) * limit
        final_query += " LIMIT :limit OFFSET :offset"
        params['limit'] = limit
        params['offset'] = offset
        
        try:
            result = db.execute(text(final_query), params)
            rows = result.fetchall()
        except Exception as query_error:
            logger.error(f"Query execution error: {str(query_error)}")
            raise HTTPException(status_code=500, detail=f"Database query error: {str(query_error)}")
        
        def format_date(val):
            if val is None:
                return None
            if isinstance(val, str):
                return val
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return str(val)
        
        def safe_get(row, index, default=None):
            try:
                if index < len(row):
                    val = row[index]
                    return val if val is not None else default
                return default
            except (IndexError, TypeError):
                return default
        
        if len(rows) > 0:
            pass

            
        teachers = []
        teacher_ids = set()
        for row in rows:
            try:
                teacher_id = safe_get(row, 0)
                if teacher_id:
                    teacher_ids.add(teacher_id)
            except:
                pass
        
        # Fetch classes for all teachers in one query
        classes_map = {}
        if teacher_ids:
            try:
                teacher_ids_list = list(teacher_ids)
                # Build query with tuple for IN clause
                if teacher_ids_list:
                    placeholders = ','.join([':id' + str(i) for i in range(len(teacher_ids_list))])
                    classes_query = f"""
                        SELECT DISTINCT
                            ct.teacher_id,
                            g.id as grade_id,
                            g.grade_name,
                            g.grade_name AS grade_code,
                            g.program_id,
                            p.program_name,
                            b.id as branch_id,
                            b.branch_name,
                            ct.academic_id,
                            ay.academic_us_name
                        FROM class_teachers ct
                        JOIN grade g ON ct.grade_id = g.id
                        LEFT JOIN program p ON g.program_id = p.id
                        LEFT JOIN branch b ON g.branch_id = b.id
                        LEFT JOIN academic ay ON ct.academic_id = ay.id
                        WHERE ct.teacher_id IN ({placeholders})
                        ORDER BY ct.teacher_id, g.grade_name
                    """
                    classes_params = {f'id{i}': tid for i, tid in enumerate(teacher_ids_list)}
                    classes_result = db.execute(text(classes_query), classes_params)
                    classes_rows = classes_result.fetchall()
                else:
                    classes_rows = []
                
                for class_row in classes_rows:
                    t_id = class_row[0]  # teacher_id
                    if t_id not in classes_map:
                        classes_map[t_id] = []
                    # Column order: teacher_id, grade_id, grade_name, grade_code, program_id, program_name, branch_id, branch_name
                    program_name = class_row[5] or ''
                    branch_name = class_row[7] or ''
                    classes_map[t_id].append({
                        'id': class_row[1],  # grade_id
                        'classCode': class_row[3] or '',  # grade_code
                        'className': class_row[2] or '',  # grade_name
                        'subject': program_name or branch_name or '',  # Use program or branch as subject
                        'academic_id': class_row[8],
                        'academic_us_name': class_row[9] if len(class_row) > 9 else None,
                        'description': None,
                        'credits': 0,
                        'maxStudents': 0,
                        'teacherId': t_id,
                        'semester': '',
                        'academicYear': '',
                        'isActive': True,
                        'createdAt': None,
                        'updatedAt': None,
                        'teacherName': None,
                        'studentCount': None,
                    })
            except Exception as classes_error:
                logger.error(f"Error fetching classes: {str(classes_error)}")
                # Continue without classes
        
        for row in rows:
            try:
                # Column mapping same as before but source is updated
                # 0: id, 1: uniqueId, 2: eName, 3: kName, 4: email, 5: phone
                # 6: education, 7: departmentId, 8: startWork, 9: salary, 10: status
                # 11: created_at, 12: updated_at, 13: branch_id, 14: branch_name
                # 15: departmentId, 16: dept_id, 17: name, 18: trans, 19: code
                # 20: positionId, 21: pos_id, 22: name, 23: trans
                # 24: class_count, 25: kName, 26: eName, 27: gender, 28: dob
                
                teacher_id = safe_get(row, 0)
                dept_id = safe_get(row, 16) or safe_get(row, 15) or safe_get(row, 7)
                dept_name = safe_get(row, 17)
                dept_translate = safe_get(row, 18)
                dept_code = safe_get(row, 19)
                department_value = dept_name or ''
                
                pos_id = safe_get(row, 21) or safe_get(row, 20)
                pos_name = safe_get(row, 22)
                pos_translate = safe_get(row, 23)
                
                # Get classes for this teacher
                teacher_classes = classes_map.get(teacher_id, [])
                class_ids = [c['id'] for c in teacher_classes]
                

                teacher = {
                    'id': teacher_id,
                    'teacher_id': safe_get(row, 1) or '',
                    'first_name': safe_get(row, 2) or '',
                    'last_name': safe_get(row, 3) or '',
                    'email': safe_get(row, 4) or '',
                    'phone': safe_get(row, 5),
                    'subject': safe_get(row, 6) or '',
                    'department': department_value,
                    'hire_date': format_date(safe_get(row, 8)),
                    'startWork': format_date(safe_get(row, 8)),
                    'salary': 0.0,
                    'is_active': safe_get(row, 10) == 1,
                    'created_at': format_date(safe_get(row, 11)),
                    'updated_at': format_date(safe_get(row, 12)),
                    'branch_id': safe_get(row, 13),
                    'branch_name': safe_get(row, 14),
                    'department_id': dept_id,
                    'department_info': {
                        'id': dept_id,
                        'department': dept_name,
                        'translate': dept_translate,
                        'code': dept_code,
                    } if dept_id is not None else None,
                    'position_id': pos_id,
                    'position_info': {
                        'id': pos_id,
                        'position': pos_name,
                        'translate': pos_translate,
                    } if pos_id is not None else None,
                    'dept_code': dept_code,
                    'class_count': safe_get(row, 24, 0),
                    'class_ids': class_ids,
                    'classes': teacher_classes,
                    'kName': safe_get(row, 25),
                    'eName': safe_get(row, 26),
                    'fullName': f"{safe_get(row, 26) or ''} {safe_get(row, 25) or ''}".strip(),
                    'gender': safe_get(row, 27),
                    'dob': format_date(safe_get(row, 28)),
                    'isForeigner': safe_get(row, 29, 0),
                    'avatar': safe_get(row, 30),
                }
                teachers.append(teacher)
            except Exception as row_error:
                logger.error(f"Error processing row: {str(row_error)}")
                continue
        
        total_pages = (total_count + limit - 1) // limit if total_count > 0 else 0
        has_next = page < total_pages
        has_previous = page > 1

        result = {
            'teachers': teachers,
            'total': total_count,
            'page': page,
            'limit': limit,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_previous': has_previous,
        }
        
        # Cache the result for 2 minutes (120 seconds)
        query_cache.set(cache_key, result, ttl=120)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_all_teachers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/dashboard/students")
async def get_dashboard_students_count(
    branch_id: Optional[int] = Query(None, description="Branch ID to filter by"),
    shift_id: Optional[int] = Query(None, description="Shift ID to filter by"),
    status: Optional[int] = Query(1, description="Status to filter by (1=active, 0=inactive, default=1)"),
    academic_id: Optional[int] = Query(None, description="Academic year ID to filter by"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID to filter by (for My Students view)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get total students count for dashboard, filtered by branch, status, and optionally teacher."""
    try:
        logger.info(f"Dashboard students count requested by user: {current_user.id} with filters: branch={branch_id}, status={status}, academic={academic_id}, teacher={teacher_id}")

        # Get current academic year from settings if not provided
        if academic_id is None:
            academic_id = _get_academic_id_from_settings(db)
            if academic_id is None or academic_id <= 0:
                logger.warning("No valid academic ID found from settings or query parameter. Using all academic years.")
                academic_id = None

        params: Dict[str, Any] = {}
        query_parts = ["SELECT COUNT(DISTINCT s.id) as total_students FROM students s"]
        join_parts = []
        where_parts = []

        # Historical years count past enrollees even if now deactivated
        historical = (
            academic_id is not None
            and is_historical_academic_year(db, academic_id)
        )

        # Status filter (required) - same logic as students API
        if status is not None:
            if status == 1:
                if historical:
                    where_parts.append("(s.status = 1 OR :historical = 1)")
                    params['historical'] = 1
                else:
                    where_parts.append("s.status = 1")
            else:
                where_parts.append("s.status != 1")
        elif not historical:
            # Default to active students (status = 1)
            where_parts.append("s.status = 1")

        # Branch filter (optional) - filter by students.branch directly (same as students API)
        if branch_id is not None:
            where_parts.append("CAST(s.branch AS UNSIGNED) = :branch_id")
            params['branch_id'] = branch_id

        # Academic year filter (optional) - join with learning table only if academic_id is specified
        # If teacher_id is provided, we MUST join learning to link students to teacher's classes
        if academic_id is not None or teacher_id is not None or shift_id is not None:
            join_parts.append("INNER JOIN learning l ON s.id = l.studentid")
            
            if academic_id is not None:
                where_parts.append("l.academicid = :academic_id")
                params['academic_id'] = academic_id
                
            if shift_id is not None:
                where_parts.append("l.shiftid = :shift_id")
                params['shift_id'] = shift_id
        
        # Teacher filter (optional)
        if teacher_id is not None:
            # Link learning records to class_teachers to find students in teacher's classes
            # Join class_teachers on matching academic, grade, program, shift
            join_parts.append("""
                INNER JOIN class_teachers ct ON 
                l.academicid = ct.academic_id AND 
                l.gradeid = ct.grade_id AND 
                l.programid = ct.program_id AND 
                l.shiftid = ct.shift_id
            """)
            where_parts.append("ct.teacher_id = :teacher_id")
            params['teacher_id'] = teacher_id

        full_query = " ".join(query_parts + list(dict.fromkeys(join_parts)) + (["WHERE"] + [" AND ".join(where_parts)] if where_parts else []))
        student_result = db.execute(text(full_query), params)
        student_row = student_result.fetchone()
        total_students = student_row[0] if student_row else 0

        logger.info(f"Total students found with filters: {total_students}")
        return {'count': total_students}

    except Exception as e:
        logger.error(f"Error fetching dashboard students count: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching students count: {str(e)}")



@router.get("/dashboard/teachers")
async def get_dashboard_teachers_count(
    branch_id: Optional[int] = Query(None, description="Branch ID to filter by"),
    program_id: Optional[int] = Query(None, description="Program ID to filter by"),
    status: Optional[int] = Query(1, description="Status to filter by (1=active, 0=inactive, default=1)"),
    academic_id: Optional[int] = Query(None, description="Academic year ID to filter by"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get total teachers count (assigned to classes in current academic year)."""
    try:


        # Get current academic year from parameter or settings
        if academic_id is None:
            academic_id = _get_academic_id_from_settings(db)
            if academic_id is None or academic_id <= 0:
                logger.warning("No valid academic ID found. Returning 0 teachers.")
                return {'count': 0}

        # Count DISTINCT teachers from class_teachers for the current academic year
        # Join with users to check active status and role
        
        params: Dict[str, Any] = {'academic_id': academic_id}
        
        query = """
            SELECT COUNT(DISTINCT ct.teacher_id) 
            FROM class_teachers ct
            INNER JOIN users u ON ct.teacher_id = u.id
            WHERE ct.academic_id = :academic_id
        """
        
        # Apply teacher status filter (default active)
        if status is not None:
             query += " AND u.status = :status"
             params['status'] = status
        else:
             query += " AND u.status = 1"

        # Apply branch filter (from class_teachers)
        if branch_id is not None:
            query += " AND ct.branch_id = :branch_id"
            params['branch_id'] = branch_id

        # Apply program filter (from class_teachers)
        if program_id is not None:
            query += " AND ct.program_id = :program_id"
            params['program_id'] = program_id

        result = db.execute(text(query), params)
        count = result.scalar() or 0
        

        return {'count': count}

    except Exception as e:
        logger.error(f"Error fetching dashboard teachers count: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.get("/dashboard/attendance")
async def get_dashboard_attendance_percentage(
    date_param: Optional[str] = Query(None, alias="date", description="Date in YYYY-MM-DD format (defaults to today)"),
    academic_id: Optional[int] = Query(None, description="Academic year ID to filter by"),
    branch_id: Optional[int] = Query(None, description="Branch ID to filter by"),
    program_id: Optional[int] = Query(None, description="Program ID to filter by"),
    shift_id: Optional[int] = Query(None, description="Shift ID to filter by"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID to filter by"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get attendance percentage for dashboard against current active students."""
    try:
        from datetime import date, datetime, timedelta



        # Parse date parameter or use today
        selected_date = date.today()
        today_str = selected_date.strftime('%Y-%m-%d')



        if date_param:
            try:
                # Handle different date formats that might come from the frontend
                if isinstance(date_param, str):
                    selected_date = datetime.strptime(date_param, '%Y-%m-%d').date()

                elif isinstance(date_param, (int, float)):
                    # If it's a timestamp, convert it
                    selected_date = datetime.fromtimestamp(date_param).date()
                    logger.info(f"Parsed timestamp {date_param} to {selected_date}")
                else:
                    # Try to convert to string first
                    date_str = str(date_param)
                    selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    logger.info(f"Parsed converted date '{date_str}' to {selected_date}")
                today_str = selected_date.strftime('%Y-%m-%d')
                logger.info(f"Final selected date for attendance: {today_str}")
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(f"Invalid date format '{date_param}' (type: {type(date_param)}), using today: {e}")
                # Invalid date format, use today
                today = date.today()
                today_str = today.strftime('%Y-%m-%d')
                logger.info(f"Falling back to today: {today_str}")
        else:
            # Use today if no date provided
            today = date.today()
            today_str = today.strftime('%Y-%m-%d')
            today = date.today()
            today_str = today.strftime('%Y-%m-%d')

        # Get current academic year
        current_academic_id = academic_id
        if current_academic_id is None or current_academic_id <= 0:
            current_academic_id = _get_academic_id_from_settings(db)

        # 1. Base Joins
        teacher_join_clause = ""
        not_marked_join_clause = ""
        
        # Initialize Query Params
        query_params = {
            'selected_date': today_str,
            'academic_id': current_academic_id,
            # Historical years include now-inactive students
            'historical': (
                1 if current_academic_id and is_historical_academic_year(db, current_academic_id) else 0
            ),
        }

        # Teacher Filter (Determine the JOINS logic first)
        if teacher_id is not None:
             teacher_join_clause = """
                 INNER JOIN class_teachers ct ON
                 da.academic_id = ct.academic_id AND
                 da.program_id = ct.program_id AND
                 da.grade_id = ct.grade_id AND
                 da.shift_id = ct.shift_id
                 AND ct.teacher_id = :teacher_id
             """

             not_marked_join_clause = """
                 INNER JOIN class_teachers ct ON
                 l.academicid = ct.academic_id AND
                 l.programid = ct.program_id AND
                 l.gradeid = ct.grade_id AND
                 l.shiftid = ct.shift_id
                 AND ct.teacher_id = :teacher_id
             """
             query_params['teacher_id'] = teacher_id


        # 1. Numerator: Count Present/Late Records ONLY (Exclude Permission/Absent)
        present_query = """
            SELECT COUNT(da.id)
            FROM daily_attendance da
            INNER JOIN students s ON da.student_id = s.id
            {teacher_join}
            WHERE DATE(da.attendance_date) = DATE(:selected_date)
            AND da.academic_id = :academic_id
            AND (s.status = 1 OR :historical = 1)
            AND da.status IN ('IsPresent', 'IsLate')
        """.format(teacher_join=teacher_join_clause)
        
        # 2. Total Marked Records (All statuses: Present, Late, Permission, Absent)
        marked_query = """
            SELECT COUNT(da.id)
            FROM daily_attendance da
            INNER JOIN students s ON da.student_id = s.id
            {teacher_join}
            WHERE DATE(da.attendance_date) = DATE(:selected_date)
            AND da.academic_id = :academic_id
            AND (s.status = 1 OR :historical = 1)
        """.format(teacher_join=teacher_join_clause)

        # 3. Not Marked Students (Heads)
        not_marked_query = """
            SELECT COUNT(DISTINCT s.id)
            FROM students s
            INNER JOIN learning l ON s.id = l.studentid
            {not_marked_join}
            WHERE (s.status = 1 OR :historical = 1)
            AND l.academicid = :academic_id
            AND NOT EXISTS (
                SELECT 1 FROM daily_attendance da 
                WHERE da.student_id = s.id 
                AND DATE(da.attendance_date) = DATE(:selected_date)
            )
        """.format(not_marked_join=not_marked_join_clause)


        # Dynamic Filters (Append *after* formatting joins)
        if branch_id is not None:
             present_query += " AND s.branch = :branch_id"
             marked_query += " AND s.branch = :branch_id"
             not_marked_query += " AND s.branch = :branch_id"
             query_params['branch_id'] = branch_id

        if program_id is not None:
             present_query += " AND da.program_id = :program_id"
             marked_query += " AND da.program_id = :program_id"
             not_marked_query += " AND l.programid = :program_id"
             query_params['program_id'] = program_id

        if shift_id is not None:
             present_query += " AND da.shift_id = :shift_id"
             marked_query += " AND da.shift_id = :shift_id"
             not_marked_query += " AND l.shiftid = :shift_id"
             query_params['shift_id'] = shift_id

        # Execute Queries
        present_count = db.execute(text(present_query), query_params).scalar() or 0
        marked_count = db.execute(text(marked_query), query_params).scalar() or 0
        not_marked_count = db.execute(text(not_marked_query), query_params).scalar() or 0



        # Final Calculation
        # Denominator = Total Marked Records + Not Marked Students
        # Matches Report Screen Logic where "Total Records" is the sum of breakdown.
        total_records = marked_count + not_marked_count
        present_records = present_count

        # Calculate attendance percentage
        attendance_percentage = 0.0
        if total_records > 0:
            attendance_percentage = (present_records / total_records) * 100



        return {
            'percentage': round(attendance_percentage, 1),
            'present_count': present_records,
            'total_students': total_records,
            'date': today_str,
            'academic_id': current_academic_id
        }

    except Exception as e:
        logger.error(f"Error fetching dashboard attendance: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error fetching attendance data: {str(e)}")

@router.get("/dashboard/reports/attendance")
async def get_attendance_report(
    start_date: str = Query(..., description="Start Date YYYY-MM-DD"),
    end_date: str = Query(..., description="End Date YYYY-MM-DD"),
    academic_id: Optional[int] = Query(None, description="Academic year ID"),
    branch_id: Optional[int] = Query(None, description="Branch ID"),
    program_id: Optional[int] = Query(None, description="Program ID"),
    shift_id: Optional[int] = Query(None, description="Shift ID"),
    grade_id: Optional[int] = Query(None, description="Grade ID"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID (My Classes filter)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed attendance report with status breakdown for a date range."""
    from datetime import datetime, timedelta
    try:
        # Validate dates
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            
        # Get current academic if not provided
        if academic_id is None or academic_id <= 0:
            academic_id = _get_academic_id_from_settings(db)

        params = {
            'start_date': start_date,
            'end_date': end_date,
            'academic_id': academic_id,
            # Historical years include now-inactive students
            'historical': 1 if academic_id and is_historical_academic_year(db, academic_id) else 0
        }

        # --- 1. Total Enrolled Students (The Denominator) ---
        # Note: Using students.branch for filtering to match C# logic (ControlStudentsByClass)
        # and checking learning table for academic year enrollment
        enrollment_base = """
            SELECT COUNT(DISTINCT l.studentid)
            FROM learning l
            INNER JOIN students s ON l.studentid = s.id
        """
        enrollment_joins = ""
        enrollment_where = "WHERE (s.status = 1 OR :historical = 1) AND l.academicid = :academic_id"

        if teacher_id:
             enrollment_joins += """
                 INNER JOIN class_teachers ct ON 
                 l.academicid = ct.academic_id AND 
                 l.gradeid = ct.grade_id AND 
                 l.programid = ct.program_id AND 
                 l.shiftid = ct.shift_id AND
                 COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
                 AND ct.teacher_id = :teacher_id
             """
             params['teacher_id'] = teacher_id

        if branch_id:
            enrollment_where += " AND s.branch = :branch_id"
            params['branch_id'] = branch_id
        if program_id:
            enrollment_where += " AND l.programid = :program_id"
            params['program_id'] = program_id
        if shift_id:
            enrollment_where += " AND l.shiftid = :shift_id"
            params['shift_id'] = shift_id
        if grade_id:
            enrollment_where += " AND l.gradeid = :grade_id"
            params['grade_id'] = grade_id

        enrollment_query = f"{enrollment_base} {enrollment_joins} {enrollment_where}"

        enrollment_result = db.execute(text(enrollment_query), params).fetchone()
        total_students = enrollment_result[0] if enrollment_result else 0


        # --- 2. Attendance Statistics (The Numerator) ---
        # Note: Using students.branch for filtering
        # --- 2. Attendance Statistics (The Numerator) ---
        # Note: Using students.branch for filtering
        attendance_base = """
            SELECT
                da.status,
                COUNT(DISTINCT da.id) as count
            FROM daily_attendance da
            INNER JOIN students s ON da.student_id = s.id
        """
        attendance_joins = ""
        attendance_where = """
            WHERE DATE(da.attendance_date) BETWEEN DATE(:start_date) AND DATE(:end_date)
            AND da.academic_id = :academic_id
            AND (s.status = 1 OR :historical = 1)
        """

        if teacher_id:
             # Filter by teacher's classes via JOIN
             attendance_joins += """
                 INNER JOIN class_teachers ct ON
                 da.academic_id = ct.academic_id AND
                 da.program_id = ct.program_id AND
                 da.grade_id = ct.grade_id AND
                 da.shift_id = ct.shift_id AND
                 COALESCE(da.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
                 AND ct.teacher_id = :teacher_id
             """
             params['teacher_id'] = teacher_id

        # Apply Filters
        if branch_id:
            attendance_where += " AND s.branch = :branch_id"
        
        if program_id:
            # Filter by the program recorded in attendance
            attendance_where += " AND da.program_id = :program_id"

        if shift_id:
            # Filter by the shift recorded in attendance
            attendance_where += " AND da.shift_id = :shift_id"

        if grade_id:
            # Filter by grade
            attendance_where += " AND da.grade_id = :grade_id"

        query_attendance = f"{attendance_base} {attendance_joins} {attendance_where} GROUP BY da.status"


        att_result = db.execute(text(query_attendance), params).fetchall()
        
        stats = {
            'IsPresent': 0, 'IsAbsent': 0, 'IsLate': 0, 'IsPermission': 0
        }

        total_marked = 0
        for row in att_result:
            status_val = row[0]
            count_val = row[1]
            if status_val in stats:
                stats[status_val] = count_val
            total_marked += count_val
            


        # --- 3. Not Marked Calculation ---
        not_marked = 0
        
        # Logic: "Not Marked" is strictly valid/useful for a Single Day (e.g., Today).
        # For date ranges, it's ambiguous because a student might be marked on some days but not others.
        # Aligning with C# ControlDashboard which is primarily a daily dashboard.
        if start_date == end_date:
            
            # Use strict C# logic: Active Students IN SCOPE who do NOT have an attendance record
            # Use strict C# logic: Active Students IN SCOPE who do NOT have an attendance record
            not_marked_base = """
                SELECT COUNT(DISTINCT l.studentid)
                FROM learning l
                INNER JOIN students s ON l.studentid = s.id
            """
            not_marked_joins = ""
            not_marked_where = """
                WHERE (s.status = 1 OR :historical = 1)
                AND l.academicid = :academic_id
            """
            
            if teacher_id:
                not_marked_joins += """
                 INNER JOIN class_teachers ct ON 
                 l.academicid = ct.academic_id AND 
                 l.gradeid = ct.grade_id AND 
                 l.programid = ct.program_id AND 
                 l.shiftid = ct.shift_id AND
                 COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
                 AND ct.teacher_id = :teacher_id
                """
                params['teacher_id'] = teacher_id

            # Apply scope filters to the BASE set of students
            if branch_id:
                not_marked_where += " AND s.branch = :branch_id"
            if program_id:
                not_marked_where += " AND l.programid = :program_id"
            if shift_id:
                not_marked_where += " AND l.shiftid = :shift_id"
            if grade_id:
                not_marked_where += " AND l.gradeid = :grade_id"

            not_marked_query = f"{not_marked_base} {not_marked_joins} {not_marked_where}"
                
            # NOT EXISTS clause: Check if they have an attendance record for this date
            not_marked_query += """
                AND NOT EXISTS (
                    SELECT 1
                    FROM daily_attendance da
                    WHERE da.student_id = l.studentid
                    AND da.program_id = l.programid
                    AND da.grade_id = l.gradeid
                    AND da.shift_id = l.shiftid
                    AND COALESCE(da.grade_type_id, -1) = COALESCE(l.grade_type_id, -1)
                    AND DATE(da.attendance_date) = DATE(:start_date)
            """
            
            # Important: The attendance record must match the scope too (if filtered)
            if program_id:
                not_marked_query += " AND da.program_id = :program_id"
            if shift_id:
                not_marked_query += " AND da.shift_id = :shift_id"
            if grade_id:
                not_marked_query += " AND da.grade_id = :grade_id"
                
            not_marked_query += ")"
            
            nm_result = db.execute(text(not_marked_query), params).fetchone()
            not_marked = nm_result[0] if nm_result else 0
            not_marked = nm_result[0] if nm_result else 0
            
        else:
            # For ranges, we just return 0 or a simple diff if acceptable, but usually UI hides it for ranges.
            # Using simple diff as fallback, though semantically weak for ranges.
            not_marked = max(0, total_students - total_marked) 
            # Using simple diff as fallback, though semantically weak for ranges.
            not_marked = max(0, total_students - total_marked)

        # --- 4. Trend Calculation ---
        # --- 4. Trend Calculation ---
        current_attendance_percent = 0.0
        
        # For percentage, we use Total Records (Marked + Not Marked) as the denominator
        # This matches the Home Screen and PDF Report logic.
        total_records = total_marked + not_marked
        if total_records > 0:
             # Sum of Present + Late (Exclude Permission)
            present_sum = stats['IsPresent'] + stats['IsLate']
            current_attendance_percent = (present_sum / total_records) * 100

        # Simplified trend: Just set to 0 for now to avoid complex queries in this iteration
        # unless specifically requested to fix trend logic too.
        attendance_trend = 0.0

        # --- 4. New Students Count ---
        # --- 4. New Students Count ---
        new_students_base = """
            SELECT COUNT(DISTINCT s.id)
            FROM students s
            LEFT JOIN learning l ON s.id = l.studentid
        """
        new_students_joins = ""
        new_students_where = """
            WHERE (s.status = 1 OR :historical = 1)
            AND DATE(s.created_at) BETWEEN DATE(:start_date) AND DATE(:end_date)
            AND l.academicid = :academic_id
        """

        if teacher_id:
             new_students_joins += """
                 INNER JOIN class_teachers ct ON 
                 l.academicid = ct.academic_id AND 
                 l.gradeid = ct.grade_id AND 
                 l.programid = ct.program_id AND 
                 l.shiftid = ct.shift_id AND
                 COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
                 AND ct.teacher_id = :teacher_id
             """
             params['teacher_id'] = teacher_id

        # (Simplified new student query logic remains similar, relying on params mostly)
        if branch_id:
            new_students_where += " AND CAST(s.branch AS UNSIGNED) = :branch_id"

        if program_id:
              new_students_where += " AND l.programid = :program_id"
        if shift_id:
              new_students_where += " AND l.shiftid = :shift_id"
        if grade_id:
              new_students_where += " AND l.gradeid = :grade_id"

        new_students_query = f"{new_students_base} {new_students_joins} {new_students_where}"

        # --- 4. New Students Count ---
        new_students_result = db.execute(text(new_students_query), params).fetchone()
        new_students_count = new_students_result[0] if new_students_result else 0

        # --- 4. Class-wise Breakdown ---
        # 4a. Get relevant classes based on filters
        classes_query = """
            SELECT 
                ct.id, 
                ct.teacher_id,
                u.kName, u.eName, 
                g.grade_name,
                s.shift_name,
                ct.program_id, ct.grade_id, ct.shift_id,
                p.program_name,
                p.short_code,
                gt.type_name,
                ct.branch_id,
                b.branch_name,
                u.isForeigner,
                ct.grade_type_id,
                u.phone
            FROM class_teachers ct
            LEFT JOIN users u ON ct.teacher_id = u.id
            LEFT JOIN grade g ON ct.grade_id = g.id
            LEFT JOIN shift s ON ct.shift_id = s.id
            LEFT JOIN program p ON ct.program_id = p.id
            LEFT JOIN grade_type gt ON ct.grade_type_id = gt.id
            LEFT JOIN branch b ON ct.branch_id = b.id
            WHERE ct.academic_id = :academic_id
        """
        classes_params = {'academic_id': academic_id}

        if branch_id:
            classes_query += " AND ct.branch_id = :branch_id"
            classes_params['branch_id'] = branch_id
        if program_id:
            classes_query += " AND ct.program_id = :program_id"
            classes_params['program_id'] = program_id
        if shift_id:
            classes_query += " AND ct.shift_id = :shift_id"
            classes_params['shift_id'] = shift_id
        if grade_id:
            classes_query += " AND ct.grade_id = :grade_id"
            classes_params['grade_id'] = grade_id
            
        if teacher_id:
            classes_query += " AND ct.teacher_id = :teacher_id"
            classes_params['teacher_id'] = teacher_id
            
        classes_query += " ORDER BY g.grade_name, s.shift_name"
        
        classes_result = db.execute(text(classes_query), classes_params).fetchall()
        
        single_day = (start_date == end_date)

        # --- OPTIMIZATION: Batched Queries ---
        
        # 4b. Batched Student Counts (Grouped by Program, Grade, Shift)
        # We need counts for ALL classes that might appear.
        # Since we filtered classes by branch/program/etc, we should filter this aggregation similarly.
        
        batch_stu_query = """
            SELECT 
                l.programid, l.gradeid, l.shiftid, l.grade_type_id, g.branch_id,
                COUNT(DISTINCT l.studentid)
            FROM learning l
            INNER JOIN students st ON l.studentid = st.id
            JOIN grade g ON l.gradeid = g.id
            WHERE l.academicid = :academic_id
            AND (st.status = 1 OR :historical = 1)
        """
        batch_stu_params = {
            'academic_id': academic_id,
            'historical': 1 if academic_id and is_historical_academic_year(db, academic_id) else 0,
        }
        
        if branch_id:
            batch_stu_query += " AND g.branch_id = :branch_id"
            batch_stu_params['branch_id'] = branch_id
        # Note: We don't filter by other params here strictly because a class might exist 
        # but we want to fetch the "universe" of combinations present in the classes_result.
        # However, for performance, applying same filters is safe because classes_result is also filtered.
        if program_id:
             batch_stu_query += " AND l.programid = :program_id"
             batch_stu_params['program_id'] = program_id
        if shift_id:
             batch_stu_query += " AND l.shiftid = :shift_id"
             batch_stu_params['shift_id'] = shift_id
        if grade_id:
             batch_stu_query += " AND l.gradeid = :grade_id"
             batch_stu_params['grade_id'] = grade_id
             
        batch_stu_query += " GROUP BY l.programid, l.gradeid, l.shiftid, l.grade_type_id, g.branch_id"
        
        stu_counts_res = db.execute(text(batch_stu_query), batch_stu_params).fetchall()
        
        # Map: (program_id, grade_id, shift_id, grade_type_id, branch_id) -> count
        stu_counts_map = {}
        for row in stu_counts_res:
            key = (row[0], row[1], row[2], row[3], row[4])
            stu_counts_map[key] = row[5]
            
        # 4c. Batched Attendance Stats (Grouped by Program, Grade, Shift, Status)
        batch_att_query = """
            SELECT 
                da.program_id, da.grade_id, da.shift_id, da.grade_type_id, g.branch_id, da.status,
                COUNT(DISTINCT da.id)
            FROM daily_attendance da
            INNER JOIN students st ON da.student_id = st.id
            JOIN grade g ON da.grade_id = g.id
            WHERE da.academic_id = :academic_id
            AND DATE(da.attendance_date) BETWEEN DATE(:start_date) AND DATE(:end_date)
        """
        batch_att_params = {
            'academic_id': academic_id,
            'start_date': start_date,
            'end_date': end_date
        }
        if branch_id:
            batch_att_query += " AND g.branch_id = :branch_id"
            batch_att_params['branch_id'] = branch_id
        if program_id:
            batch_att_query += " AND da.program_id = :program_id"
            batch_att_params['program_id'] = program_id
        if shift_id:
            batch_att_query += " AND da.shift_id = :shift_id"
            batch_att_params['shift_id'] = shift_id
        if grade_id:
            batch_att_query += " AND da.grade_id = :grade_id"
            batch_att_params['grade_id'] = grade_id
            
        batch_att_query += " GROUP BY da.program_id, da.grade_id, da.shift_id, da.grade_type_id, g.branch_id, da.status"
        
        att_stats_res = db.execute(text(batch_att_query), batch_att_params).fetchall()
        
        # Map: (program_id, grade_id, shift_id, grade_type_id, branch_id) -> {status: count, total_marked: sum}
        att_stats_map = {}
        for row in att_stats_res:
            key = (row[0], row[1], row[2], row[3], row[4])
            status = row[5]
            count = row[6]
            
            if key not in att_stats_map:
                att_stats_map[key] = {'stats': {'IsPresent': 0, 'IsAbsent': 0, 'IsLate': 0, 'IsPermission': 0}, 'total': 0}
            
            if status in att_stats_map[key]['stats']:
                att_stats_map[key]['stats'][status] = count
            att_stats_map[key]['total'] += count

        # --- Build Result List ---
        # Calculate teaching days in the range (excluding Sundays and holidays)
        from datetime import timedelta
        
        h_query = text("SELECT date FROM holidays WHERE date BETWEEN :start AND :end")
        holidays_res = db.execute(h_query, {"start": start_date, "end": end_date}).fetchall()
        holiday_dates = {h[0] for h in holidays_res}
        
        teaching_days = 0
        curr_d = s_date
        while curr_d <= e_date:
            if curr_d.weekday() != 6 and curr_d not in holiday_dates:  # 6 is Sunday
                teaching_days += 1
            curr_d += timedelta(days=1)
        if teaching_days == 0:
            teaching_days = 1

        classes_breakdown = []
        for row in classes_result:
            c_program_id = row[6]
            c_grade_id = row[7]
            c_shift_id = row[8]
            c_grade_type_id = row[15] if len(row) > 15 else None
            c_branch_id = row[12] if len(row) > 12 else None
            
            key = (c_program_id, c_grade_id, c_shift_id, c_grade_type_id, c_branch_id)
            
            # Lookup Student Count
            c_total_students_base = stu_counts_map.get(key, 0)
            c_expected_records = c_total_students_base * teaching_days
            
            # Lookup Stats
            c_data = att_stats_map.get(key, {'stats': {'IsPresent': 0, 'IsAbsent': 0, 'IsLate': 0, 'IsPermission': 0}, 'total': 0})
            c_stats = c_data['stats']
            c_total_marked = c_data['total']
            
            # Calculate Not Marked
            c_not_marked = max(0, c_expected_records - c_total_marked)
            
            # Retrieve isForeigner from the last column (index 14)
            is_foreigner = row[14] if len(row) > 14 else None
            k_name = row[2]
            e_name = row[3]
            
            teacher_name = "Unknown"
            
            if is_foreigner == 1:
                teacher_name = k_name if k_name else (e_name if e_name else "Unknown")
            elif is_foreigner == 2:
                teacher_name = e_name if e_name else (k_name if k_name else "Unknown")
            else:
                teacher_name = k_name if k_name else (e_name if e_name else "Unknown")

            classes_breakdown.append({
                "className": f"{row[4]} ({row[5]})",
                "gradeName": row[4],
                "shiftName": row[5],
                "programName": row[9] if len(row) > 9 else "",
                "short_code": row[10] if len(row) > 10 else "",
                "gradeTypeName": row[11] if len(row) > 11 else "",
                "teacherName": teacher_name,
                "teacherPhone": row[16] if len(row) > 16 else "",
                "totalStudents": c_total_students_base,
                "present": c_stats['IsPresent'],
                "absent": c_stats['IsAbsent'],
                "late": c_stats['IsLate'],
                "permission": c_stats['IsPermission'],
                "notMarked": c_not_marked,
                # IDs for navigation
                "programId": c_program_id,
                "gradeId": c_grade_id,
                "shiftId": c_shift_id,
                "gradeTypeId": c_grade_type_id,
                "branchId": row[12] if len(row) > 12 else 0,
                "branchName": row[13] if len(row) > 13 else ""
            })

        # --- Fix Percentage Calculation ---
        # Old (Wrong for ranges): (Present + Late + Permission) / Total Students
        # New (Correct for ranges): (Present + Late + Permission) / Total Marked Records
        # If Total Marked is 0, we can fall back to 0 or use Total Students if it's a single day.
        
        # Using the value calculated earlier (based on Total Records = Marked + Not Marked)
        # to ensure consistency with Home Screen.
        pass

        return {
            'summary': {
                'total_students': total_students,
                'attendance_percentage': round(current_attendance_percent, 1),
                'total_records': total_marked,
                'new_students_count': new_students_count,
                'attendance_trend': round(attendance_trend, 1)
            },
            'breakdown': {
                'present': stats['IsPresent'],
                'absent': stats['IsAbsent'],
                'late': stats['IsLate'],
                'permission': stats['IsPermission'],
                'not_marked': not_marked
            },
            'classes_breakdown': classes_breakdown
        }
        
    except Exception as e:
        logger.error(f"Error generating attendance report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboard/reports/attendance/students")
async def get_attendance_report_students(
    start_date: str = Query(..., description="Start Date YYYY-MM-DD"),
    end_date: str = Query(..., description="End Date YYYY-MM-DD"),
    academic_id: Optional[int] = Query(None, description="Academic year ID"),
    branch_id: Optional[int] = Query(None, description="Branch ID"),
    program_id: Optional[int] = Query(None, description="Program ID"),
    shift_id: Optional[int] = Query(None, description="Shift ID"),
    grade_id: Optional[int] = Query(None, description="Grade ID"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID (My Classes filter)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed student list for attendance report (filtered to Absent, Permission, Not Marked)."""
    from datetime import datetime
    try:
        # Validate dates
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            
        # Get current academic if not provided
        if academic_id is None or academic_id <= 0:
            academic_id = _get_academic_id_from_settings(db)
            
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'academic_id': academic_id,
            # Historical years include now-inactive students
            'historical': 1 if academic_id and is_historical_academic_year(db, academic_id) else 0
        }

        # Query to get enrolled students within the scope
        query_base = """
            SELECT DISTINCT 
                s.id as student_id,
                s.kName as k_name,
                s.eName as e_name,
                s.gender,
                g.grade_name,
                sh.shift_name,
                da.status as attendance_status,
                da.note,
                gt.type_name,
                ur.avatar
            FROM learning l
            INNER JOIN students s ON l.studentid = s.id
            LEFT JOIN grade g ON l.gradeid = g.id
            LEFT JOIN shift sh ON l.shiftid = sh.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN users_resource ur ON s.id = ur.user_id AND ur.user_type = 'student'
        """

        # Join with daily_attendance
        query_joins = """
            LEFT JOIN daily_attendance da ON l.studentid = da.student_id 
                AND l.programid = da.program_id
                AND l.gradeid = da.grade_id
                AND l.shiftid = da.shift_id
                AND COALESCE(l.grade_type_id, -1) = COALESCE(da.grade_type_id, -1)
                AND DATE(da.attendance_date) BETWEEN DATE(:start_date) AND DATE(:end_date)
                AND da.academic_id = :academic_id
        """

        query_where = "WHERE (s.status = 1 OR :historical = 1) AND l.academicid = :academic_id"

        if teacher_id:
             query_joins += """
                 INNER JOIN class_teachers ct ON 
                 l.academicid = ct.academic_id AND 
                 l.gradeid = ct.grade_id AND 
                 l.programid = ct.program_id AND 
                 l.shiftid = ct.shift_id AND
                 COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
                 AND ct.teacher_id = :teacher_id
             """
             params['teacher_id'] = teacher_id

        if branch_id:
            query_where += " AND g.branch_id = :branch_id"
            params['branch_id'] = branch_id
        if program_id:
            query_where += " AND l.programid = :program_id"
            params['program_id'] = program_id
        if shift_id:
            query_where += " AND l.shiftid = :shift_id"
            params['shift_id'] = shift_id
        if grade_id:
            query_where += " AND l.gradeid = :grade_id"
            params['grade_id'] = grade_id

        # ONLY INCLUDE Absent, Permission, or Not Marked (NULL)
        query_where += " AND (da.status IN ('IsAbsent', 'IsPermission') OR da.id IS NULL)"

        full_query = f"{query_base} {query_joins} {query_where} ORDER BY g.grade_name, sh.shift_name, s.eName"

        result = db.execute(text(full_query), params).fetchall()

        students = []
        for row in result:
            student_id = row[0]
            k_name = row[1] or ""
            e_name = row[2] or ""
            gender = row[3] or ""
            grade_name = row[4] or ""
            shift_name = row[5] or ""
            attendance_status = row[6]
            db_note = row[7] or ""
            type_name = row[8] or ""
            avatar = row[9] or ""

            # Standardize Not Marked
            if not attendance_status:
                attendance_status = "Not Marked"
            
            note = ""
            if attendance_status in ["IsPermission", "IsAbsent"]:
                note = db_note

            class_name_parts = filter(bool, [grade_name, type_name])
            formatted_class_name = f"{' - '.join(class_name_parts)}"

            students.append({
                "student_id": student_id,
                "k_name": k_name,
                "e_name": e_name,
                "gender": gender,
                "className": formatted_class_name,
                "grade_name": grade_name,
                "shift_name": shift_name,
                "status": attendance_status,
                "note": note,
                "avatar": avatar,
            })

        return {"students": students}

    except Exception as e:
        logger.error(f"Error getting attendance report students: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/reports/attendance/monthly-full-marked")
async def get_monthly_full_marked_attendance_report(
    start_date: str = Query(..., description="Start Date YYYY-MM-DD"),
    end_date: str = Query(..., description="End Date YYYY-MM-DD"),
    academic_id: Optional[int] = Query(None, description="Academic year ID"),
    branch_id: Optional[int] = Query(None, description="Branch ID"),
    program_id: Optional[int] = Query(None, description="Program ID"),
    shift_id: Optional[int] = Query(None, description="Shift ID"),
    grade_id: Optional[int] = Query(None, description="Grade ID"),
    teacher_id: Optional[int] = Query(None, description="Teacher ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Monthly matrix report:
    - Each teaching day column = 1 when class has full attendance marked (no missing rows)
    - Total column = full_marked_days / teaching_days
    """
    from datetime import datetime, timedelta
    try:
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        if academic_id is None or academic_id <= 0:
            academic_id = _get_academic_id_from_settings(db)

        # Teaching days: exclude Sundays and holidays
        h_query = text("SELECT date FROM holidays WHERE date BETWEEN :start AND :end")
        holidays_res = db.execute(h_query, {"start": start_date, "end": end_date}).fetchall()
        holiday_dates = {h[0] for h in holidays_res}

        teaching_dates = []
        d = s_date
        while d <= e_date:
            if d.weekday() != 6 and d not in holiday_dates:
                teaching_dates.append(d)
            d += timedelta(days=1)

        # Relevant classes in scope
        cls_query = """
            SELECT
                ct.teacher_id,
                u.kName, u.eName, u.isForeigner,
                ct.program_id, ct.grade_id, ct.shift_id, ct.grade_type_id, ct.branch_id,
                p.program_name,
                g.grade_name,
                gt.type_name,
                s.shift_name,
                b.branch_name
            FROM class_teachers ct
            LEFT JOIN users u ON ct.teacher_id = u.id
            LEFT JOIN program p ON ct.program_id = p.id
            LEFT JOIN grade g ON ct.grade_id = g.id
            LEFT JOIN grade_type gt ON ct.grade_type_id = gt.id
            LEFT JOIN shift s ON ct.shift_id = s.id
            LEFT JOIN branch b ON ct.branch_id = b.id
            WHERE ct.academic_id = :academic_id
        """
        cls_params = {"academic_id": academic_id}
        if teacher_id:
            cls_query += " AND ct.teacher_id = :teacher_id"
            cls_params["teacher_id"] = teacher_id
        if branch_id:
            cls_query += " AND ct.branch_id = :branch_id"
            cls_params["branch_id"] = branch_id
        if program_id:
            cls_query += " AND ct.program_id = :program_id"
            cls_params["program_id"] = program_id
        if shift_id:
            cls_query += " AND ct.shift_id = :shift_id"
            cls_params["shift_id"] = shift_id
        if grade_id:
            cls_query += " AND ct.grade_id = :grade_id"
            cls_params["grade_id"] = grade_id
        cls_query += " ORDER BY p.program_name, b.branch_name, s.shift_name, g.grade_name"
        classes_res = db.execute(text(cls_query), cls_params).fetchall()

        # Total students per class key
        stu_query = """
            SELECT
                l.programid, l.gradeid, l.shiftid, l.grade_type_id, g.branch_id,
                COUNT(DISTINCT l.studentid) AS total_students
            FROM learning l
            INNER JOIN students st ON l.studentid = st.id
            INNER JOIN grade g ON l.gradeid = g.id
            WHERE l.academicid = :academic_id
              AND (st.status = 1 OR :historical = 1)
        """
        stu_params = {
            "academic_id": academic_id,
            "historical": 1 if academic_id and is_historical_academic_year(db, academic_id) else 0,
        }
        if branch_id:
            stu_query += " AND g.branch_id = :branch_id"
            stu_params["branch_id"] = branch_id
        if program_id:
            stu_query += " AND l.programid = :program_id"
            stu_params["program_id"] = program_id
        if shift_id:
            stu_query += " AND l.shiftid = :shift_id"
            stu_params["shift_id"] = shift_id
        if grade_id:
            stu_query += " AND l.gradeid = :grade_id"
            stu_params["grade_id"] = grade_id
        stu_query += " GROUP BY l.programid, l.gradeid, l.shiftid, l.grade_type_id, g.branch_id"
        stu_res = db.execute(text(stu_query), stu_params).fetchall()
        stu_map = {(r[0], r[1], r[2], r[3], r[4]): int(r[5] or 0) for r in stu_res}

        # Marked attendance count per day / class key
        att_query = """
            SELECT
                DATE(da.attendance_date) AS d,
                da.program_id, da.grade_id, da.shift_id, da.grade_type_id, g.branch_id,
                COUNT(DISTINCT da.student_id) AS marked_students
            FROM daily_attendance da
            INNER JOIN students st ON da.student_id = st.id
            INNER JOIN grade g ON da.grade_id = g.id
            WHERE da.academic_id = :academic_id
              AND DATE(da.attendance_date) BETWEEN DATE(:start_date) AND DATE(:end_date)
              AND (st.status = 1 OR :historical = 1)
        """
        att_params = {
            "academic_id": academic_id,
            "start_date": start_date,
            "end_date": end_date,
            "historical": 1 if academic_id and is_historical_academic_year(db, academic_id) else 0,
        }
        if branch_id:
            att_query += " AND g.branch_id = :branch_id"
            att_params["branch_id"] = branch_id
        if program_id:
            att_query += " AND da.program_id = :program_id"
            att_params["program_id"] = program_id
        if shift_id:
            att_query += " AND da.shift_id = :shift_id"
            att_params["shift_id"] = shift_id
        if grade_id:
            att_query += " AND da.grade_id = :grade_id"
            att_params["grade_id"] = grade_id
        att_query += """
            GROUP BY DATE(da.attendance_date), da.program_id, da.grade_id, da.shift_id, da.grade_type_id, g.branch_id
        """
        att_res = db.execute(text(att_query), att_params).fetchall()
        att_map = {}
        for r in att_res:
            key = (r[1], r[2], r[3], r[4], r[5], r[0])
            att_map[key] = int(r[6] or 0)

        classes = []
        for row in classes_res:
            is_foreigner = row[3]
            k_name = row[1]
            e_name = row[2]
            if is_foreigner == 2:
                teacher_name = e_name or k_name or "Unknown"
            else:
                teacher_name = k_name or e_name or "Unknown"

            c_program_id = row[4]
            c_grade_id = row[5]
            c_shift_id = row[6]
            c_grade_type_id = row[7]
            c_branch_id = row[8]
            class_key = (c_program_id, c_grade_id, c_shift_id, c_grade_type_id, c_branch_id)
            total_students = stu_map.get(class_key, 0)

            grade_name = row[10] or ""
            type_name = row[11] or ""
            class_name = f"{grade_name} ({type_name})" if type_name else grade_name

            daily_marks = {}
            full_days = 0
            for td in teaching_dates:
                marked = att_map.get((c_program_id, c_grade_id, c_shift_id, c_grade_type_id, c_branch_id, td), 0)
                is_full = 1 if total_students > 0 and marked >= total_students else 0
                daily_marks[str(td)] = is_full
                if is_full == 1:
                    full_days += 1

            classes.append({
                "teacherName": teacher_name,
                "className": class_name,
                "gradeName": grade_name,
                "gradeTypeName": type_name,
                "programName": row[9] or "",
                "shiftName": row[12] or "",
                "branchName": row[13] or "",
                "totalStudents": total_students,
                "dailyMarks": daily_marks,
                "fullMarkedDays": full_days,
                "teachingDays": len(teaching_dates),
            })

        return {
            "start_date": start_date,
            "end_date": end_date,
            "teaching_dates": [str(d) for d in teaching_dates],
            "classes": classes,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating monthly full-marked report: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{teacher_id}", response_model=TeacherResponse)
async def read_teacher(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific teacher by ID."""
    db_teacher = get_teacher(db=db, teacher_id=teacher_id)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher

@router.get("/by-teacher-id/{teacher_id}", response_model=TeacherResponse)
async def read_teacher_by_teacher_id(
    teacher_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a specific teacher by teacher ID."""
    db_teacher = get_teacher_by_teacher_id(db=db, teacher_id=teacher_id)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher



@router.put("/{teacher_id}", response_model=TeacherResponse)
async def update_teacher_info(
    teacher_id: int,
    teacher_update: TeacherUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update teacher information."""
    db_teacher = update_teacher(db=db, teacher_id=teacher_id, teacher_update=teacher_update)
    if db_teacher is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return db_teacher

@router.delete("/{teacher_id}")
async def delete_teacher_info(
    teacher_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Delete a teacher (soft delete)."""
    success = delete_teacher(db=db, teacher_id=teacher_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )
    return {"message": "Teacher deleted successfully"}

@router.get("/search/{search_term}", response_model=List[TeacherResponse])
async def search_teachers(
    search_term: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Search teachers by name, email, or teacher_id."""
    teachers = db.query(Teacher).filter(
        or_(
            Teacher.first_name.ilike(f"%{search_term}%"),
            Teacher.last_name.ilike(f"%{search_term}%"),
            Teacher.email.ilike(f"%{search_term}%"),
            Teacher.teacher_id.ilike(f"%{search_term}%")
        )
    ).all()
    
    return teachers

@router.get("/by-subject/{subject}", response_model=List[TeacherResponse])
async def get_teachers_by_subject(
    subject: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get teachers by subject."""
    teachers = db.query(Teacher).filter(Teacher.subject.ilike(f"%{subject}%")).all()
    return teachers

@router.get("/by-department/{department}", response_model=List[TeacherResponse])
async def get_teachers_by_department(
    department: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get teachers by department."""
    teachers = db.query(Teacher).filter(Teacher.department.ilike(f"%{department}%")).all()
    return teachers

@router.get("/departments/all")
async def get_all_departments(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all departments for filter dropdown."""
    try:
        query = """
            SELECT id, department, translate, code, created_at, updated_at
            FROM department
            ORDER BY department ASC
        """
        result = db.execute(text(query))
        rows = result.fetchall()
        
        departments = []
        for row in rows:
            departments.append({
                'id': row[0],
                'department': row[1] or '',
                'translate': row[2] or '',
                'code': row[3] or '',
                'created_at': row[4].isoformat() if row[4] else None,
                'updated_at': row[5].isoformat() if row[5] else None,
            })
        
        return departments
    except Exception as e:
        logger.error(f"Error fetching departments: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error fetching departments: {str(e)}")

@router.get("/positions/all")
async def get_all_positions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all positions for filter dropdown."""
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
