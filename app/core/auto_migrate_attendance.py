"""
Auto-migration for Attendance Audit & Statistics tables.
Creates tables automatically when API starts.
"""
from sqlalchemy import inspect, text
import logging

logger = logging.getLogger(__name__)


def create_attendance_audit_table(engine):
    """Create attendance_audit_log table if it doesn't exist"""
    try:
        inspector = inspect(engine)
        if "attendance_audit_log" not in inspector.get_table_names():
            logger.info("Creating attendance_audit_log table...")
            
            create_table_sql = """
            CREATE TABLE attendance_audit_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                user_name VARCHAR(200) NOT NULL,
                user_role VARCHAR(50) NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                change_description TEXT,
                student_id INT,
                student_name VARCHAR(200),
                class_id INT,
                class_description VARCHAR(300),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at_khmer VARCHAR(50),
                ip_address VARCHAR(50),
                user_agent VARCHAR(500),
                branch_id INT,
                INDEX idx_user_id (user_id),
                INDEX idx_student_id (student_id),
                INDEX idx_branch_id (branch_id),
                INDEX idx_created_at (created_at),
                INDEX idx_action_type (action_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            
            with engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
            
            logger.info("✅ attendance_audit_log table created successfully")
        else:
            logger.debug("✅ attendance_audit_log table already exists")
    except Exception as e:
        logger.error(f"❌ Error creating attendance_audit_log table: {e}")


def create_attendance_statistics_table(engine):
    """Create attendance_statistics table if it doesn't exist"""
    try:
        inspector = inspect(engine)
        if "attendance_statistics" not in inspector.get_table_names():
            logger.info("Creating attendance_statistics table...")
            
            create_table_sql = """
            CREATE TABLE attendance_statistics (
                id INT AUTO_INCREMENT PRIMARY KEY,
                branch_id INT NOT NULL,
                program_id INT NOT NULL,
                grade_id INT NOT NULL,
                shift_id INT NOT NULL,
                academic_id INT NOT NULL,
                statistic_date DATE NOT NULL,
                day_of_week INT NOT NULL,
                month INT NOT NULL,
                year INT NOT NULL,
                first_attendance_time TIMESTAMP,
                last_attendance_time TIMESTAMP,
                average_attendance_time TIMESTAMP,
                first_attendance_minutes INT,
                last_attendance_minutes INT,
                average_attendance_minutes FLOAT,
                total_students INT DEFAULT 0,
                marked_present INT DEFAULT 0,
                marked_absent INT DEFAULT 0,
                marked_late INT DEFAULT 0,
                marked_permission INT DEFAULT 0,
                primary_teacher_id INT,
                primary_teacher_name VARCHAR(200),
                peak_hour INT,
                peak_hour_count INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                statistic_date_khmer VARCHAR(100),
                INDEX idx_branch_program_grade (branch_id, program_id, grade_id),
                INDEX idx_shift_academic (shift_id, academic_id),
                INDEX idx_statistic_date (statistic_date),
                INDEX idx_month (month),
                INDEX idx_year (year),
                INDEX idx_day_of_week (day_of_week)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            
            with engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
            
            logger.info("✅ attendance_statistics table created successfully")
        else:
            logger.debug("✅ attendance_statistics table already exists")
    except Exception as e:
        logger.error(f"❌ Error creating attendance_statistics table: {e}")


def run_attendance_migrations(engine):
    """Run all attendance-related migrations"""
    logger.info("🔍 Running attendance audit & statistics migrations...")
    
    create_attendance_audit_table(engine)
    create_attendance_statistics_table(engine)
    
    logger.info("✅ Attendance migrations completed")
