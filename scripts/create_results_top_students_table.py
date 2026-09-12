from sqlalchemy import text

from app.core.database import SessionLocal


SQL = """
CREATE TABLE IF NOT EXISTS results_top_students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    featured_batch_id VARCHAR(36) NOT NULL,
    academic_id INT NOT NULL,
    program_id INT NOT NULL,
    grade_id INT NOT NULL,
    shift_id INT NOT NULL,
    grade_type_id INT NULL,
    student_id INT NOT NULL,
    rank INT NOT NULL,
    average DECIMAL(10,2) NULL,
    grade VARCHAR(20) NULL,
    marks_system_id INT NULL,
    result_name VARCHAR(255) NULL,
    exam_name VARCHAR(255) NULL,
    exam_type VARCHAR(50) NULL,
    period VARCHAR(50) NULL,
    is_active INT NOT NULL DEFAULT 1,
    featured_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_rts_batch (featured_batch_id),
    INDEX idx_rts_class (academic_id, program_id, grade_id, shift_id, grade_type_id),
    INDEX idx_rts_student (student_id),
    INDEX idx_rts_active (is_active)
);
"""


def main():
    db = SessionLocal()
    try:
        db.execute(text(SQL))
        db.commit()
        print("✅ results_top_students table is ready")
    except Exception as e:
        db.rollback()
        print(f"❌ Failed to create table: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
