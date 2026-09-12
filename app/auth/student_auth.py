from sqlalchemy.orm import Session
from ..models import Student
import bcrypt
import asyncio
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_student_by_username(db: Session, username: str) -> Student | None:
    """Get student by username."""
    from sqlalchemy.orm import defer
    return db.query(Student).options(defer(Student.image)).filter(Student.username == username).first()

def verify_student_password(student: Student, password: str) -> bool:
    """Verify student password."""
    if not student.password:
        return False
    # return pwd_context.verify(password, student.password)
    if isinstance(password, str):
        password = password.encode('utf-8')
    hashed = student.password.encode('utf-8') if isinstance(student.password, str) else student.password
    try:
        return bcrypt.checkpw(password, hashed)
    except ValueError:
        # Stored value is not a bcrypt hash (legacy import, plaintext). That is a
        # failed login, not a 500.
        import logging

        logging.getLogger(__name__).warning(
            "Student %s has a password that is not a valid bcrypt hash", student.id
        )
        return False

async def async_verify_student_password(student: Student, password: str) -> bool:
    """Async wrapper to prevent bcrypt from blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, verify_student_password, student, password)

def authenticate_student(db: Session, username: str, password: str) -> Student | None:
    """Authenticate student with username and password."""
    student = get_student_by_username(db, username)
    if not student:
        return None
    if not verify_student_password(student, password):
        return None
    return student

async def async_authenticate_student(db: Session, username: str, password: str) -> Student | None:
    """Authenticate student asynchronously."""
    student = get_student_by_username(db, username)
    if not student:
        return None
        
    db.expunge(student)
    db.rollback()
    
    is_valid = await async_verify_student_password(student, password)
    if not is_valid:
        return None
    return student
