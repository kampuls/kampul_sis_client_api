from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import traceback
import logging

from ...core import get_db
from ...auth import get_current_active_user
from ...models import Student, Parent
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

# Schema for Student Registration
class StudentRegisterRequest(BaseModel):
    kName: str
    eName: str
    gender: str
    dob: date
    image: Optional[str] = None  # Base64 string
    student_phone: Optional[str] = None
    is_foreigner: int = 1
    province: str
    district: str
    commune: str
    village: str
    previousSchool: Optional[str] = None
    leaveDate: Optional[date] = None
    child_order: int = 1
    academic: str  # ID as string
    branch: str  # ID as string
    status: int = 1
    student_noted: Optional[str] = None
    # registration | pending_approval — limits for unapproved parents
    add_phase: Optional[str] = None

    # Parent Linking
    # If registered by a parent, we get parent_id from token.
    # But if registered by admin, they might provide parent_id?
    # For this specific flow (Parent App), we rely on the token.


@router.get("/students")
async def get_all_students(
    branch_id: Optional[int] = Query(None),
    status: Optional[int] = Query(None),  # 1 = active, 0 or other = inactive (defaults to 1 in code if None)
    search: Optional[str] = Query(None),
    academic_id: Optional[int] = Query(None, description="Only students enrolled (learning row) in this academic year"),
    page: int = Query(1, ge=1),
    # Allow larger page sizes to match Flutter client which uses limit=1000
    limit: int = Query(100, ge=1, le=1000),  # Compromise: default 100, max 1000 for Flutter compatibility
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all students - CACHED for 2 minutes"""
    from ...services.query_cache import query_cache, generate_cache_key
    from ...utils.academic_year import is_historical_academic_year

    # Historical years must include now-inactive students, otherwise past
    # rosters look empty (their students were deactivated since).
    historical = (
        academic_id is not None
        and is_historical_academic_year(db, academic_id)
    )

    # Generate cache key based on query parameters (academic_id changes results!)
    cache_key = generate_cache_key("students_list", branch_id, status, search, page, limit, academic_id)
    
    # Try to get from cache
    cached_result = query_cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    try:
        
        # Base query: students only, optional join to branch for name
        # NOTE: We intentionally avoid loading heavy/sensitive fields (e.g. image)
        # here to improve list performance. Those can be fetched via the
        # get_student_by_id detail endpoint when needed.
        query = """
            SELECT 
                s.id, s.studentid, s.optional_id, NULL as username,
                s.kName, s.eName, s.gender, s.dob, ur.avatar as image,
                s.student_phone, s.is_foreigner, s.province, s.district,
                s.commune, s.village, s.previousSchool, s.leaveDate,
                s.myparents, s.child_order, s.academic, s.branch, s.status,
                NULL as student_noted, s.created_at, s.updated_at,
                b.branch_name,
                TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age,
                s.pickup_audio_url
            FROM students s
            LEFT JOIN branch b ON b.id = s.branch
            LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
            WHERE 1=1
        """
        
        params: Dict[str, Any] = {}
        
        # Apply status filter (default to 1 = active if not specified).
        # For historical years the default-active filter is skipped so
        # past enrollees who have since left still appear.
        if status is not None:
            if status == 1:
                query += " AND s.status = 1"
            else:
                query += " AND s.status != 1"
        elif not historical:
            # Default to active (status = 1) if not specified
            query += " AND s.status = 1"

        # Only students enrolled in the requested academic year
        if academic_id is not None:
            query += """ AND EXISTS (
                SELECT 1 FROM learning l
                WHERE l.studentid = s.id AND l.academicid = :academic_id
            )"""
            params["academic_id"] = academic_id

        # Apply branch filter if provided (based on students.branch column)
        if branch_id is not None:
            query += " AND s.branch = :branch_id_str"
            params["branch_id_str"] = str(branch_id)
        
        # Search filter (optional)
        if search is not None and search.strip():
            search_term = f"%{search}%"
            query += """ AND (
                s.kName LIKE :search OR 
                s.eName LIKE :search OR 
                s.studentid LIKE :search OR
                b.branch_name LIKE :search
            )"""
            params["search"] = search_term
        
        query += " ORDER BY s.kName ASC"
        
        # Get total count for pagination (before adding LIMIT/OFFSET)
        count_query = """
            SELECT COUNT(DISTINCT s.id)
            FROM students s
            LEFT JOIN branch b ON b.id = s.branch
            WHERE 1=1
        """
        count_params: Dict[str, Any] = {}
        
        # Apply same status filter to count query
        if status is not None:
            if status == 1:
                count_query += " AND s.status = 1"
            else:
                count_query += " AND s.status != 1"
        elif not historical:
            count_query += " AND s.status = 1"

        if academic_id is not None:
            count_query += """ AND EXISTS (
                SELECT 1 FROM learning l
                WHERE l.studentid = s.id AND l.academicid = :academic_id
            )"""
            count_params["academic_id"] = academic_id

        # Apply same filters to count query
        if branch_id is not None:
            count_query += " AND s.branch = :branch_id_str"
            count_params["branch_id_str"] = str(branch_id)
        
        if search is not None and search.strip():
            search_term = f"%{search}%"
            count_query += """ AND (
                s.kName LIKE :search OR 
                s.eName LIKE :search OR 
                s.studentid LIKE :search OR
                b.branch_name LIKE :search
            )"""
            count_params["search"] = search_term
        
        try:
            count_result = db.execute(text(count_query), count_params)
            total_count = count_result.scalar() or 0
        except Exception as count_error:
            logger.error(f"Count query error: {str(count_error)}")
            logger.error(f"Count query traceback: {traceback.format_exc()}")
            # If count fails, try to get count from main query result
            total_count = 0
        
        # Add pagination
        offset = (page - 1) * limit
        query += f" LIMIT :limit OFFSET :offset"
        params['limit'] = limit
        params['offset'] = offset
        
        try:
            result = db.execute(text(query), params)
            rows = result.fetchall()
        except Exception as query_error:
            logger.error(f"Query execution error: {str(query_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Database query error: {str(query_error)}")
        
        def format_date(val):
            """Format date to ISO string"""
            if val is None:
                return None
            if hasattr(val, 'isoformat'):
                return val.isoformat()
            return None
        
        def format_binary(val):
            """Format binary data to hex string"""
            if val is None:
                return None
            if hasattr(val, 'hex'):
                return val.hex()
            return None
        
        def safe_get(row, index, default=None):
            """Safely get value from row by index"""
            try:
                if index < len(row):
                    val = row[index]
                    return val if val is not None else default
                return default
            except (IndexError, TypeError):
                return default
        
        students = []
        for row in rows:
            try:
                # Access by index (like attendance API)
                # Column order: id, studentid, optional_id, username, kName, eName, gender, dob, image,
                # student_phone, is_foreigner, province, district, commune, village, previousSchool,
                # leaveDate, myparents, child_order, academic, branch, status, student_noted,
                # created_at, updated_at, branch_name, age, pickup_audio_url
                # (removed program_name, grade_name, shift_name - not needed in list)

                # Get created_at value and provide fallback if NULL
                created_at_value = safe_get(row, 23)
                if created_at_value is None:
                    # For existing students with NULL created_at, use a reasonable default
                    # This represents when the school system was likely first deployed
                    created_at_value = '2022-01-01T00:00:00'

                student = {
                    'id': safe_get(row, 0),
                    'studentid': safe_get(row, 1),
                    'optional_id': safe_get(row, 2),
                    'username': safe_get(row, 3),
                    'kName': safe_get(row, 4) or '',
                    'eName': safe_get(row, 5) or '',
                    'gender': safe_get(row, 6) or '',
                    'dob': format_date(safe_get(row, 7)),
                    'image': safe_get(row, 8),  # avatar URL from users_resource
                    'student_phone': safe_get(row, 9),
                    'is_foreigner': safe_get(row, 10) or 0,
                    'province': safe_get(row, 11),
                    'district': safe_get(row, 12),
                    'commune': safe_get(row, 13),
                    'village': safe_get(row, 14),
                    'previousSchool': safe_get(row, 15),
                    'leaveDate': format_date(safe_get(row, 16)),
                    'myparents': safe_get(row, 17),
                    'child_order': safe_get(row, 18),
                    'academic': safe_get(row, 19),
                    'branch': safe_get(row, 20),
                    'status': 'active' if (safe_get(row, 21) == 1 or safe_get(row, 21) == 'active') else 'inactive',
                    'student_noted': safe_get(row, 22),
                    'created_at': format_date(created_at_value),
                    'updated_at': format_date(safe_get(row, 24)),
                    'branch_name': safe_get(row, 25),
                    'age': safe_get(row, 26),
                    'pickup_audio_url': safe_get(row, 27),
                }
                students.append(student)
            except Exception as row_error:
                logger.error(f"Error processing row: {row_error}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                logger.error(f"Row type: {type(row)}, Row length: {len(row) if hasattr(row, '__len__') else 'N/A'}, Row: {row}")
                continue
        
        
        result = {
            "students": students,
            "total": total_count,
            "page": page,
            "limit": limit,
            "total_pages": (total_count + limit - 1) // limit if limit > 0 else 1,
            "has_next": (page * limit) < total_count,
            "has_previous": page > 1,
            "message": "Students retrieved successfully"
        }
        
        # Cache the result for 2 minutes (120 seconds)
        query_cache.set(cache_key, result, ttl=120)
        
        return result

    except Exception as e:
        logger.error(f"ERROR in get_all_students: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving students: {str(e)}")


def _notify_admins_new_pending_child_bg(student_id: int, parent_name: str, child_name: str):
    """Push to active App Admins when a parent submits a new child for approval."""
    from ...core.database import SessionLocal
    from ...services import notification_service
    db = SessionLocal()
    try:
        admin_targets = notification_service.get_app_admin_user_ids(db)
        if not admin_targets:
            return
        tokens = notification_service.resolve_device_tokens_for_users(
            db,
            admin_targets,
        )
        notification_service.send_notification(
            device_tokens=tokens,
            title="New Student Registration",
            body=f"{parent_name} registered a new student: {child_name}. Pending approval.",
            data={
                "type": "pending_student_request",
                "student_id": str(student_id),
                "notification_key": f"pending_student_request:{student_id}",
            },
            channel_id="message_channel",
            android_show_system_notification=True,
            db=db,
            user_ids=admin_targets,
            redirect_route="pending_students",
            redirect_args={"student_id": student_id},
        )
    except Exception as e:
        logger.error(f"Error notifying admins of new pending child: {e}")
    finally:
        db.close()


@router.post("/students/register")
async def create_student(
    student_data: StudentRegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_active_user)
):
    """
    Register a new student.
    
    If the current user is a Parent, automatically link this student to the parent.
    """
    try:
        from ...utils import get_password_hash
        
        # Gender Mapping to Khmer
        # User requested: save "ប្រុស" or "ស្រី"
        mapped_gender = student_data.gender
        if student_data.gender:
            g_lower = student_data.gender.lower()
            if g_lower in ['male', 'm', 'ប្រុស']:
                mapped_gender = 'ប្រុស'
            elif g_lower in ['female', 'f', 'ស្រី']:
                mapped_gender = 'ស្រី'
        
        # Handle Image
        # 1. student.image should be NULL (or empty)
        # 2. Save image to disk and create UserResource
        image_binary = None # For students table
        
        # Default password
        hashed_password = get_password_hash("123456")

        # Prepare Parent Linking Data (Before creation to get child_order)
        parent_id = None
        user_type = None
        child_order = 1
        parent_obj = None

        # Helper to get attribute from dict or object or Pydantic model
        def get_attr(obj, attr_name):
            if isinstance(obj, dict):
                return obj.get(attr_name)
            return getattr(obj, attr_name, None)

        user_type = get_attr(current_user, 'user_type')
        
        # Check if user is parent (either via user_type or is_parent attr)
        is_parent_flag = get_attr(current_user, 'is_parent')
        
        if user_type == 'parent' or is_parent_flag:
            parent_id = get_attr(current_user, 'id')
            if parent_id:
                parent_obj = db.query(Parent).filter(Parent.id == parent_id).first()
                if parent_obj:
                    from ...core.parent_child_limits import (
                        validate_pending_parent_child_add,
                    )

                    validate_pending_parent_child_add(
                        parent_obj,
                        student_data.add_phase,
                    )
                    # Calculate child order
                    current_child_ids = []
                    if parent_obj.myChilds:
                        try:
                            current_child_ids = [x.strip() for x in str(parent_obj.myChilds).split(',') if x.strip()]
                        except:
                            current_child_ids = []
                    
                    child_order = len(current_child_ids) + 1

        new_student = Student(
            kName=student_data.kName,
            eName=student_data.eName,
            gender=mapped_gender,
            dob=student_data.dob,
            image=image_binary,
            student_phone=student_data.student_phone,
            is_foreigner=student_data.is_foreigner,
            province=student_data.province,
            district=student_data.district,
            commune=student_data.commune,
            village=student_data.village,
            previousSchool=student_data.previousSchool,
            leaveDate=None, # Explicitly null as requested
            myparents=str(parent_id) if parent_id else "", 
            child_order=child_order, 
            academic="1", # Default 1
            branch=student_data.branch or "1", # Default 1 if missing
            status=2, # Default 2 (Pending/Review)
            # Only parent self-registrations are tracked as pending child
            # submissions (shown in the admin screen + 7-day auto-cleanup).
            submitted_by_parent=(1 if parent_id else 0),
            student_noted=student_data.student_noted,
            password=hashed_password,
            username=None, # Will generate after ID
            studentid=None, # Will generate after ID
            optional_id=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        db.add(new_student)
        db.flush() # Get ID
        
        # Generate Credentials
        # Username: s + id + YY (e.g. s10526)
        yy = datetime.now().strftime('%y')
        generated_username = f"s{new_student.id}{yy}"
        
        # --- Auto-generated Student ID Logic ---
        # Query settings table to determine ID format
        # Use try-except to fallback to original logic if tables/columns don't exist
        generated_studentid = None
        try:
            settings_query = text("SELECT prefixid, follow_type, digit_number, startid FROM settings LIMIT 1")
            settings_result = db.execute(settings_query).fetchone()

            if settings_result:
                prefixid = getattr(settings_result, 'prefixid', '') or ''
                follow_type = getattr(settings_result, 'follow_type', 'settings')
                digit_number = getattr(settings_result, 'digit_number', 6) or 6
                startid = getattr(settings_result, 'startid', 1) or 1

                if follow_type == 'branch':
                    # Query branch table
                    branch_query = text("SELECT id_prefix, id_digit, id_start_number FROM branch WHERE id = :branch_id LIMIT 1")
                    branch_result = db.execute(branch_query, {"branch_id": student_data.branch or 1}).fetchone()
                    
                    if branch_result:
                        prefixid = getattr(branch_result, 'id_prefix', prefixid) or prefixid
                        digit_number = getattr(branch_result, 'id_digit', digit_number) or digit_number
                        startid = getattr(branch_result, 'id_start_number', startid) or startid

                # To ensure the ID increments correctly, we can use the newly inserted student ID
                # or query the count of existing students. Given auto-increment can have gaps,
                # querying the max ID or simply counting might be safer for a contiguous sequence.
                # Let's count total students (or total in branch if follow_type == branch) to get the offset.
                if follow_type == 'branch':
                    count_query = text("SELECT COUNT(id) FROM students WHERE branch = :branch_id")
                    count_result = db.execute(count_query, {"branch_id": student_data.branch or 1}).scalar()
                else:
                    count_query = text("SELECT COUNT(id) FROM students")
                    count_result = db.execute(count_query).scalar()
                
                # count_result already includes the newly flushed student
                # so if count is 1, it should be startid
                current_offset = (count_result or 1) - 1
                base_number = int(startid) + current_offset
                
                # Format to digit_number, padded with zeros
                formatted_number = f"{base_number:0{int(digit_number)}d}"
                generated_studentid = f"{prefixid}{formatted_number}"
        except Exception as id_error:
            logger.error(f"Failed to auto-generate studentID from settings: {id_error}")
            
        # Fallback if generation failed
        if not generated_studentid:
            generated_studentid = f"STU{new_student.id:06d}"

        new_student.username = generated_username
        new_student.studentid = generated_studentid
        
        # Update Parent's myChilds if linked
        if parent_obj:
            current_childs = parent_obj.myChilds or ""
            if current_childs:
                new_childs = f"{current_childs},{new_student.id}"
            else:
                new_childs = str(new_student.id)
            parent_obj.myChilds = new_childs
            db.add(parent_obj)

        db.add(new_student)
        db.commit()
        db.refresh(new_student)
        
        # Invalidate students list cache
        from ...services.query_cache import invalidate_cache
        invalidate_cache("students_list")

        # Handle Image Saving to UserResource
        if student_data.image:
            try:
                import base64
                import uuid
                import os
                from ...models.user_resource import UserResource
                
                # Decode base64
                # Check if header present (data:image/jpeg;base64,...)
                img_str = student_data.image
                if ',' in img_str:
                    img_str = img_str.split(',')[1]
                    
                image_data = base64.b64decode(img_str)
                
                # Directory
                upload_dir = "uploads/avatars"
                os.makedirs(upload_dir, exist_ok=True)
                
                filename = f"student_{new_student.id}_{uuid.uuid4().hex[:8]}.jpg"
                file_path = os.path.join(upload_dir, filename)
                
                with open(file_path, "wb") as f:
                    f.write(image_data)
                    
                # Create UserResource
                user_res = UserResource(
                    user_id=new_student.id,
                    user_type='student',
                    avatar=file_path,
                    status=1
                )
                db.add(user_res)
                db.commit()
            except Exception as e:
                logger.error(f"Failed to save student image to UserResource: {e}")
                # Don't fail the registration
        
        # Notify App Admins when a PARENT submitted a new child for approval.
        if parent_id:
            parent_name = (
                (parent_obj.fatherName if parent_obj else None)
                or (parent_obj.motherName if parent_obj else None)
                or "A parent"
            )
            child_name = (student_data.eName or student_data.kName or f"Student #{new_student.id}")
            background_tasks.add_task(
                _notify_admins_new_pending_child_bg,
                new_student.id,
                parent_name,
                child_name,
            )

        return {
            "message": "Student created successfully",
            "student_id": new_student.id,
            "username": new_student.username,
            "password": "123456"  # Return default password for display
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating student: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error creating student: {str(e)}")



@router.get("/students/summary")
async def get_student_summary(
    branch_id: Optional[int] = Query(None),
    status: Optional[int] = Query(None),  # 1 = active, 0 or other = inactive (defaults to 1 in code if None)
    academic_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get aggregated student statistics
    
    IMPORTANT: Uses students.branch column directly (same as get_all_students)
    to ensure counts match the filtered student list.
    """
    try:
        # Base summary query - use students.branch directly (same as get_all_students)
        # This ensures summary counts match the filtered student list
        summary_query = """
            SELECT 
                COUNT(*) as total_students,
                SUM(CASE WHEN gender IN ('ប្រុស', 'Male', 'M') THEN 1 ELSE 0 END) as male_count,
                SUM(CASE WHEN gender IN ('ស្រី', 'Female', 'F') THEN 1 ELSE 0 END) as female_count,
                SUM(CASE WHEN is_foreigner = 1 THEN 1 ELSE 0 END) as foreigner_count,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as active_count,
                SUM(CASE WHEN status != 1 THEN 1 ELSE 0 END) as inactive_count
            FROM students
            WHERE 1=1
        """
        params: Dict[str, Any] = {}
        
        # Apply status filter (same logic as get_all_students)
        if status is not None:
            if status == 1:
                summary_query += " AND status = 1"
            else:
                # status != 1 means inactive (could be 0, 2, etc.)
                summary_query += " AND status != 1"
        else:
            # Default to active (status = 1) if not specified
            summary_query += " AND status = 1"
        
        # Apply branch filter using students.branch column (same as get_all_students)
        if branch_id is not None:
            summary_query += " AND branch = :branch_id_str"
            params['branch_id_str'] = str(branch_id)
        
        # Apply academic filter if provided
        if academic_id is not None:
            # Academic filter: students.academic is VARCHAR, so compare as string
            summary_query += " AND academic = :academic_id"
            params['academic_id'] = str(academic_id)
        
        # Apply search filter if provided (same as get_all_students)
        if search is not None and search.strip():
            search_term = f"%{search}%"
            summary_query += """ AND (
                kName LIKE :search OR 
                eName LIKE :search OR 
                studentid LIKE :search
            )"""
            params['search'] = search_term
        
        try:
            result = db.execute(text(summary_query), params)
            summary_row = result.fetchone()
        except Exception as query_error:
            logger.error(f"Summary query execution error: {str(query_error)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Database query error: {str(query_error)}")
        
        # Access summary by index: total_students, male_count, female_count, foreigner_count, active_count, inactive_count
        def safe_get(row, index, default=0):
            """Safely get value from row by index"""
            try:
                if row and index < len(row):
                    val = row[index]
                    return val if val is not None else default
                return default
            except (IndexError, TypeError):
                return default
        
        total_students = safe_get(summary_row, 0, 0)
        male_count = safe_get(summary_row, 1, 0)
        female_count = safe_get(summary_row, 2, 0)
        foreigner_count = safe_get(summary_row, 3, 0)
        active_count = safe_get(summary_row, 4, 0)
        inactive_count = safe_get(summary_row, 5, 0)
        
        # Program / shift / branch / age breakdowns in one round-trip (same filters as before; search is summary-only)
        status_filter_sql = ""
        if status is not None:
            if status == 1:
                status_filter_sql = " AND s.status = 1"
            else:
                status_filter_sql = " AND s.status != 1"
        else:
            status_filter_sql = " AND s.status = 1"

        branch_filter_sql = ""
        if branch_id is not None:
            branch_filter_sql = " AND s.branch = :branch_id_str"

        academic_learning_sql = ""
        academic_students_sql = ""
        breakdown_params: Dict[str, Any] = {}
        if branch_id is not None:
            breakdown_params["branch_id_str"] = str(branch_id)
        if academic_id is not None:
            academic_learning_sql = " AND l.academicid = :academic_id"
            academic_students_sql = " AND s.academic = :academic_id"
            breakdown_params["academic_id"] = str(academic_id)

        program_sub = f"""
            SELECT CAST('program' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_type, CAST(COALESCE(p.program_name, '') AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_key, COUNT(DISTINCT s.id) AS cnt
            FROM students s
            JOIN learning l ON l.studentid = s.id
            LEFT JOIN program p ON l.programid = p.id
            WHERE 1=1
            {status_filter_sql}
            {branch_filter_sql}
            {academic_learning_sql}
            GROUP BY p.program_name
        """
        shift_sub = f"""
            SELECT CAST('shift' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_type, CAST(COALESCE(sh.shift_name, '') AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_key, COUNT(DISTINCT s.id) AS cnt
            FROM students s
            JOIN learning l ON l.studentid = s.id
            LEFT JOIN shift sh ON l.shiftid = sh.id
            WHERE 1=1
            {status_filter_sql}
            {branch_filter_sql}
            {academic_learning_sql}
            GROUP BY sh.shift_name
        """
        branch_sub = f"""
            SELECT CAST('branch' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_type, CAST(COALESCE(b.branch_name, '') AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_key, COUNT(DISTINCT s.id) AS cnt
            FROM students s
            LEFT JOIN branch b ON b.id = s.branch
            WHERE 1=1
            {status_filter_sql}
            {branch_filter_sql}
            {academic_students_sql}
            GROUP BY b.branch_name
        """
        age_sub = f"""
            SELECT CAST('age' AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_type, CAST(TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci AS stat_key, COUNT(DISTINCT s.id) AS cnt
            FROM students s
            WHERE s.dob IS NOT NULL
            {status_filter_sql}
            {branch_filter_sql}
            {academic_students_sql}
            GROUP BY TIMESTAMPDIFF(YEAR, s.dob, CURDATE())
        """

        combined_breakdown = f"""
            ({program_sub.strip()})
            UNION ALL
            ({shift_sub.strip()})
            UNION ALL
            ({branch_sub.strip()})
            UNION ALL
            ({age_sub.strip()})
        """

        breakdown_result = db.execute(text(combined_breakdown), breakdown_params)
        by_program: Dict[str, int] = {}
        by_shift: Dict[str, int] = {}
        by_branch: Dict[str, int] = {}
        by_age: Dict[str, int] = {}
        for row in breakdown_result:
            stat_type = row[0]
            stat_key = row[1]
            cnt = row[2] or 0
            if stat_type == "program" and stat_key:
                by_program[stat_key] = cnt
            elif stat_type == "shift" and stat_key:
                by_shift[stat_key] = cnt
            elif stat_type == "branch" and stat_key:
                by_branch[stat_key] = cnt
            elif stat_type == "age" and stat_key is not None and stat_key != "":
                by_age[str(stat_key)] = cnt

        # Preserve age bucket ordering (numeric) — same as previous ORDER BY age
        if by_age:
            try:
                by_age = dict(sorted(by_age.items(), key=lambda kv: int(kv[0])))
            except (ValueError, TypeError):
                by_age = dict(sorted(by_age.items(), key=lambda kv: str(kv[0])))
        
        return {
            "summary": {
                "total_students": total_students,
                "male_count": male_count,
                "female_count": female_count,
                "foreigner_count": foreigner_count,
                "active_count": active_count,
                "inactive_count": inactive_count,
                "by_program": by_program,
                "by_shift": by_shift,
                "by_branch": by_branch,
                "by_age": by_age
            },
            "message": "Summary retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"ERROR in get_student_summary: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving summary: {str(e)}")
@router.get("/students/branches")
async def get_all_branches(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all branches (wrapped payload, includes pickup_radius_meters).

    Canonical public list is GET /api/v1/branches (branches router).
    This authenticated endpoint remains for clients that need the wrapped
    shape or fields; path is /students/branches to avoid clashing with it.
    """
    try:
        # Fetch branches
        branch_query = """
            SELECT 
                id, 
                branch_name,
                app_display_name,
                app_branch_cover,
                app_branch_facebook_url,
                app_branch_telegram_url,
                app_branch_youtube_url,
                app_branch_tiktok_url,
                app_branch_google_map_url,
                map_latitude,
                map_longitude,
                pickup_radius_meters,
                open_at,
                close_at
            FROM branch 
            ORDER BY branch_name ASC
        """
        branch_result = db.execute(text(branch_query))
        branch_rows = branch_result.fetchall()
        
        # Fetch branch contacts
        contacts_query = """
            SELECT
                id,
                branch_id,
                label,
                value,
                sort_order
            FROM branch_contacts
            ORDER BY branch_id, sort_order ASC, id ASC
        """
        contacts_result = db.execute(text(contacts_query))
        contacts_rows = contacts_result.fetchall()

        # Group contacts by branch_id
        from collections import defaultdict
        contacts_by_branch = defaultdict(list)
        for crow in contacts_rows:
            branch_id = getattr(crow, 'branch_id', None) or (crow._mapping.get('branch_id') if hasattr(crow, '_mapping') else crow['branch_id'])
            
            def get_cval(col):
                if hasattr(crow, col): return getattr(crow, col)
                if hasattr(crow, '_mapping'): return crow._mapping.get(col)
                return crow[col]
                
            contacts_by_branch[branch_id].append({
                "id": get_cval("id"),
                "label": get_cval("label"),
                "value": get_cval("value"),
                "sort_order": get_cval("sort_order"),
            })
        
        def get_val(row, key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        def _format_time(t):
            if t is None:
                return None
            if isinstance(t, str):
                return t
            if hasattr(t, 'total_seconds'):
                total_seconds = int(t.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return str(t)

        branches = []
        for row in branch_rows:
            branch_id = get_val(row, 'id')
            branches.append({
                'id': branch_id, 
                'branch_name': get_val(row, 'branch_name'),
                'app_display_name': get_val(row, 'app_display_name'),
                'app_branch_cover': get_val(row, 'app_branch_cover'),
                'app_branch_facebook_url': get_val(row, 'app_branch_facebook_url'),
                'app_branch_telegram_url': get_val(row, 'app_branch_telegram_url'),
                'app_branch_youtube_url': get_val(row, 'app_branch_youtube_url'),
                'app_branch_tiktok_url': get_val(row, 'app_branch_tiktok_url'),
                'app_branch_google_map_url': get_val(row, 'app_branch_google_map_url'),
                'map_latitude': get_val(row, 'map_latitude'),
                'map_longitude': get_val(row, 'map_longitude'),
                'pickup_radius_meters': float(get_val(row, 'pickup_radius_meters'))
                if get_val(row, 'pickup_radius_meters') is not None
                else None,
                'open_at': _format_time(get_val(row, 'open_at')),
                'close_at': _format_time(get_val(row, 'close_at')),
                'contacts': contacts_by_branch.get(branch_id, [])
            })
        
        return {
            "branches": branches,
            "message": "Branches retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"ERROR in get_all_branches: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving branches: {str(e)}")


@router.get("/academics")
async def get_all_academics(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all academic years"""
    try:
        query = "SELECT id, academic_name, academic_us_name, academic_start, academic_end, status FROM academic ORDER BY id DESC"
        result = db.execute(text(query))
        rows = result.fetchall()
        
        def get_val(row, key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        academics = [{
            'id': get_val(row, 'id'),
            'academic_name': get_val(row, 'academic_name'),
            'academic_us_name': get_val(row, 'academic_us_name'),
            'academic_start': str(get_val(row, 'academic_start')) if get_val(row, 'academic_start') else None,
            'academic_end': str(get_val(row, 'academic_end')) if get_val(row, 'academic_end') else None,
            'status': get_val(row, 'status')
        } for row in rows]
        
        return {
            "academics": academics,
            "message": "Academics retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"ERROR in get_all_academics: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving academics: {str(e)}")



@router.get("/programs")
async def get_all_programs(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all programs"""
    try:
        query = "SELECT id, program_name, short_code FROM program ORDER BY program_name ASC"
        result = db.execute(text(query))
        rows = result.fetchall()
        
        def get_val(row, key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        programs = [
            {
                'id': get_val(row, 'id'),
                'program_name': get_val(row, 'program_name'),
                'program_short_code': get_val(row, 'short_code') or get_val(row, 'program_name')
            }
            for row in rows
        ]
        
        return {
            "programs": programs,
            "message": "Programs retrieved successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving programs: {str(e)}")


@router.get("/shifts")
async def get_all_shifts(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all shifts"""
    try:
        query = "SELECT id, shift_name, start_at, end_at FROM shift ORDER BY start_at ASC"
        result = db.execute(text(query))
        rows = result.fetchall()
        
        def get_val(row, key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        shifts = [
            {
                'id': get_val(row, 'id'),
                'shift_name': get_val(row, 'shift_name'),
                'start_at': str(get_val(row, 'start_at')) if get_val(row, 'start_at') else None,
                'end_at': str(get_val(row, 'end_at')) if get_val(row, 'end_at') else None
            }
            for row in rows
        ]
        
        return {
            "shifts": shifts,
            "message": "Shifts retrieved successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving shifts: {str(e)}")


@router.get("/students/{student_id}")
async def get_student_by_id(
    student_id: int,
    academic_id: Optional[int] = Query(None, description="Academic year for the learning records; defaults to the current year"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get a specific student by ID"""
    try:
        # Try full query with joins first
        try:
            query = """
                SELECT 
                    s.id, s.studentid, s.optional_id, s.username,
                    s.kName, s.eName, s.gender, s.dob,
                    s.student_phone, s.is_foreigner,
                    s.province, s.district, s.commune, s.village,
                    s.previousSchool, s.leaveDate,
                    s.myparents, s.child_order, s.academic,
                    s.branch, s.status, s.student_noted,
                    s.created_at, s.updated_at,
                    b.branch_name,
                    a.academic_us_name as academic_name,
                    TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age,
                    ur.avatar as ur_avatar,
                    s.pickup_audio_url
                FROM students s
                LEFT JOIN branch b ON b.id = s.branch
                LEFT JOIN academic a ON s.academic = a.id
                LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
                WHERE s.id = :student_id
            """
            result = db.execute(text(query), {'student_id': student_id})
            row = result.fetchone()
        except Exception as e:
            error_str = str(e)
            if "1146" in error_str and ("academic" in error_str or "branch" in error_str):
                # Fallback query if academic or branch table missing
                logger.warning(f"Table missing in get_student_by_id, using fallback query: {error_str}")
                query = """
                    SELECT 
                        s.id, s.studentid, s.optional_id, s.username,
                        s.kName, s.eName, s.gender, s.dob,
                        s.student_phone, s.is_foreigner,
                        s.province, s.district, s.commune, s.village,
                        s.previousSchool, s.leaveDate,
                        s.myparents, s.child_order, s.academic,
                        s.branch, s.status, s.student_noted,
                        s.created_at, s.updated_at,
                        NULL as branch_name,
                        NULL as academic_name,
                        TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age,
                        NULL as ur_avatar,
                        s.pickup_audio_url
                    FROM students s
                    WHERE s.id = :student_id
                """
                result = db.execute(text(query), {'student_id': student_id})
                row = result.fetchone()
            else:
                raise e
        
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Helper functions
        def get_val(key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        def format_date(val):
            if val and hasattr(val, 'isoformat'):
                return val.isoformat()
            return None
        
        def format_binary(val):
            if val and hasattr(val, 'hex'):
                return val.hex()
            return None

        # Get created_at value and provide fallback if NULL
        created_at_value = get_val('created_at')
        if created_at_value is None:
            # For existing students with NULL created_at, use a reasonable default
            # This represents when the school system was likely first deployed
            created_at_value = '2022-01-01T00:00:00'

        student = {
            'id': get_val('id'),
            'studentid': get_val('studentid'),
            'optional_id': get_val('optional_id'),
            'username': get_val('username'),
            'kName': get_val('kName'),
            'eName': get_val('eName'),
            'gender': get_val('gender'),
            'dob': format_date(get_val('dob')),
            'image': get_val('ur_avatar'),  # avatar URL from users_resource
            'student_phone': get_val('student_phone'),
            'is_foreigner': get_val('is_foreigner'),
            'province': get_val('province'),
            'district': get_val('district'),
            'commune': get_val('commune'),
            'village': get_val('village'),
            'previousSchool': get_val('previousSchool'),
            'leaveDate': format_date(get_val('leaveDate')),
            'myparents': get_val('myparents'),
            'child_order': get_val('child_order'),
            'academic': get_val('academic'),
            'academic_name': get_val('academic_name'),
            'branch': get_val('branch'),
            'status': get_val('status'),
            'student_noted': get_val('student_noted'),
            'created_at': format_date(created_at_value),
            'updated_at': format_date(get_val('updated_at')),
            'program_name': get_val('program_name'),
            'grade_name': get_val('grade_name'),
            'shift_name': get_val('shift_name'),
            'branch_name': get_val('branch_name'),
            'age': get_val('age'),
            'pickup_audio_url': get_val('pickup_audio_url'),
            'learnings': []
        }

        # Fetch learning records
        learning_query = """
            SELECT 
                l.id,
                l.academicid,
                l.programid,
                l.gradeid,
                l.shiftid,
                l.grade_type_id,
                COALESCE(NULLIF(p.short_code, ''), p.program_name) as program_name,
                p.program_name as program_full_name,
                g.grade_name,
                sh.shift_name,
                b.branch_name,
                CASE 
                    WHEN u.isForeigner = 1 THEN COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                    WHEN u.isForeigner = 2 THEN COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), 'Unknown')
                    ELSE COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                END as teacher_name,
                u.id as teacher_id,
                gt.type_name
            FROM learning l
            LEFT JOIN program p ON l.programid = p.id
            LEFT JOIN grade g ON l.gradeid = g.id
            LEFT JOIN shift sh ON l.shiftid = sh.id
            LEFT JOIN branch b ON g.branch_id = b.id
            LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
            LEFT JOIN (
                SELECT 
                    ct.program_id,
                    ct.grade_id,
                    ct.shift_id,
                    ct.branch_id,
                    ct.academic_id,
                    ct.grade_type_id,
                    MIN(ct.teacher_id) as teacher_id
                FROM class_teachers ct
                GROUP BY ct.program_id, ct.grade_id, ct.shift_id, ct.branch_id, ct.academic_id, ct.grade_type_id
            ) ct ON (
                l.programid = ct.program_id AND 
                l.gradeid = ct.grade_id AND 
                l.shiftid = ct.shift_id AND 
                g.branch_id = ct.branch_id AND 
                l.academicid = ct.academic_id AND
                COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1)
            )
            LEFT JOIN users u ON ct.teacher_id = u.id
            WHERE l.studentid = :student_id AND l.academicid = :academic_id
            GROUP BY l.id, l.academicid, l.programid, l.gradeid, l.shiftid, l.grade_type_id,
                     p.short_code, p.program_name, g.grade_name,
                     sh.shift_name, b.branch_name, u.kName, u.eName, gt.type_name, u.isForeigner, u.id
        """
        
        # Academic year for the learning records: honor the caller's
        # academic_id (the app passes its globally selected year), otherwise
        # resolve the current year via the canonical rule
        # (academic.status=1 -> settings.academicid -> newest).
        from ...utils.academic_year import get_current_academic_id

        if academic_id is not None and academic_id > 0:
            global_academic_id = academic_id
        else:
            global_academic_id = get_current_academic_id(db)
        academic_us_name_val = None
        academic_name_val = None

        try:
            def _row_val(row, *keys_or_indices):
                """Get first non-null value from row by key or index."""
                if row is None:
                    return None
                for k in keys_or_indices:
                    try:
                        if isinstance(k, int):
                            v = row[k] if k < len(row) else None
                        else:
                            v = getattr(row, k, None) or (row._mapping.get(k) if hasattr(row, "_mapping") else None) or (row[k] if hasattr(row, "__getitem__") else None)
                        if v is not None and str(v).strip():
                            return str(v).strip()
                    except (IndexError, KeyError, AttributeError, TypeError):
                        continue
                return None

            # 4) Get academic_us_name from academic table by that id (settings -> academic)
            try:
                ac_result = db.execute(
                    text(
                        "SELECT academic_us_name, academic_name FROM academic WHERE id = :aid LIMIT 1"
                    ),
                    {"aid": global_academic_id},
                )
                ac_row = ac_result.fetchone()
                if ac_row:
                    academic_us_name_val = _row_val(ac_row, "academic_us_name", "academic_name", 0, 1)
                    academic_name_val = _row_val(ac_row, "academic_name", "academic_us_name", 1, 0)
                    if not academic_us_name_val:
                        academic_us_name_val = academic_name_val
                    if not academic_name_val:
                        academic_name_val = academic_us_name_val
            except Exception as e:
                logger.warning(f"Could not fetch academic by id {global_academic_id}: {e}")

            # 5) Fallback: get active academic from academic table (status = 1 if column exists)
            if not academic_us_name_val and not academic_name_val:
                try:
                    ac_active_result = db.execute(
                        text(
                            "SELECT academic_us_name, academic_name FROM academic WHERE status = 1 LIMIT 1"
                        )
                    )
                    ac_active_row = ac_active_result.fetchone()
                    if ac_active_row:
                        academic_us_name_val = _row_val(ac_active_row, "academic_us_name", "academic_name", 0, 1)
                        academic_name_val = _row_val(ac_active_row, "academic_name", "academic_us_name", 1, 0)
                        if not academic_us_name_val:
                            academic_us_name_val = academic_name_val
                        if not academic_name_val:
                            academic_name_val = academic_us_name_val
                except Exception:
                    pass

            # 6) Fallback: get latest academic by id (any row)
            if not academic_us_name_val and not academic_name_val:
                try:
                    ac_latest_result = db.execute(
                        text(
                            "SELECT academic_us_name, academic_name FROM academic ORDER BY id DESC LIMIT 1"
                        )
                    )
                    ac_latest_row = ac_latest_result.fetchone()
                    if ac_latest_row:
                        academic_us_name_val = _row_val(ac_latest_row, "academic_us_name", "academic_name", 0, 1)
                        academic_name_val = _row_val(ac_latest_row, "academic_name", "academic_us_name", 1, 0)
                        if not academic_us_name_val:
                            academic_us_name_val = academic_name_val
                        if not academic_name_val:
                            academic_name_val = academic_us_name_val
                except Exception as e:
                    logger.warning(f"Could not fetch latest academic: {e}")

            # Set on student response for UI (always set both keys so Flutter gets them)
            display_name = academic_us_name_val or academic_name_val
            if display_name:
                student["academic_us_name"] = display_name
                student["academic_name"] = display_name
            else:
                student["academic_us_name"] = student.get("academic_name")  # keep from JOIN if any
                if not student.get("academic_name"):
                    student["academic_name"] = None

        except Exception as e:
            logger.warning(f"Error resolving current academic for student response: {e}")
            if global_academic_id is None:
                global_academic_id = 1

        # Unconditional fallback: if still no academic name, try one more time (e.g. if try block failed early)
        if not student.get("academic_us_name") and not student.get("academic_name"):
            try:
                last_ac = db.execute(
                    text("SELECT academic_us_name, academic_name FROM academic ORDER BY id DESC LIMIT 1")
                ).fetchone()
                if last_ac:
                    v0 = last_ac[0] if len(last_ac) > 0 else None
                    v1 = last_ac[1] if len(last_ac) > 1 else None
                    display = (v0 or v1)
                    if display is not None and str(display).strip():
                        student["academic_us_name"] = str(display).strip()
                        student["academic_name"] = str(display).strip()
            except Exception as e2:
                logger.warning(f"Final academic fallback failed: {e2}")

        # Only fetch learnings if we have a valid academic_id (not None and > 0)
        learning_rows = []
        if global_academic_id is not None and global_academic_id > 0:
            learning_result = db.execute(text(learning_query), {
                'student_id': student_id,
                'academic_id': global_academic_id
            })
            learning_rows = learning_result.fetchall()
        # If global_academic_id is None or <= 0, learning_rows remains empty
        
        for l_row in learning_rows:
            student['learnings'].append({
                'id': l_row[0],
                'academic_id': l_row[1],
                'program_id': l_row[2],
                'grade_id': l_row[3],
                'shift_id': l_row[4],
                'grade_type_id': l_row[5],
                'program_short_code': l_row[6],
                'program_name': l_row[7],
                'grade_name': l_row[8],
                'shift_name': l_row[9],
                'branch_name': l_row[10],
                'teacher_name': l_row[11],
                'teacher_id': l_row[12],
                'grade_type_name': l_row[13],
            })
        
        return {
            "student": student,
            "message": "Student retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error retrieving student: {str(e)}")


@router.get("/parents/{parent_id}")
async def get_parent_info(
    parent_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get parent information"""
    try:
        query = "SELECT * FROM parents WHERE id = :parent_id"
        result = db.execute(text(query), {'parent_id': parent_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Parent not found")
        
        # Helper functions
        def get_val(key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        def format_date(val):
            if val and hasattr(val, 'isoformat'):
                return val.isoformat()
            return None
        
        parent = {
            'id': get_val('id'),
            'uniqueid': get_val('uniqueid'),
            'username': get_val('username'),
            'fatherName': get_val('fatherName'),
            'motherName': get_val('motherName'),
            'fatherPhone': get_val('fatherPhone'),
            'motherPhone': get_val('motherPhone'),
            'fatherJob': get_val('fatherJob'),
            'motherJob': get_val('motherJob'),
            'pProvince': get_val('pProvince'),
            'pDistrict': get_val('pDistrict'),
            'pCommune': get_val('pCommune'),
            'pVillage': get_val('pVillage'),
            'pEmail': get_val('pEmail'),
            'pTelegramId': get_val('pTelegramId'),
            'gName': get_val('gName'),
            'gPhone': get_val('gPhone'),
            'gIsThe': get_val('gIsThe'),
            'gHome': get_val('gHome'),
            'gStreet': get_val('gStreet'),
            'gGroup': get_val('gGroup'),
            'gProvince': get_val('gProvince'),
            'gDistrict': get_val('gDistrict'),
            'gCommune': get_val('gCommune'),
            'gVillage': get_val('gVillage'),
            'myChilds': get_val('myChilds'),
            'status': get_val('status'),
            'created_at': format_date(get_val('created_at')),
            'updated_at': format_date(get_val('updated_at'))
        }
        
        return {
            "parent": parent,
            "message": "Parent retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving parent: {str(e)}")


@router.get("/parents/{parent_id}/students")
async def get_students_by_parent(
    parent_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_active_user)
):
    """Get all students for a specific parent using myChilds column"""
    from ...services.child_access import assert_can_access_parent_record

    # This returns full student rows (s.*), which include the password hash,
    # date of birth and phone number. Without this check any signed-in user
    # could walk parent_id and dump the whole school's student records.
    assert_can_access_parent_record(db, current_user, parent_id)

    try:
        # 1. Get parent's myChilds
        parent_query = text("SELECT myChilds FROM parents WHERE id = :parent_id")
        parent_result = db.execute(parent_query, {"parent_id": parent_id}).fetchone()
        
        if not parent_result or not parent_result[0]:
            return {"students": [], "message": "No students found for this parent"}
            
        my_childs_str = parent_result[0] # e.g. "4,43"
        # Filter out empty strings and non-digit values
        student_ids = []
        if my_childs_str:
            student_ids = [int(x.strip()) for x in str(my_childs_str).split(',') if x.strip().isdigit()]
        
        if not student_ids:
             return {"students": [], "message": "No valid student IDs found"}

        # 2. Fetch students WHERE id IN student_ids
        # We dynamically build the IN clause parameters
        placeholders = ','.join([f':id_{i}' for i in range(len(student_ids))])
        params = {f'id_{i}': uid for i, uid in enumerate(student_ids)}
        
        # Join with learning to get current class info if possible
        # We take the latest learning record (highest ID) for the current academic year ideally
        # But for simplicity and speed, let's fetch students first, then attach basic class info or join simple
        
        # Try full query with joins first
        try:
            query_sql = f"""
                SELECT 
                    s.*,
                    b.branch_name,
                    ur.avatar as ur_avatar,
                    TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age
                FROM students s
                LEFT JOIN branch b ON b.id = s.branch
                LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
                WHERE s.id IN ({placeholders})
                ORDER BY s.child_order ASC, s.kName ASC
            """
            result = db.execute(text(query_sql), params)
            rows = result.fetchall()
        except Exception as e:
            error_str = str(e)
            if "1146" in error_str and "branch" in error_str:
                # Fallback query if branch table missing
                logger.warning(f"Table missing in get_students_by_parent, using fallback query: {error_str}")
                query_sql = f"""
                    SELECT 
                        s.*,
                        NULL as branch_name,
                        ur.avatar as ur_avatar,
                        TIMESTAMPDIFF(YEAR, s.dob, CURDATE()) as age
                    FROM students s
                    LEFT JOIN users_resource ur ON ur.user_id = s.id AND ur.user_type = 'student'
                    WHERE s.id IN ({placeholders})
                    ORDER BY s.child_order ASC, s.kName ASC
                """
                result = db.execute(text(query_sql), params)
                rows = result.fetchall()
            else:
                raise e
        
        # Define helpers again inside function scope or use shared ones if refactored
        def get_val(row, key, default=None):
            try:
                val = getattr(row, key, None)
                if val is not None:
                    return val
                if hasattr(row, '_mapping'):
                    return row._mapping.get(key, default)
                if hasattr(row, '__getitem__'):
                    return row[key]
                return default
            except (AttributeError, KeyError, IndexError):
                return default
        
        def format_date(val):
            if val and hasattr(val, 'isoformat'):
                return val.isoformat()
            return None
            
        def format_binary(val):
            if val is None:
                return None
            try:
                # If bytes, encode to base64
                import base64
                if isinstance(val, bytes):
                    return base64.b64encode(val).decode('utf-8')
                # If already string (and maybe base64 or just a path), return as is
                if isinstance(val, str):
                    return val
                return None
            except Exception:
                return None

        students = []
        for row in rows:
            student_id = get_val(row, 'id')
            
            # Fetch latest learning with teacher info
            # Fetch latest learning with teacher info AND IDs needed for attendance filtering
            learning_query = text("""
                SELECT 
                    l.id,
                    l.programid,
                    l.gradeid,
                    l.shiftid,
                    l.academicid,
                    l.grade_type_id,
                    p.program_name, 
                    COALESCE(NULLIF(p.short_code, ''), p.program_name) as program_short_code,
                    g.grade_name, 
                    sh.shift_name,
                    b.branch_name,
                    gt.type_name as grade_type_name,
                    CASE 
                        WHEN u.isForeigner = 1 THEN COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                        WHEN u.isForeigner = 2 THEN COALESCE(NULLIF(u.eName, ''), NULLIF(u.kName, ''), 'Unknown')
                        ELSE COALESCE(NULLIF(u.kName, ''), NULLIF(u.eName, ''), 'Unknown')
                    END as teacher_name,
                    u.id as teacher_id
                FROM learning l
                LEFT JOIN program p ON l.programid = p.id
                LEFT JOIN grade g ON l.gradeid = g.id
                LEFT JOIN shift sh ON l.shiftid = sh.id
                LEFT JOIN branch b ON g.branch_id = b.id
                LEFT JOIN grade_type gt ON l.grade_type_id = gt.id
                LEFT JOIN class_teachers ct ON (
                    l.programid = ct.program_id AND 
                    l.gradeid = ct.grade_id AND 
                    COALESCE(l.grade_type_id, -1) = COALESCE(ct.grade_type_id, -1) AND
                    l.shiftid = ct.shift_id AND 
                    g.branch_id = ct.branch_id AND 
                    l.academicid = ct.academic_id
                )
                LEFT JOIN users u ON ct.teacher_id = u.id
                WHERE l.studentid = :sid
                ORDER BY l.id DESC LIMIT 1
            """)
            l_row = db.execute(learning_query, {'sid': student_id}).fetchone()
            
            program_name = get_val(l_row, 'program_name')
            grade_name = get_val(l_row, 'grade_name')
            shift_name = get_val(l_row, 'shift_name')
            branch_name = get_val(l_row, 'branch_name') or get_val(row, 'branch_name')
            grade_type_name = get_val(l_row, 'grade_type_name')
            teacher_name = get_val(l_row, 'teacher_name')
            teacher_id = get_val(l_row, 'teacher_id')
            program_short_code = get_val(l_row, 'program_short_code')
            # Real IDs for attendance filtering
            l_id = get_val(l_row, 'id')
            program_id = get_val(l_row, 'programid')
            grade_id = get_val(l_row, 'gradeid')
            shift_id = get_val(l_row, 'shiftid')
            academic_id = get_val(l_row, 'academicid')
            grade_type_id = get_val(l_row, 'grade_type_id')

            # Get created_at value and provide fallback if NULL
            created_at_value = get_val(row, 'created_at')
            if created_at_value is None:
                # For existing students with NULL created_at, use a reasonable default
                # This represents when the school system was likely first deployed
                created_at_value = '2022-01-01T00:00:00'

            student = {
                'id': student_id,
                'studentid': get_val(row, 'studentid'),
                'optional_id': get_val(row, 'optional_id'),
                'username': get_val(row, 'username'),
                'kName': get_val(row, 'kName'),
                'eName': get_val(row, 'eName'),
                'gender': get_val(row, 'gender'),
                'dob': format_date(get_val(row, 'dob')),
                'image': get_val(row, 'ur_avatar'),
                'student_phone': get_val(row, 'student_phone'),
                'is_foreigner': get_val(row, 'is_foreigner'),
                'province': get_val(row, 'province'),
                'district': get_val(row, 'district'),
                'commune': get_val(row, 'commune'),
                'village': get_val(row, 'village'),
                'previousSchool': get_val(row, 'previousSchool'),
                'leaveDate': format_date(get_val(row, 'leaveDate')),
                'myparents': get_val(row, 'myparents'),
                'child_order': get_val(row, 'child_order'),
                'academic': get_val(row, 'academic'),
                'branch': get_val(row, 'branch'),
                'status': get_val(row, 'status'),
                'student_noted': get_val(row, 'student_noted'),
                'created_at': format_date(created_at_value),
                'updated_at': format_date(get_val(row, 'updated_at')),
                'program_name': program_name,
                'grade_name': grade_name,
                'shift_name': shift_name,
                'branch_name': branch_name,
                'teacher_name': teacher_name,
                'teacher_id': teacher_id,
                'program_short_code': program_short_code,
                'age': get_val(row, 'age'),
                'learnings': [{
                    'id': l_id or 0,
                    'program_id': program_id,
                    'grade_id': grade_id,
                    'shift_id': shift_id,
                    'academic_id': academic_id,
                    'grade_type_id': grade_type_id,
                    'program_name': program_name,
                    'program_short_code': program_short_code,
                    'grade_name': grade_name,
                    'shift_name': shift_name,
                    'branch_name': branch_name,
                    'grade_type_name': grade_type_name,
                    'teacher_name': teacher_name,
                    'teacher_id': teacher_id
                }] if program_name else []
            }
            students.append(student)
            
        return {
            "students": students,
            "message": "Students retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error fetching students for parent {parent_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error retrieving students: {str(e)}")

