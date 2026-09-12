from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def check_and_update_schema(db: Session):
    """
    Checks for missing columns in the database and adds them if necessary.
    This runs on application startup.
    """
    try:
        logger.info("Checking database schema for required column updates...")
        
        # Columns to check for 'users' table
        # Format: (column_name, column_definition)
        users_columns = [
            ("bankAccountNumber", "VARCHAR(50) NULL"),
            ("bankAccountName", "VARCHAR(100) NULL"),
            ("bankName", "VARCHAR(100) NULL"),
            ("baseSalary", "DECIMAL(10, 2) NULL"),
            ("nssfNumber", "VARCHAR(50) NULL"),
            ("isNssf", "INT DEFAULT 0"),
            ("isResident", "INT DEFAULT 1"),
            ("hasSpouse", "INT DEFAULT 0"),
            ("numberOfDependents", "INT DEFAULT 0")
        ]
        
        for col_name, col_def in users_columns:
            # Check if column exists
            check_sql = text(f"SHOW COLUMNS FROM users LIKE '{col_name}'")
            result = db.execute(check_sql).fetchone()
            
            if not result:
                logger.info(f"Adding missing column to users table: {col_name}")
                alter_sql = text(f"ALTER TABLE users ADD COLUMN `{col_name}` {col_def}")
                db.execute(alter_sql)
                logger.info(f"✅ Added {col_name}")
            # else:
            #     logger.debug(f"Column {col_name} already exists.")

        # Columns to check for 'attendance_user_assignments' table
        aua_columns = [
            ("start_date", "DATE DEFAULT CURRENT_DATE"),
            ("end_date", "DATE NULL")
        ]

        for col_name, col_def in aua_columns:
            # Check if column exists
            check_sql = text(f"SHOW COLUMNS FROM attendance_user_assignments LIKE '{col_name}'")
            result = db.execute(check_sql).fetchone()
            
            if not result:
                logger.info(f"Adding missing column to attendance_user_assignments table: {col_name}")
                alter_sql = text(f"ALTER TABLE attendance_user_assignments ADD COLUMN `{col_name}` {col_def}")
                db.execute(alter_sql)
                logger.info(f"✅ Added {col_name}")

        # pickup_requests.pickup_branch_id — required for branch-scoped queue / my-children-status
        try:
            pr_check = text("SHOW COLUMNS FROM pickup_requests LIKE 'pickup_branch_id'")
            pr_row = db.execute(pr_check).fetchone()
            if not pr_row:
                logger.info("Adding missing column pickup_requests.pickup_branch_id")
                db.execute(
                    text(
                        "ALTER TABLE pickup_requests ADD COLUMN `pickup_branch_id` INT NULL"
                    )
                )
                try:
                    db.execute(
                        text(
                            """
                            UPDATE pickup_requests pr
                            INNER JOIN students s ON pr.student_id = s.id
                            SET pr.pickup_branch_id = CAST(s.branch AS UNSIGNED)
                            WHERE pr.pickup_branch_id IS NULL
                              AND s.branch IS NOT NULL
                              AND TRIM(s.branch) REGEXP '^[0-9]+$'
                            """
                        )
                    )
                except Exception as bf:
                    logger.warning(
                        "pickup_branch_id backfill skipped (non-fatal): %s", bf
                    )
                logger.info("✅ Added pickup_requests.pickup_branch_id")
        except Exception as pr_ex:
            logger.warning(
                "pickup_requests.pickup_branch_id check skipped: %s", pr_ex
            )

        try:
            db.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS pickup_branch_calling (
                        academic_id INT NOT NULL,
                        branch_id INT NOT NULL,
                        calling_enabled TINYINT(1) NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
                        PRIMARY KEY (academic_id, branch_id),
                        KEY idx_pbc_academic (academic_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
            )
            logger.info("Ensured pickup_branch_calling table exists")
        except Exception as pbc_ex:
            logger.warning(
                "pickup_branch_calling table check skipped: %s", pbc_ex
            )

        # student_profile_edit_requests — columns added after the table's creation
        try:
            spe_columns = [
                ("previousSchool", "VARCHAR(100) NULL"),
                ("avatar", "VARCHAR(255) NULL"),
                ("previous_values", "TEXT NULL"),
            ]
            for col_name, col_def in spe_columns:
                exists = db.execute(
                    text(
                        f"SHOW COLUMNS FROM student_profile_edit_requests LIKE '{col_name}'"
                    )
                ).fetchone()
                if not exists:
                    logger.info(
                        f"Adding missing column student_profile_edit_requests.{col_name}"
                    )
                    db.execute(
                        text(
                            f"ALTER TABLE student_profile_edit_requests ADD COLUMN `{col_name}` {col_def}"
                        )
                    )
                    logger.info(f"✅ Added student_profile_edit_requests.{col_name}")
        except Exception as spe_ex:
            logger.warning(
                "student_profile_edit_requests column check skipped: %s", spe_ex
            )

        # students.submitted_by_parent — marks parent-app self-registrations.
        try:
            exists = db.execute(
                text("SHOW COLUMNS FROM students LIKE 'submitted_by_parent'")
            ).fetchone()
            if not exists:
                logger.info("Adding missing column students.submitted_by_parent")
                db.execute(
                    text(
                        "ALTER TABLE students ADD COLUMN `submitted_by_parent` INT NOT NULL DEFAULT 0"
                    )
                )
                logger.info("✅ Added students.submitted_by_parent")
        except Exception as sbp_ex:
            logger.warning("students.submitted_by_parent check skipped: %s", sbp_ex)

        db.commit()
        logger.info("Schema check completed.")
        
    except Exception as e:
        logger.error(f"Error checking/updating schema: {e}")
        db.rollback()
