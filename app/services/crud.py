from sqlalchemy.orm import Session
from sqlalchemy import and_, text
from typing import List, Optional
from fastapi import HTTPException, status

from ..models import User, Student, Teacher, Class, Enrollment, UserResource
from ..schemas import (
    UserCreate, StudentCreate, StudentUpdate,
    TeacherCreate, TeacherUpdate, ClassCreate, ClassUpdate,
    EnrollmentCreate, EnrollmentUpdate
)
from .utils import get_password_hash
from .storage_service import StorageService
def create_user(db: Session, user: UserCreate) -> User:
    """Create a new user."""
    hashed_password = get_password_hash(user.password)
    
    # Create user data dictionary, excluding password
    # Create user data dictionary, excluding password
    user_data = user.dict(exclude={"password"})
    user_data['password'] = hashed_password

    # Normalize Gender to Khmer (ស្រី/ប្រុស)
    if user.gender:
        g = user.gender.strip().lower()
        if g in ['female', 'f', 'woman', 'girl', 'lady']:
            user_data['gender'] = 'ស្រី'
        elif g in ['male', 'm', 'man', 'boy', 'gentleman']:
            user_data['gender'] = 'ប្រុស'
        # Else keep as is (assuming it might already be Khmer or another accepted value)

    # Extract image / signature to save in UserResource instead.
    # NOTE: The Flutter registration payload always sends image=null now.
    # Avatar is uploaded separately via /profile/me/avatar after registration.
    image_data = user_data.get('image')  # Will be None from registration
    user_data['image'] = None
    user_data['signature'] = None

    # --- Generate Unique ID ---
    # Format: CODE-XXXX (e.g., CDA-0012)
    # 1. Get Department Code
    dept_code = "EMP" # Default fallback
    if user.departmentId:
        try:
            # Execute raw SQL to get department code
            result = db.execute(
                text("SELECT code FROM department WHERE id = :id"),
                {"id": user.departmentId}
            ).first()
            if result and result[0]:
                dept_code = result[0]
        except Exception:
            pass # Keep default if error
            
    # 2. Get last ID to increment
    try:
        # Get the max ID from users table
        result = db.execute(text("SELECT MAX(id) FROM users")).first()
        last_id = result[0] if result and result[0] else 0
        next_id = last_id + 1
    except Exception:
        next_id = 9999 # Fallback if something goes wrong
        
    # 3. Format generated ID
    generated_id = f"{dept_code}-{next_id:04d}"
    
    # Set the generated uniqueId in user_data
    user_data['uniqueId'] = generated_id
    
    db_user = User(**user_data)
    db.add(db_user)
    db.flush() # Flush to get the ID for the new user
    
    # Create UserResource entry with the image/avatar
    if image_data:
        # Upload image using StorageService
        avatar_path = StorageService.upload_file(
            file_data=image_data,
            folder="avatars",
            filename=f"{db_user.username}_avatar.jpg",
            content_type="image/jpeg"
        )
        
        if avatar_path:
            # Determine user type based on role? For now default to 'employee' or 'teacher' based on context?
            # The prompt mentioned "users parents students". Detailed logic might be needed.
            # For now, let's assume 'employee' as default for general User model, 
            # or we could infer from role. But 'employee' is a safe generic for staff.
            user_type = 'employee' 
            
            user_resource = UserResource(
                user_id=db_user.id,
                user_type=user_type,
                avatar=avatar_path
            )
            db.add(user_resource)
    
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username."""
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email."""
    return db.query(User).filter(User.email == email).first()

# Student CRUD operations
def create_student(db: Session, student: StudentCreate) -> Student:
    """Create a new student."""
    # Check if student_id already exists
    if db.query(Student).filter(Student.student_id == student.student_id).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student ID already exists"
        )
    
    # Check if email already exists
    if db.query(Student).filter(Student.email == student.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    db_student = Student(**student.dict())
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

def get_student(db: Session, student_id: int) -> Optional[Student]:
    """Get student by ID."""
    return db.query(Student).filter(Student.id == student_id).first()

def get_student_by_student_id(db: Session, student_id: str) -> Optional[Student]:
    """Get student by student ID."""
    return db.query(Student).filter(Student.student_id == student_id).first()

def get_students(db: Session, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None) -> List[Student]:
    """Get list of students with optional filtering."""
    query = db.query(Student)
    if is_active is not None:
        query = query.filter(Student.is_active == is_active)
    return query.offset(skip).limit(limit).all()

def update_student(db: Session, student_id: int, student_update: StudentUpdate) -> Optional[Student]:
    """Update student information."""
    db_student = db.query(Student).filter(Student.id == student_id).first()
    if not db_student:
        return None
    
    update_data = student_update.dict(exclude_unset=True)
    
    # Check email uniqueness if email is being updated
    if "email" in update_data:
        existing_student = db.query(Student).filter(
            and_(Student.email == update_data["email"], Student.id != student_id)
        ).first()
        if existing_student:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
    
    for field, value in update_data.items():
        setattr(db_student, field, value)
    
    db.commit()
    db.refresh(db_student)
    return db_student

def delete_student(db: Session, student_id: int) -> bool:
    """Delete a student (soft delete by setting is_active to False)."""
    db_student = db.query(Student).filter(Student.id == student_id).first()
    if not db_student:
        return False
    
    db_student.is_active = False
    db.commit()
    return True

# Teacher CRUD operations
def create_teacher(db: Session, teacher: TeacherCreate) -> Teacher:
    """Create a new teacher."""
    # Check if teacher_id already exists
    if db.query(Teacher).filter(Teacher.teacher_id == teacher.teacher_id).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teacher ID already exists"
        )
    
    # Check if email already exists
    if db.query(Teacher).filter(Teacher.email == teacher.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    db_teacher = Teacher(**teacher.dict())
    db.add(db_teacher)
    db.commit()
    db.refresh(db_teacher)
    return db_teacher

def get_teacher(db: Session, teacher_id: int) -> Optional[Teacher]:
    """Get teacher by ID."""
    return db.query(Teacher).filter(Teacher.id == teacher_id).first()

def get_teacher_by_teacher_id(db: Session, teacher_id: str) -> Optional[Teacher]:
    """Get teacher by teacher ID."""
    return db.query(Teacher).filter(Teacher.teacher_id == teacher_id).first()

def get_teachers(db: Session, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None) -> List[Teacher]:
    """Get list of teachers with optional filtering."""
    query = db.query(Teacher)
    if is_active is not None:
        query = query.filter(Teacher.is_active == is_active)
    return query.offset(skip).limit(limit).all()

def update_teacher(db: Session, teacher_id: int, teacher_update: TeacherUpdate) -> Optional[Teacher]:
    """Update teacher information."""
    db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not db_teacher:
        return None
    
    update_data = teacher_update.dict(exclude_unset=True)
    
    # Check email uniqueness if email is being updated
    if "email" in update_data:
        existing_teacher = db.query(Teacher).filter(
            and_(Teacher.email == update_data["email"], Teacher.id != teacher_id)
        ).first()
        if existing_teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists"
            )
    
    for field, value in update_data.items():
        setattr(db_teacher, field, value)
    
    db.commit()
    db.refresh(db_teacher)
    return db_teacher

def delete_teacher(db: Session, teacher_id: int) -> bool:
    """Delete a teacher (soft delete by setting is_active to False)."""
    db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not db_teacher:
        return False
    
    db_teacher.is_active = False
    db.commit()
    return True

# Class CRUD operations
def create_class(db: Session, class_data: ClassCreate) -> Class:
    """Create a new class."""
    # Check if teacher exists
    teacher = db.query(Teacher).filter(Teacher.id == class_data.teacher_id).first()
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teacher not found"
        )
    
    # Check if class_code already exists
    if db.query(Class).filter(Class.class_code == class_data.class_code).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class code already exists"
        )
    
    db_class = Class(**class_data.dict())
    db.add(db_class)
    db.commit()
    db.refresh(db_class)
    return db_class

def get_class(db: Session, class_id: int) -> Optional[Class]:
    """Get class by ID."""
    return db.query(Class).filter(Class.id == class_id).first()

def get_class_by_code(db: Session, class_code: str) -> Optional[Class]:
    """Get class by class code."""
    return db.query(Class).filter(Class.class_code == class_code).first()

def get_classes(db: Session, skip: int = 0, limit: int = 100, is_active: Optional[bool] = None) -> List[Class]:
    """Get list of classes with optional filtering."""
    query = db.query(Class)
    if is_active is not None:
        query = query.filter(Class.is_active == is_active)
    return query.offset(skip).limit(limit).all()

def update_class(db: Session, class_id: int, class_update: ClassUpdate) -> Optional[Class]:
    """Update class information."""
    db_class = db.query(Class).filter(Class.id == class_id).first()
    if not db_class:
        return None
    
    update_data = class_update.dict(exclude_unset=True)
    
    # Check if teacher exists if teacher_id is being updated
    if "teacher_id" in update_data:
        teacher = db.query(Teacher).filter(Teacher.id == update_data["teacher_id"]).first()
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teacher not found"
            )
    
    for field, value in update_data.items():
        setattr(db_class, field, value)
    
    db.commit()
    db.refresh(db_class)
    return db_class

def delete_class(db: Session, class_id: int) -> bool:
    """Delete a class (soft delete by setting is_active to False)."""
    db_class = db.query(Class).filter(Class.id == class_id).first()
    if not db_class:
        return False
    
    db_class.is_active = False
    db.commit()
    return True

# Enrollment CRUD operations
def create_enrollment(db: Session, enrollment: EnrollmentCreate) -> Enrollment:
    """Create a new enrollment."""
    # Check if student exists
    student = db.query(Student).filter(Student.id == enrollment.student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student not found"
        )
    
    # Check if class exists
    class_obj = db.query(Class).filter(Class.id == enrollment.class_id).first()
    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class not found"
        )
    
    # Check if student is already enrolled in this class
    existing_enrollment = db.query(Enrollment).filter(
        and_(
            Enrollment.student_id == enrollment.student_id,
            Enrollment.class_id == enrollment.class_id
        )
    ).first()
    
    if existing_enrollment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student is already enrolled in this class"
        )
    
    db_enrollment = Enrollment(**enrollment.dict())
    db.add(db_enrollment)
    db.commit()
    db.refresh(db_enrollment)
    return db_enrollment

def get_enrollment(db: Session, enrollment_id: int) -> Optional[Enrollment]:
    """Get enrollment by ID."""
    return db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()

def get_enrollments(db: Session, skip: int = 0, limit: int = 100) -> List[Enrollment]:
    """Get list of enrollments."""
    return db.query(Enrollment).offset(skip).limit(limit).all()

def get_student_enrollments(db: Session, student_id: int) -> List[Enrollment]:
    """Get all enrollments for a specific student."""
    return db.query(Enrollment).filter(Enrollment.student_id == student_id).all()

def get_class_enrollments(db: Session, class_id: int) -> List[Enrollment]:
    """Get all enrollments for a specific class."""
    return db.query(Enrollment).filter(Enrollment.class_id == class_id).all()

def update_enrollment(db: Session, enrollment_id: int, enrollment_update: EnrollmentUpdate) -> Optional[Enrollment]:
    """Update enrollment information."""
    db_enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not db_enrollment:
        return None
    
    update_data = enrollment_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_enrollment, field, value)
    
    db.commit()
    db.refresh(db_enrollment)
    return db_enrollment

def delete_enrollment(db: Session, enrollment_id: int) -> bool:
    """Delete an enrollment."""
    db_enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not db_enrollment:
        return False
    
    db.delete(db_enrollment)
    db.commit()
    return True
