"""
Auto-migration module for applying performance indexes on startup.
Runs automatically when the API starts.
"""
from sqlalchemy import inspect, text
import logging
import hashlib

logger = logging.getLogger(__name__)

INDEX_MIGRATIONS = [
    # Attendance table indexes
    {
        "name": "idx_attendance_student_date",
        "table": "daily_attendance",
        "sql": "CREATE INDEX idx_attendance_student_date ON daily_attendance(student_id, attendance_date)",
    },
    {
        "name": "idx_attendance_program_grade_shift",
        "table": "daily_attendance",
        "sql": "CREATE INDEX idx_attendance_program_grade_shift ON daily_attendance(program_id, grade_id, shift_id, academic_id)",
    },
    {
        "name": "idx_attendance_academic",
        "table": "daily_attendance",
        "sql": "CREATE INDEX idx_attendance_academic ON daily_attendance(academic_id)",
    },
    # Learning table indexes
    {
        "name": "idx_learning_student_academic",
        "table": "learning",
        "sql": "CREATE INDEX idx_learning_student_academic ON learning(studentid, academicid)",
    },
    {
        "name": "idx_learning_grade_shift",
        "table": "learning",
        "sql": "CREATE INDEX idx_learning_grade_shift ON learning(gradeid, shiftid)",
    },
    {
        "name": "idx_learning_program",
        "table": "learning",
        "sql": "CREATE INDEX idx_learning_program ON learning(programid)",
    },
    # Class teachers indexes
    {
        "name": "idx_class_teachers_teacher_academic",
        "table": "class_teachers",
        "sql": "CREATE INDEX idx_class_teachers_teacher_academic ON class_teachers(teacher_id, academic_id)",
    },
    {
        "name": "idx_class_teachers_grade_shift",
        "table": "class_teachers",
        "sql": "CREATE INDEX idx_class_teachers_grade_shift ON class_teachers(grade_id, shift_id, academic_id)",
    },
    # Marks indexes
    {
        "name": "idx_marks_input_student_academic",
        "table": "marks_input",
        "sql": "CREATE INDEX idx_marks_input_student_academic ON marks_input(student_id, academic_id)",
    },
    {
        "name": "idx_marks_input_marks_system",
        "table": "marks_input",
        "sql": "CREATE INDEX idx_marks_input_marks_system ON marks_input(marks_system_id, student_id)",
    },
    # Students indexes
    {
        "name": "idx_students_branch_status",
        "table": "students",
        "sql": "CREATE INDEX idx_students_branch_status ON students(branch, status)",
    },
    {
        "name": "idx_students_academic",
        "table": "students",
        "sql": "CREATE INDEX idx_students_academic ON students(academic)",
    },
    {
        "name": "idx_students_program_grade",
        "table": "students",
        "sql": "CREATE INDEX idx_students_program_grade ON students(programid, gradeid)",
    },
    # Events and Forms indexes
    {
        "name": "idx_events_hot_createdat",
        "table": "events",
        "sql": "CREATE INDEX idx_events_hot_createdat ON events(is_hot, created_at)",
    },
    {
        "name": "idx_forms_program_grade",
        "table": "forms",
        "sql": "CREATE INDEX idx_forms_program_grade ON forms(program, grade, shift)",
    },
    # Holiday indexes
    {
        "name": "idx_holiday_dates",
        "table": "holiday_tbl",
        "sql": "CREATE INDEX idx_holiday_dates ON holiday_tbl(start_date, end_date)",
    },
    {
        "name": "idx_holiday_program_grade_shift",
        "table": "holiday_tbl",
        "sql": "CREATE INDEX idx_holiday_program_grade_shift ON holiday_tbl(program, grade, shift)",
    },
    # Fee services indexes
    {
        "name": "idx_fee_services_grade_program",
        "table": "fee_services",
        "sql": "CREATE INDEX idx_fee_services_grade_program ON fee_services(grade, program)",
    },
    # Users composite index
    {
        "name": "idx_users_workplace_role_status",
        "table": "users",
        "sql": "CREATE INDEX idx_users_workplace_role_status ON users(workplace, role, status)",
    },
    # Pickup queue indexes: branch/global FIFO reads, cooldown lookup, and
    # duplicate-active checks are all hot paths during dismissal time.
    {
        "name": "idx_pickup_academic_status_requested",
        "table": "pickup_requests",
        "sql": "CREATE INDEX idx_pickup_academic_status_requested ON pickup_requests(academic_id, status, requested_at, id)",
    },
    {
        "name": "idx_pickup_branch_queue",
        "table": "pickup_requests",
        "sql": "CREATE INDEX idx_pickup_branch_queue ON pickup_requests(academic_id, pickup_branch_id, status, requested_at, id)",
    },
    {
        "name": "idx_pickup_parent_student_latest",
        "table": "pickup_requests",
        "sql": "CREATE INDEX idx_pickup_parent_student_latest ON pickup_requests(parent_id, student_id, id)",
    },
    {
        "name": "idx_pickup_student_active",
        "table": "pickup_requests",
        "sql": "CREATE INDEX idx_pickup_student_active ON pickup_requests(student_id, status)",
    },
]


def get_existing_indexes(inspector, table_name):
    """Get list of existing index names for a table"""
    try:
        indexes = inspector.get_indexes(table_name)
        return {idx["name"] for idx in indexes}
    except Exception:
        return set()


def apply_index_migrations(engine):
    """
    Apply performance indexes to the database.
    Safe to run multiple times (idempotent).
    """
    logger.info("🔍 Checking for missing performance indexes...")
    
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        
        applied_count = 0
        skipped_count = 0
        error_count = 0
        
        with engine.connect() as conn:
            for index_info in INDEX_MIGRATIONS:
                table_name = index_info["table"]
                index_name = index_info["name"]
                index_sql = index_info["sql"]
                
                # Skip if table doesn't exist
                if table_name not in existing_tables:
                    logger.debug(f"⏭️  Table '{table_name}' doesn't exist yet, skipping index '{index_name}'")
                    skipped_count += 1
                    continue
                
                # Check if index already exists
                existing_indexes = get_existing_indexes(inspector, table_name)
                
                if index_name in existing_indexes:
                    logger.debug(f"✅ Index '{index_name}' already exists")
                    skipped_count += 1
                    continue
                
                # Create the index
                try:
                    logger.info(f"📊 Creating index '{index_name}' on table '{table_name}'...")
                    conn.execute(text(index_sql))
                    conn.commit()
                    logger.info(f"✅ Index '{index_name}' created successfully")
                    applied_count += 1

                    # Update inspector cache
                    existing_indexes.add(index_name)

                except Exception as e:
                    error_msg = str(e)
                    # Ignore "duplicate key name" errors (race condition)
                    if "Duplicate key name" in error_msg or "already exists" in error_msg:
                        logger.debug(f"✅ Index '{index_name}' already exists (concurrent creation)")
                        skipped_count += 1
                    # Ignore "column doesn't exist" errors (schema variation)
                    elif "doesn't exist" in error_msg or "Key column" in error_msg:
                        logger.debug(f"⏭️  Index '{index_name}' skipped (column doesn't exist in this schema)")
                        skipped_count += 1
                    else:
                        logger.error(f"❌ Failed to create index '{index_name}': {e}")
                        error_count += 1
        
        logger.info(f"📈 Index migration complete: {applied_count} applied, {skipped_count} skipped, {error_count} errors")
        return applied_count, skipped_count, error_count
        
    except Exception as e:
        logger.error(f"❌ Critical error during index migration: {e}")
        return 0, 0, 1


def verify_indexes(engine):
    """Verify that critical indexes exist and return stats"""
    try:
        inspector = inspect(engine)
        critical_tables = ["daily_attendance", "learning", "students", "marks_input"]
        
        stats = {
            "total_indexes": 0,
            "missing_critical": [],
        }
        
        for table in critical_tables:
            if table in inspector.get_table_names():
                indexes = inspector.get_indexes(table)
                stats["total_indexes"] += len(indexes)
            else:
                stats["missing_critical"].append(table)
        
        return stats
    except Exception as e:
        logger.error(f"Failed to verify indexes: {e}")
        return {"total_indexes": 0, "missing_critical": [], "error": str(e)}
