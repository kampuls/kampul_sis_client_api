from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pathlib import Path
import asyncio
import uvicorn
import time
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError
import html as html_lib
from urllib.parse import urlparse
import secrets

from alembic.config import Config
from alembic import command

from .core import settings, engine, SessionLocal
from .core.http_errors import json_safe_http_exception_handler
from .models.base import Base

# Import all models to ensure they are registered with Base.metadata
from .models import (
    SystemSettings,
    User,
    Subject,
    Student,
    Parent,
    Teacher,
    Class,
    Enrollment,
    Branch,
    Role,
    Department,
    Notification,
    AttendanceSchedule,
    AttendanceSystemSettings,
    AttendanceUserAssignment,
    AttendanceRecord,
    AttendanceScheduleException,
    AttendanceAllowedBranch,
    UserFinancials,
    WorkLocation,
    SalaryHistory,
    SalaryDeduction,
    SalaryBonus,
    Ad,
    AdClick,
    DeviceToken,
    DailyAttendance,
    LearningTimeSlot,
    LearningClassSchedule,
    LearningSessionLog,
    LearningScheduleException,
    TelegramAttendanceSettings,
    AppAdmin,
    StudentProfileEditRequest,
    SmartDownloadLink,
    MarketStore,
    MarketListing,
)
from .api.v1 import api_router
from .api.desktop import api_router as desktop_api_router
from .api.web import api_router as web_api_router
from .core.seed_permissions import seed_permissions
from .core.schema_check import check_and_update_schema
from .core.auto_migrate import sync_database_schema
from .core.migrations import run_migrations


async def run_database_migrations():
    """
    Run database migrations on startup to ensure schema is up to date.
    This replaces the need for external SQL files and manual migration scripts.
    """
    try:
        logger.info("Checking database schema for required migrations...")

        with engine.connect() as conn:
            inspector = inspect(engine)
            existing_tables = inspector.get_table_names()

            # Determine database type and capabilities
            is_mysql = engine.dialect.name == "mysql"
            is_sqlite = engine.dialect.name == "sqlite"
            supports_json = False
            supports_enum = False

            if is_mysql:
                try:
                    mysql_version_result = conn.execute(
                        text("SELECT VERSION() as version")
                    )
                    version_row = mysql_version_result.fetchone()
                    if version_row:
                        mysql_version = version_row[0]
                        # broadly check for 8.x or 5.7+ (simplified check)
                        supports_enum = mysql_version.startswith(
                            "8."
                        ) or mysql_version.startswith("9.")
                        supports_json = True  # Assumes reasonably modern MySQL
                except:
                    pass

                # ---------------------------------------------------------
                # Auto-detect and fix unsupported collations
                # ---------------------------------------------------------
                try:
                    db_name_row = conn.execute(text("SELECT DATABASE()")).fetchone()
                    if db_name_row and db_name_row[0]:
                        db_name = db_name_row[0]
                        
                        # Find tables with unsupported/different collation
                        wrong_collation_tables = conn.execute(
                            text("""
                                SELECT TABLE_NAME, TABLE_COLLATION 
                                FROM information_schema.TABLES 
                                WHERE TABLE_SCHEMA = :db_name 
                                AND TABLE_COLLATION != 'utf8mb4_unicode_ci'
                                AND TABLE_TYPE = 'BASE TABLE'
                            """),
                            {"db_name": db_name}
                        ).fetchall()
                        
                        if wrong_collation_tables:
                            logger.info(f"Found {len(wrong_collation_tables)} tables with wrong collation. Converting to utf8mb4_unicode_ci...")
                            for row in wrong_collation_tables:
                                table_name = row[0]
                                try:
                                    conn.execute(text(f"ALTER TABLE `{table_name}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"))
                                    conn.commit()
                                    logger.info(f"✅ Converted table: {table_name}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to convert {table_name}: {e}")
                except Exception as e:
                    logger.error(f"Error checking collations: {e}")

            # ---------------------------------------------------------
            # Global App Config Tables (auto-create)
            # ---------------------------------------------------------
            if is_mysql:
                # Results -> Top Students display preferences (GLOBAL)
                conn.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS results_top_students_display_settings (
                        id INT PRIMARY KEY,
                        avatar_chip_mode VARCHAR(10) NULL,
                        hide_section TINYINT(1) NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                )
                conn.execute(
                    text("""
                    INSERT INTO results_top_students_display_settings (id, avatar_chip_mode, hide_section)
                    VALUES (1, 'rank', 0)
                    ON DUPLICATE KEY UPDATE id = id
                """)
                )
                conn.commit()

                # OTP codes table (shared across all workers via DB, not in-memory)
                conn.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS otp_codes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255) NOT NULL,
                        otp_hash VARCHAR(255) NOT NULL,
                        expiry DATETIME NOT NULL,
                        attempts INT NOT NULL DEFAULT 0,
                        locked_until DATETIME NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_username (username),
                        INDEX idx_otp_expiry (expiry)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                )
                conn.commit()
                logger.info("✅ otp_codes table ready")

                # WebSocket cross-worker broadcast queue (DB pub/sub — no Redis needed)
                conn.execute(
                    text("""
                    CREATE TABLE IF NOT EXISTS ws_broadcast_queue (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        channel VARCHAR(100) NOT NULL,
                        payload JSON NOT NULL,
                        created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
                        INDEX idx_ws_channel_created (channel, created_at),
                        INDEX idx_ws_created (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """)
                )
                conn.commit()
                logger.info("✅ ws_broadcast_queue table ready")

            # ---------------------------------------------------------
            # Admin Logs Table
            # ---------------------------------------------------------
            if "admin_logs" not in existing_tables:
                logger.info("Creating admin_logs table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS admin_logs (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            action VARCHAR(255) NOT NULL,
                            details TEXT,
                            timestamp DATETIME NOT NULL,
                            INDEX idx_admin_logs_user (user_id),
                            INDEX idx_admin_logs_action (action)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE IF NOT EXISTS admin_logs (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            action VARCHAR(255) NOT NULL,
                            details TEXT,
                            timestamp DATETIME NOT NULL
                        )
                    """)
                    )
                conn.commit()
                logger.info("✅ Created admin_logs table")

            # ---------------------------------------------------------
            # 1. Core Columns Migrations (Daily Attendance & Parents)
            # ---------------------------------------------------------

            # Create daily_attendance table if it doesn't exist
            if "daily_attendance" not in existing_tables:
                logger.info("Creating daily_attendance table...")
                enum_def = (
                    "ENUM('teacher', 'parent', 'student')"
                    if supports_enum
                    else "VARCHAR(20)"
                )

                if is_mysql:
                    conn.execute(
                        text(f"""
                        CREATE TABLE daily_attendance (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            student_id INT NOT NULL,
                            program_id INT NOT NULL,
                            grade_id INT NOT NULL,
                            grade_type_id INT NOT NULL,
                            shift_id INT NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            attendance_date DATE NOT NULL,
                            academic_id INT,
                            note VARCHAR(50),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            created_by INT NOT NULL,
                            updated_by INT NOT NULL,
                            teacher_id INT NOT NULL,
                            created_by_type {enum_def} NOT NULL DEFAULT 'teacher',
                            INDEX idx_attendance_student (student_id),
                            INDEX idx_attendance_program (program_id),
                            INDEX idx_attendance_grade (grade_id),
                            INDEX idx_attendance_grade_type (grade_type_id),
                            INDEX idx_attendance_shift (shift_id),
                            INDEX idx_attendance_date (attendance_date),
                            INDEX ix_daily_attendance_created_by_type (created_by_type)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )


                else:
                    # SQLite fallback
                    conn.execute(
                        text("""
                        CREATE TABLE daily_attendance (
                            id INTEGER PRIMARY KEY,
                            student_id INTEGER NOT NULL,
                            program_id INTEGER NOT NULL,
                            grade_id INTEGER NOT NULL,
                            grade_type_id INTEGER NOT NULL,
                            shift_id INTEGER NOT NULL,
                            status VARCHAR(20) NOT NULL,
                            attendance_date DATE NOT NULL,
                            academic_id INTEGER,
                            note VARCHAR(50),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            created_by INTEGER NOT NULL,
                            updated_by INTEGER NOT NULL,
                            teacher_id INTEGER NOT NULL,
                            created_by_type VARCHAR(20) NOT NULL DEFAULT 'teacher'
                        )
                    """)
                    )
                conn.commit()
                logger.info("✅ Created daily_attendance table")
                # Recreate inspector to refresh metadata cache
                inspector = inspect(engine)
                existing_tables = inspector.get_table_names()

            # Check if daily_attendance table exists for column migrations
            # Note: We don't need an else block here because we create the table above if it doesn't exist
            if "daily_attendance" in existing_tables:
                # Check if created_by_type column exists
                columns = inspector.get_columns("daily_attendance")
                column_names = [col["name"] for col in columns]

                if "created_by_type" not in column_names:
                    logger.info(
                        "Adding created_by_type column to daily_attendance table..."
                    )

                    if supports_enum:
                        logger.info("Using ENUM type for created_by_type column")
                        conn.execute(
                            text("""
                            ALTER TABLE daily_attendance
                            ADD COLUMN created_by_type ENUM('teacher', 'parent', 'student') NOT NULL DEFAULT 'teacher'
                        """)
                        )
                    else:
                        logger.info(
                            f"Using VARCHAR type for created_by_type column ({engine.dialect.name})"
                        )
                        conn.execute(
                            text("""
                            ALTER TABLE daily_attendance
                            ADD COLUMN created_by_type VARCHAR(20) NOT NULL DEFAULT 'teacher'
                        """)
                        )

                    conn.execute(
                        text("""
                        CREATE INDEX ix_daily_attendance_created_by_type
                        ON daily_attendance(created_by_type)
                    """)
                    )

                    # Migrate existing data
                    conn.execute(
                        text(
                            "UPDATE daily_attendance SET created_by_type = 'parent' WHERE status = 'IsPermission'"
                        )
                    )
                    conn.execute(
                        text(
                            "UPDATE daily_attendance SET created_by_type = 'teacher' WHERE teacher_id IS NOT NULL"
                        )
                    )
                    conn.commit()
                    logger.info(
                        "✅ Successfully added created_by_type column and migrated data"
                    )

                if "note" in column_names:
                    col_info = next((c for c in columns if c["name"] == "note"), None)
                    if col_info and str(col_info.get("type", "")).lower().startswith(
                        "varchar"
                    ):
                        logger.info("Migrating daily_attendance note column to TEXT...")
                        try:
                            if is_mysql:
                                conn.execute(
                                    text(
                                        "ALTER TABLE daily_attendance MODIFY COLUMN note TEXT NULL"
                                    )
                                )
                                conn.commit()
                                logger.info(
                                    "✅ Successfully expanded daily_attendance note to TEXT"
                                )
                        except Exception as e:
                            logger.error(f"Error modifying daily_attendance note: {e}")

            # Check if status column exists in parents table
            if "parents" in existing_tables:
                parent_columns = inspector.get_columns("parents")
                parent_column_names = [col["name"] for col in parent_columns]
                if "status" not in parent_column_names:
                    logger.info("Adding status column to parents table...")
                    conn.execute(
                        text(
                            "ALTER TABLE parents ADD COLUMN status INT NOT NULL DEFAULT 1"
                        )
                    )
                    conn.execute(
                        text("CREATE INDEX ix_parents_status ON parents(status)")
                    )
                    conn.commit()
                    logger.info("✅ Successfully added status column to parents table")

                # Make token_version nullable with default 1, or add it if missing
                if "token_version" in parent_column_names:
                    col_info = next(
                        (c for c in parent_columns if c["name"] == "token_version"), None
                    )
                    if col_info and (not col_info.get("nullable", True) or col_info.get("default") is None):
                        logger.info("Making token_version nullable with default 1 in parents table...")
                        try:
                            if is_mysql:
                                conn.execute(
                                    text(
                                        "ALTER TABLE parents MODIFY COLUMN token_version INT NULL DEFAULT 1"
                                    )
                                )
                                conn.commit()
                                logger.info(
                                    "✅ Successfully made token_version nullable with default 1 in parents table"
                                )
                        except Exception as e:
                            logger.error(f"Error modifying parents.token_version: {e}")
                else:
                    logger.info("Adding token_version column to parents table...")
                    try:
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE parents ADD COLUMN token_version INT NULL DEFAULT 1"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE parents ADD COLUMN token_version INTEGER DEFAULT 1"
                                )
                            )
                        conn.commit()
                        logger.info(
                            "✅ Successfully added token_version column to parents table"
                        )
                    except Exception as e:
                        logger.error(f"Error adding parents.token_version: {e}")
            else:
                logger.warning("⚠️ parents table does not exist, skipping migration")

            # ---------------------------------------------------------
            # 1.5. Users Table Migrations
            # ---------------------------------------------------------
            if "users" in existing_tables:
                user_columns = inspector.get_columns("users")
                user_column_names = [col["name"] for col in user_columns]
                if "signatureImagePath" not in user_column_names:
                    logger.info("Adding signatureImagePath column to users table...")
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN signatureImagePath VARCHAR(500) NULL AFTER signature"
                        )
                    )
                    conn.commit()
                    logger.info(
                        "✅ Successfully added signatureImagePath column to users table"
                    )

                # Make token_version nullable if it isn't, or add it if missing
                if "token_version" in user_column_names:
                    col_info = next(
                        (c for c in user_columns if c["name"] == "token_version"), None
                    )
                    if col_info and not col_info.get("nullable", True):
                        logger.info("Making token_version nullable in users table...")
                        try:
                            if is_mysql:
                                conn.execute(
                                    text(
                                        "ALTER TABLE users MODIFY COLUMN token_version INT NULL DEFAULT 1"
                                    )
                                )
                                conn.commit()
                                logger.info(
                                    "✅ Successfully made token_version nullable in users table"
                                )
                        except Exception as e:
                            logger.error(f"Error modifying token_version: {e}")
                else:
                    logger.info("Adding token_version column to users table...")
                    try:
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE users ADD COLUMN token_version INT NULL DEFAULT 1"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1"
                                )
                            )
                        conn.commit()
                        logger.info(
                            "✅ Successfully added token_version column to users table"
                        )
                    except Exception as e:
                        logger.error(f"Error adding token_version: {e}")

            # ---------------------------------------------------------
            # 1.6. Branch Table Migrations
            # ---------------------------------------------------------
            if "branch" in existing_tables:
                branch_columns = inspector.get_columns("branch")
                branch_column_names = [col["name"] for col in branch_columns]

                new_columns = [
                    ("image_header_path", "VARCHAR(255)"),
                    ("director_signature_path", "VARCHAR(255)"),
                    ("headTeacher_signature_path", "VARCHAR(255)"),
                    ("stamp_path", "VARCHAR(255)"),
                    ("director_kName", "VARCHAR(255)"),
                    ("director_eName", "VARCHAR(255)"),
                    ("headTeacher_kName", "VARCHAR(255)"),
                    ("headTeacher_eName", "VARCHAR(255)"),
                ]

                for col_name, col_type in new_columns:
                    if col_name not in branch_column_names:
                        logger.info(f"Adding {col_name} to branch table...")
                        conn.execute(
                            text(
                                f"ALTER TABLE branch ADD COLUMN {col_name} {col_type} NULL"
                            )
                        )
                        conn.commit()
                        logger.info(f"✅ Successfully added {col_name}")

            # ---------------------------------------------------------
            # 2. Permissions Table
            # ---------------------------------------------------------
            if "parent_permission_interactions" not in existing_tables:
                logger.info("Creating parent_permission_interactions table...")
                # Note: For SQLite compatibility, we avoid ENUM in CREATE TABLE if simplified
                enum_def = (
                    "ENUM('requested', 'cancelled')" if supports_enum else "VARCHAR(20)"
                )
                # MySQL uses AUTO_INCREMENT, SQLite uses AUTOINCREMENT (or implied by INTEGER PRIMARY KEY)

                if is_mysql:
                    conn.execute(
                        text(f"""
                        CREATE TABLE parent_permission_interactions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            parent_id INT NOT NULL,
                            student_id INT NOT NULL,
                            learning_id INT NOT NULL,
                            interaction_date DATE NOT NULL,
                            interaction_type {enum_def} NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            INDEX ix_permission_parent_date (parent_id, interaction_date),
                            INDEX ix_permission_student_learning (student_id, learning_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    # SQLite fallback (simplified)
                    conn.execute(
                        text("""
                        CREATE TABLE parent_permission_interactions (
                            id INTEGER PRIMARY KEY,
                            parent_id INTEGER NOT NULL,
                            student_id INTEGER NOT NULL,
                            learning_id INTEGER NOT NULL,
                            interaction_date DATE NOT NULL,
                            interaction_type VARCHAR(20) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created parent_permission_interactions table")

            # ---------------------------------------------------------
            # 3. Ads System Tables
            # ---------------------------------------------------------
            if "ads" not in existing_tables:
                logger.info("Creating ads table...")
                json_type = "JSON" if is_mysql and supports_json else "TEXT"
                long_text = "TEXT"

                # Using conditional SQL generation for basic compatibility
                if is_mysql:
                    conn.execute(
                        text(f"""
                        CREATE TABLE ads (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            title VARCHAR(255) NOT NULL,
                            subtitle VARCHAR(255),
                            description {long_text},
                            image_url VARCHAR(500) NOT NULL,
                            image_path VARCHAR(500),
                            ad_type VARCHAR(50) NOT NULL DEFAULT 'general',
                            action_type VARCHAR(50),
                            action_data {json_type},
                            button_text VARCHAR(100),
                            button_color VARCHAR(20) DEFAULT '#1976D2',
                            target_audience VARCHAR(50) DEFAULT 'all',
                            start_date DATETIME,
                            end_date DATETIME,
                            is_active BOOLEAN DEFAULT 1,
                            display_order INT DEFAULT 0,
                            click_count INT DEFAULT 0,
                            view_count INT DEFAULT 0,
                            created_by INT,
                            academic_id INT,
                            branch_id INT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_ads_active (is_active, start_date, end_date),
                            INDEX idx_ads_order (display_order),
                            INDEX idx_ads_academic (academic_id),
                            INDEX idx_ads_branch (branch_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    # SQLite schema
                    conn.execute(
                        text("""
                        CREATE TABLE ads (
                            id INTEGER PRIMARY KEY,
                            title VARCHAR(255) NOT NULL,
                            subtitle VARCHAR(255),
                            description TEXT,
                            image_url VARCHAR(500) NOT NULL,
                            image_path VARCHAR(500),
                            ad_type VARCHAR(50) NOT NULL DEFAULT 'general',
                            action_type VARCHAR(50),
                            action_data TEXT,
                            button_text VARCHAR(100),
                            button_color VARCHAR(20) DEFAULT '#1976D2',
                            target_audience VARCHAR(50) DEFAULT 'all',
                            start_date DATETIME,
                            end_date DATETIME,
                            is_active BOOLEAN DEFAULT 1,
                            display_order INTEGER DEFAULT 0,
                            click_count INTEGER DEFAULT 0,
                            view_count INTEGER DEFAULT 0,
                            created_by INTEGER,
                            academic_id INTEGER,
                            branch_id INTEGER,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created ads table")

            if "ad_clicks" not in existing_tables:
                logger.info("Creating ad_clicks table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE ad_clicks (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            ad_id INT NOT NULL,
                            user_id INT,
                            user_type VARCHAR(50),
                            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            device_info VARCHAR(255),
                            INDEX idx_clicks_ad (ad_id),
                            INDEX idx_clicks_user (user_id),
                            FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE ad_clicks (
                            id INTEGER PRIMARY KEY,
                            ad_id INTEGER NOT NULL,
                            user_id INTEGER,
                            user_type VARCHAR(50),
                            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            device_info VARCHAR(255),
                            FOREIGN KEY (ad_id) REFERENCES ads(id) ON DELETE CASCADE
                        )
                    """)
                    )
                logger.info("✅ Created ad_clicks table")

            # ---------------------------------------------------------
            # 4. Device Tokens Table (for Notifications)
            # ---------------------------------------------------------
            if "device_tokens" not in existing_tables:
                logger.info("Creating device_tokens table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE device_tokens (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            user_type VARCHAR(50) NOT NULL,
                            device_token VARCHAR(500) NOT NULL,
                            device_type VARCHAR(50),
                            device_name VARCHAR(255),
                            app_version VARCHAR(50),
                            is_active BOOLEAN DEFAULT 1,
                            notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            attendance_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            leave_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            message_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            announcement_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            market_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            other_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            last_used_at TIMESTAMP NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE KEY unique_user_device (user_id, user_type, device_token),
                            INDEX idx_tokens_user (user_id, user_type),
                            INDEX idx_tokens_active (is_active, last_used_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE device_tokens (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            user_type VARCHAR(50) NOT NULL,
                            device_token VARCHAR(500) NOT NULL,
                            device_type VARCHAR(50),
                            device_name VARCHAR(255),
                            app_version VARCHAR(50),
                            is_active BOOLEAN DEFAULT 1,
                            notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            attendance_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            leave_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            message_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            announcement_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            market_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            other_notifications_enabled BOOLEAN NOT NULL DEFAULT 1,
                            last_used_at TIMESTAMP,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP,
                            CONSTRAINT unique_user_device UNIQUE (user_id, user_type, device_token)
                        )
                    """)
                    )
                logger.info("✅ Created device_tokens table")

            # ---------------------------------------------------------
            # 5. Notifications Table
            # ---------------------------------------------------------
            if "notifications" not in existing_tables:
                logger.info("Creating notifications table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE notifications (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT,
                            user_type VARCHAR(50),
                            title VARCHAR(255),
                            body TEXT,
                            data TEXT,
                            is_read TINYINT(1) DEFAULT 0,
                            is_deletable TINYINT(1) DEFAULT 1,
                            redirect_route VARCHAR(100),
                            redirect_args TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_notif_user (user_id, user_type),
                            INDEX idx_notif_read (is_read)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE notifications (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER,
                            user_type VARCHAR(50),
                            title VARCHAR(255),
                            body TEXT,
                            data TEXT,
                            is_read BOOLEAN DEFAULT 0,
                            is_deletable BOOLEAN DEFAULT 1,
                            redirect_route VARCHAR(100),
                            redirect_args TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created notifications table")

            # ---------------------------------------------------------
            # 4.1. Hot Events Table (admin-pushed home banner)
            # ---------------------------------------------------------
            if "hot_events" not in existing_tables:
                logger.info("Creating hot_events table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE hot_events (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            title VARCHAR(255),
                            message TEXT NOT NULL,
                            start_at DATETIME NULL,
                            end_at DATETIME NOT NULL,
                            audience VARCHAR(100) NOT NULL DEFAULT 'all',
                            event_type VARCHAR(50) NOT NULL DEFAULT 'banner',
                            frequency VARCHAR(50) NOT NULL DEFAULT 'always',
                            interval_minutes INT DEFAULT NULL,
                            max_impressions INT DEFAULT NULL,
                            link_url VARCHAR(500),
                            status_text VARCHAR(255) DEFAULT NULL,
                            is_active TINYINT(1) NOT NULL DEFAULT 1,
                            created_by INT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_hot_events_active (is_active, start_at, end_at),
                            INDEX idx_hot_events_audience (audience),
                            INDEX idx_hot_events_type (event_type)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE hot_events (
                            id INTEGER PRIMARY KEY,
                            title VARCHAR(255),
                            message TEXT NOT NULL,
                            start_at DATETIME,
                            end_at DATETIME NOT NULL,
                            audience VARCHAR(100) NOT NULL DEFAULT 'all',
                            event_type VARCHAR(50) NOT NULL DEFAULT 'banner',
                            frequency VARCHAR(50) NOT NULL DEFAULT 'always',
                            interval_minutes INT DEFAULT NULL,
                            max_impressions INT DEFAULT NULL,
                            link_url VARCHAR(500),
                            status_text VARCHAR(255),
                            is_active BOOLEAN NOT NULL DEFAULT 1,
                            created_by INTEGER,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created hot_events table")

            # Check for missing columns in hot_events
            if "hot_events" in existing_tables:
                try:
                    columns = inspector.get_columns("hot_events")
                    column_names = [col["name"] for col in columns]

                    if "event_type" not in column_names:
                        logger.info("Adding event_type column to hot_events table...")
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'banner'"
                                )
                            )
                            conn.execute(
                                text(
                                    "CREATE INDEX idx_hot_events_type ON hot_events(event_type)"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN event_type VARCHAR(50) NOT NULL DEFAULT 'banner'"
                                )
                            )
                        logger.info("✅ Added event_type to hot_events")

                    if "frequency" not in column_names:
                        logger.info("Adding frequency column to hot_events table...")
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN frequency VARCHAR(50) NOT NULL DEFAULT 'always'"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN frequency VARCHAR(50) NOT NULL DEFAULT 'always'"
                                )
                            )
                        logger.info("✅ Added frequency to hot_events")

                    if "interval_minutes" not in column_names:
                        logger.info(
                            "Adding interval_minutes column to hot_events table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN interval_minutes INT DEFAULT NULL"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN interval_minutes INTEGER DEFAULT NULL"
                                )
                            )
                        logger.info("✅ Added interval_minutes to hot_events")

                    if "max_impressions" not in column_names:
                        logger.info(
                            "Adding max_impressions column to hot_events table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN max_impressions INT DEFAULT NULL"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN max_impressions INTEGER DEFAULT NULL"
                                )
                            )
                        logger.info("✅ Added max_impressions to hot_events")

                    if "status_text" not in column_names:
                        logger.info("Adding status_text column to hot_events table...")
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN status_text VARCHAR(100) DEFAULT NULL"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE hot_events ADD COLUMN status_text VARCHAR(100) DEFAULT NULL"
                                )
                            )
                        logger.info("✅ Added status_text to hot_events")

                except Exception as e:
                    logger.warning(f"Could not check/add columns to hot_events: {e}")

            # 4.2. Hot Event Impressions Table
            # ---------------------------------------------------------
            if "hot_event_impressions" not in existing_tables:
                logger.info("Creating hot_event_impressions table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE hot_event_impressions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            hot_event_id INT NOT NULL,
                            user_id INT,
                            impression_count INT DEFAULT 0,
                            last_viewed_at DATETIME,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            FOREIGN KEY (hot_event_id) REFERENCES hot_events(id) ON DELETE CASCADE,
                            UNIQUE KEY unique_user_event (user_id, hot_event_id),
                            INDEX idx_impressions_user (user_id),
                            INDEX idx_impressions_event (hot_event_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE hot_event_impressions (
                            id INTEGER PRIMARY KEY,
                            hot_event_id INTEGER NOT NULL,
                            user_id INTEGER,
                            impression_count INTEGER DEFAULT 0,
                            last_viewed_at DATETIME,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP,
                            FOREIGN KEY (hot_event_id) REFERENCES hot_events(id) ON DELETE CASCADE,
                            UNIQUE (user_id, hot_event_id)
                        )
                    """)
                    )
                logger.info("✅ Created hot_event_impressions table")

            # 4.3. Message Groups Table
            # ---------------------------------------------------------
            if "message_groups" not in existing_tables:
                logger.info("Creating message_groups table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE message_groups (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            type ENUM('class', 'custom') NOT NULL DEFAULT 'class',
                            academic_year_id INT,
                            grade_id INT,
                            description TEXT,
                            created_by INT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_groups_type (type),
                            INDEX idx_groups_academic_year (academic_year_id),
                            INDEX idx_groups_grade (grade_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE message_groups (
                            id INTEGER PRIMARY KEY,
                            name VARCHAR(255) NOT NULL,
                            type VARCHAR(20) NOT NULL DEFAULT 'class',
                            academic_year_id INTEGER,
                            grade_id INTEGER,
                            description TEXT,
                            created_by INTEGER NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created message_groups table")

            # 4.4. Message Group Members Table
            # ---------------------------------------------------------
            if "message_group_members" not in existing_tables:
                logger.info("Creating message_group_members table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE message_group_members (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            group_id INT NOT NULL,
                            user_id INT NOT NULL,
                            role ENUM('admin', 'member') NOT NULL DEFAULT 'member',
                            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE,
                            UNIQUE KEY unique_group_user (group_id, user_id),
                            INDEX idx_members_group (group_id),
                            INDEX idx_members_user (user_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE message_group_members (
                            id INTEGER PRIMARY KEY,
                            group_id INTEGER NOT NULL,
                            user_id INTEGER NOT NULL,
                            role VARCHAR(20) NOT NULL DEFAULT 'member',
                            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE,
                            UNIQUE (group_id, user_id)
                        )
                    """)
                    )
                logger.info("✅ Created message_group_members table")

            # 4.5. Messages Table
            # ---------------------------------------------------------
            if "messages" not in existing_tables:
                logger.info("Creating messages table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE messages (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            group_id INT NOT NULL,
                            sender_id INT NOT NULL,
                            content TEXT NOT NULL,
                            message_type ENUM('text', 'announcement', 'file') NOT NULL DEFAULT 'text',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            read_by TEXT,
                            FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE,
                            INDEX idx_messages_group (group_id),
                            INDEX idx_messages_sender (sender_id),
                            INDEX idx_messages_created (created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE messages (
                            id INTEGER PRIMARY KEY,
                            group_id INTEGER NOT NULL,
                            sender_id INTEGER NOT NULL,
                            content TEXT NOT NULL,
                            message_type VARCHAR(20) NOT NULL DEFAULT 'text',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            read_by TEXT,
                            FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE
                        )
                    """)
                    )
                logger.info("✅ Created messages table")

            # 5.1. Attendance System Settings Table
            # ---------------------------------------------------------
            if "attendance_system_settings" not in existing_tables:
                logger.info("Creating attendance_system_settings table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_system_settings (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            require_location TINYINT(1) DEFAULT 1,
                            block_mock_location TINYINT(1) DEFAULT 1,
                            block_developer_options TINYINT(1) DEFAULT 0,
                            allowed_ip_ranges TEXT,
                            allow_early_clock_in_mins INT DEFAULT NULL COMMENT 'NULL = allow all early clock-ins',
                            allow_late_clock_out_mins INT DEFAULT NULL COMMENT 'NULL = allow all late clock-outs',
                            session_transition_wait_mins INT NOT NULL DEFAULT 10 COMMENT 'Wait after checkout before another session check-in',
                            late_grace_minutes INT NOT NULL DEFAULT 15 COMMENT 'Grace period before marking as late',
                            updated_at DATE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    # SQLite fallback
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_system_settings (
                            id INTEGER PRIMARY KEY,
                            require_location BOOLEAN DEFAULT 1,
                            block_mock_location BOOLEAN DEFAULT 1,
                            block_developer_options BOOLEAN DEFAULT 0,
                            allowed_ip_ranges TEXT,
                            allow_early_clock_in_mins INTEGER DEFAULT NULL, -- NULL = allow all early clock-ins
                            allow_late_clock_out_mins INTEGER DEFAULT NULL, -- NULL = allow all late clock-outs
                            session_transition_wait_mins INTEGER NOT NULL DEFAULT 10,
                            late_grace_minutes INTEGER NOT NULL DEFAULT 15, -- Grace period before marking as late
                            updated_at DATE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created attendance_system_settings table")

                # Create a default record
                conn.execute(
                    text("""
                    INSERT IGNORE INTO attendance_system_settings
                    (require_location, block_mock_location, block_developer_options)
                    VALUES (1, 1, 0)
                """)
                )
                logger.info("✅ Created default attendance system settings")

            # 5.2. Fix existing attendance_system_settings tables (ensure NULL defaults)
            # ---------------------------------------------------------
            if "attendance_system_settings" in existing_tables:
                logger.info(
                    "Ensuring attendance_system_settings table has correct NULL defaults..."
                )

                # Check and fix column defaults
                try:
                    # Add late_grace_minutes column if it doesn't exist
                    try:
                        # Try to add the column (will fail silently if it already exists)
                        if is_mysql:
                            conn.execute(
                                text("""
                                ALTER TABLE attendance_system_settings
                                ADD COLUMN late_grace_minutes INT NOT NULL DEFAULT 15 COMMENT 'Grace period before marking as late'
                            """)
                            )
                        else:
                            conn.execute(
                                text("""
                                ALTER TABLE attendance_system_settings
                                ADD COLUMN late_grace_minutes INTEGER NOT NULL DEFAULT 15
                            """)
                            )
                        logger.info(
                            "✅ Added late_grace_minutes column to attendance_system_settings"
                        )
                    except Exception as e:
                        # Column might already exist, that's fine
                        logger.debug(
                            f"late_grace_minutes column may already exist: {e}"
                        )

                    try:
                        if is_mysql:
                            conn.execute(
                                text("""
                                ALTER TABLE attendance_system_settings
                                ADD COLUMN per_session_early_clock_in_mins JSON NULL
                            """)
                            )
                        else:
                            conn.execute(
                                text("""
                                ALTER TABLE attendance_system_settings
                                ADD COLUMN per_session_early_clock_in_mins TEXT NULL
                            """)
                            )
                        logger.info(
                            "✅ Added per_session_early_clock_in_mins to attendance_system_settings"
                        )
                    except Exception as e:
                        logger.debug(
                            f"per_session_early_clock_in_mins column may already exist: {e}"
                        )

                    # Remove default values from time restriction columns to allow NULL = unlimited
                    if is_mysql:
                        # Remove legacy rooted/jailbroken policy column from older schemas.
                        try:
                            conn.execute(
                                text("""
                                ALTER TABLE attendance_system_settings
                                DROP COLUMN block_rooted_devices
                            """)
                            )
                            logger.info(
                                "✅ Dropped legacy block_rooted_devices column from attendance_system_settings"
                            )
                        except Exception as e:
                            logger.debug(
                                f"block_rooted_devices column may already be removed: {e}"
                            )

                        conn.execute(
                            text("""
                            ALTER TABLE attendance_system_settings
                            MODIFY COLUMN allow_early_clock_in_mins INT DEFAULT NULL
                        """)
                        )

                        conn.execute(
                            text("""
                            ALTER TABLE attendance_system_settings
                            MODIFY COLUMN allow_late_clock_out_mins INT DEFAULT NULL
                        """)
                        )
                    # SQLite doesn't have ALTER COLUMN MODIFY in the same way, but since we're creating with NULL defaults, existing tables should be fine

                    # Set existing default values to NULL (unlimited)
                    conn.execute(
                        text("""
                        UPDATE attendance_system_settings
                        SET allow_early_clock_in_mins = NULL
                        WHERE allow_early_clock_in_mins = 15
                    """)
                    )

                    conn.execute(
                        text("""
                        UPDATE attendance_system_settings
                        SET allow_late_clock_out_mins = NULL
                        WHERE allow_late_clock_out_mins = 60
                    """)
                    )

                    logger.info("✅ Fixed attendance_system_settings table defaults")

                except Exception as e:
                    logger.warning(
                        f"Could not fix attendance_system_settings defaults (may already be correct): {e}"
                    )

            # ---------------------------------------------------------
            # 6. Additional Table Creations
            # ---------------------------------------------------------

            # Create attendance_records table
            if "attendance_records" not in existing_tables:
                logger.info("Creating attendance_records table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_records (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            check_in_time DATETIME,
                            check_out_time DATETIME,
                            check_in_latitude FLOAT(10,8),
                            check_in_longitude FLOAT(11,8),
                            check_out_latitude FLOAT(10,8),
                            check_out_longitude FLOAT(11,8),
                            check_in_location_id INT,
                            check_out_location_id INT,
                            is_mock_location TINYINT(1) DEFAULT 0,
                            device_info TEXT,
                            attendance_date DATE NOT NULL,
                            session_index INT DEFAULT NULL,
                            schedule_id INT DEFAULT NULL,
                            scheduled_start VARCHAR(8),
                            scheduled_end VARCHAR(8),
                            snapshot_late_grace_minutes INT DEFAULT NULL,
                            snapshot_allow_early_leave_mins INT DEFAULT NULL,
                            work_hours FLOAT,
                            status ENUM('present','absent','half_day','late') DEFAULT 'present',
                            notes TEXT,
                            late_reason TEXT,
                            leave_early_reason TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_attendance_user (user_id),
                            INDEX idx_attendance_date (attendance_date),
                            INDEX idx_attendance_status (status)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_records (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            check_in_time DATETIME,
                            check_out_time DATETIME,
                            check_in_latitude REAL,
                            check_in_longitude REAL,
                            check_out_latitude REAL,
                            check_out_longitude REAL,
                            check_in_location_id INTEGER,
                            check_out_location_id INTEGER,
                            is_mock_location BOOLEAN DEFAULT 0,
                            device_info TEXT,
                            attendance_date DATE NOT NULL,
                            session_index INTEGER,
                            schedule_id INTEGER,
                            scheduled_start VARCHAR(8),
                            scheduled_end VARCHAR(8),
                            snapshot_late_grace_minutes INTEGER,
                            snapshot_allow_early_leave_mins INTEGER,
                            work_hours REAL,
                            status VARCHAR(20) DEFAULT 'present',
                            notes TEXT,
                            late_reason TEXT,
                            leave_early_reason TEXT,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created attendance_records table")

            # Check and add attendance_records columns used by newer attendance flows
            if "attendance_records" in existing_tables:
                logger.info("Checking attendance_records table for required columns...")

                try:
                    columns = inspector.get_columns("attendance_records")
                    column_names = [col["name"] for col in columns]

                    def add_attendance_record_column(
                        column_name: str,
                        mysql_definition: str,
                        sqlite_definition: str,
                    ) -> None:
                        nonlocal column_names
                        if column_name in column_names:
                            return
                        logger.info(
                            f"Adding {column_name} column to attendance_records table..."
                        )
                        definition = mysql_definition if is_mysql else sqlite_definition
                        conn.execute(
                            text(
                                f"ALTER TABLE attendance_records ADD COLUMN {column_name} {definition}"
                            )
                        )
                        column_names.append(column_name)
                        logger.info(
                            f"✅ Added {column_name} column to attendance_records"
                        )

                    attendance_column_definitions = [
                        ("session_index", "INT DEFAULT NULL", "INTEGER"),
                        ("schedule_id", "INT DEFAULT NULL", "INTEGER"),
                        ("scheduled_start", "VARCHAR(8)", "VARCHAR(8)"),
                        ("scheduled_end", "VARCHAR(8)", "VARCHAR(8)"),
                        (
                            "snapshot_late_grace_minutes",
                            "INT DEFAULT NULL",
                            "INTEGER",
                        ),
                        (
                            "snapshot_allow_early_leave_mins",
                            "INT DEFAULT NULL",
                            "INTEGER",
                        ),
                    ]
                    for column_name, mysql_def, sqlite_def in attendance_column_definitions:
                        add_attendance_record_column(column_name, mysql_def, sqlite_def)

                    if is_mysql:
                        try:
                            indexes = {
                                idx["name"]
                                for idx in inspector.get_indexes("attendance_records")
                            }
                            if (
                                "idx_attendance_records_session_index" not in indexes
                                and "session_index" in column_names
                            ):
                                conn.execute(
                                    text(
                                        "CREATE INDEX idx_attendance_records_session_index ON attendance_records (session_index)"
                                    )
                                )
                                logger.info(
                                    "✅ Added idx_attendance_records_session_index"
                                )
                            if (
                                "idx_attendance_records_schedule_id" not in indexes
                                and "schedule_id" in column_names
                            ):
                                conn.execute(
                                    text(
                                        "CREATE INDEX idx_attendance_records_schedule_id ON attendance_records (schedule_id)"
                                    )
                                )
                                logger.info(
                                    "✅ Added idx_attendance_records_schedule_id"
                                )
                        except Exception as index_err:
                            logger.warning(
                                f"Could not ensure attendance_records snapshot indexes: {index_err}"
                            )

                    # Add late_reason column if it doesn't exist
                    if "late_reason" not in column_names:
                        logger.info(
                            "Adding late_reason column to attendance_records table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN late_reason TEXT"
                                )
                            )
                        else:
                            # SQLite syntax
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN late_reason TEXT"
                                )
                            )
                        logger.info("✅ Added late_reason column to attendance_records")

                    # Add leave_early_reason column if it doesn't exist
                    if "leave_early_reason" not in column_names:
                        logger.info(
                            "Adding leave_early_reason column to attendance_records table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN leave_early_reason TEXT"
                                )
                            )
                        else:
                            # SQLite syntax
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN leave_early_reason TEXT"
                                )
                            )
                        logger.info(
                            "✅ Added leave_early_reason column to attendance_records"
                        )

                    # Add check_in_branch_id column if it doesn't exist
                    if "check_in_branch_id" not in column_names:
                        logger.info(
                            "Adding check_in_branch_id column to attendance_records table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN check_in_branch_id INT DEFAULT NULL COMMENT 'Branch where user scanned QR at check-in'"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN check_in_branch_id INTEGER DEFAULT NULL"
                                )
                            )
                        logger.info(
                            "✅ Added check_in_branch_id column to attendance_records"
                        )

                    # Add check_out_branch_id column if it doesn't exist
                    if "check_out_branch_id" not in column_names:
                        logger.info(
                            "Adding check_out_branch_id column to attendance_records table..."
                        )
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN check_out_branch_id INT DEFAULT NULL COMMENT 'Branch where user scanned QR at check-out'"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE attendance_records ADD COLUMN check_out_branch_id INTEGER DEFAULT NULL"
                                )
                            )
                        logger.info(
                            "✅ Added check_out_branch_id column to attendance_records"
                        )

                    # Ensure status ENUM includes 'early_leave' (for early check-out)
                    if is_mysql:
                        try:
                            logger.info(
                                "Ensuring attendance_records.status supports 'early_leave'..."
                            )
                            status_column = next(
                                (col for col in columns if col["name"] == "status"),
                                None,
                            )
                            if status_column is not None:
                                col_type_str = str(status_column["type"]).lower()
                                if (
                                    "enum" in col_type_str
                                    and "early_leave" not in col_type_str
                                ):
                                    logger.info(
                                        "Updating attendance_records.status ENUM to include 'early_leave'..."
                                    )
                                    conn.execute(
                                        text(
                                            """
                                            ALTER TABLE attendance_records
                                            MODIFY COLUMN status ENUM(
                                                'present',
                                                'absent',
                                                'half_day',
                                                'late',
                                                'early_leave'
                                            ) DEFAULT 'present'
                                            """
                                        )
                                    )
                                    logger.info(
                                        "✅ Updated attendance_records.status ENUM with 'early_leave'"
                                    )
                        except Exception as status_err:
                            logger.warning(
                                f"Could not update attendance_records.status ENUM: {status_err}"
                            )

                except Exception as e:
                    logger.warning(
                        f"Could not check/add reason columns to attendance_records: {e}"
                    )
                    # Continue with startup - this is not critical

            # Create attendance_schedules table
            if "attendance_schedules" not in existing_tables:
                logger.info("Creating attendance_schedules table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_schedules (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            type VARCHAR(50) DEFAULT 'standard',
                            branch_id INT,
                            department_id INT,
                            user_id INT,
                            weekly_config JSON NOT NULL,
                            is_active INT DEFAULT 1,
                            effective_date DATE NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_schedule_branch (branch_id),
                            INDEX idx_schedule_dept (department_id),
                            INDEX idx_schedule_user (user_id),
                            INDEX idx_schedule_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_schedules (
                            id INTEGER PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            type VARCHAR(50) DEFAULT 'standard',
                            branch_id INTEGER,
                            department_id INTEGER,
                            user_id INTEGER,
                            weekly_config TEXT NOT NULL,
                            is_active INTEGER DEFAULT 1,
                            effective_date DATE NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created attendance_schedules table")

            # Create attendance_user_assignments table
            if "attendance_user_assignments" not in existing_tables:
                logger.info("Creating attendance_user_assignments table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_user_assignments (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            schedule_id INT NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            assigned_by INT,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_assignment_user (user_id),
                            INDEX idx_assignment_schedule (schedule_id),
                            UNIQUE KEY unique_user_schedule (user_id, schedule_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_user_assignments (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            schedule_id INTEGER NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            assigned_by INTEGER,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, schedule_id)
                        )
                    """)
                    )
                logger.info("✅ Created attendance_user_assignments table")

            # Create attendance__allowed_branches table
            if "attendance__allowed_branches" not in existing_tables:
                logger.info("Creating attendance__allowed_branches table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance__allowed_branches (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            branch_id INT NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE KEY user_branch_unique (user_id, branch_id),
                            INDEX idx_allowed_user (user_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance__allowed_branches (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            branch_id INTEGER NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(user_id, branch_id)
                        )
                    """)
                    )
                logger.info("✅ Created attendance__allowed_branches table")

            # Create attendance_schedule_exceptions table
            if "attendance_schedule_exceptions" not in existing_tables:
                logger.info("Creating attendance_schedule_exceptions table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_schedule_exceptions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            exception_date DATE NOT NULL,
                            end_date DATE NULL,
                            user_id INT NULL,
                            branch_id INT NULL,
                            department_id INT NULL,
                            is_foreigner INT NULL,
                            recurrence_type VARCHAR(30) NULL,
                            exception_type VARCHAR(50) NOT NULL DEFAULT 'sessions_override',
                            sessions JSON NULL,
                            reason VARCHAR(500) NULL,
                            created_by INT NULL,
                            is_active INT NOT NULL DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_exc_date (exception_date),
                            INDEX idx_exc_end_date (end_date),
                            INDEX idx_exc_user (user_id),
                            INDEX idx_exc_branch (branch_id),
                            INDEX idx_exc_dept (department_id),
                            INDEX idx_exc_foreigner (is_foreigner),
                            INDEX idx_exc_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE attendance_schedule_exceptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            exception_date DATE NOT NULL,
                            end_date DATE NULL,
                            user_id INTEGER NULL,
                            branch_id INTEGER NULL,
                            department_id INTEGER NULL,
                            is_foreigner INTEGER NULL,
                            recurrence_type VARCHAR(30) NULL,
                            exception_type VARCHAR(50) NOT NULL DEFAULT 'sessions_override',
                            sessions TEXT NULL,
                            reason VARCHAR(500) NULL,
                            created_by INTEGER NULL,
                            is_active INTEGER NOT NULL DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created attendance_schedule_exceptions table")

            # Create telegram_attendance_settings table
            if "telegram_attendance_settings" not in existing_tables:
                logger.info("Creating telegram_attendance_settings table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_attendance_settings (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            bot_token VARCHAR(500) NULL COMMENT 'Telegram bot token from BotFather',
                            chat_id VARCHAR(100) NULL COMMENT 'Telegram chat ID (group or private)',
                            leave_routing_mode VARCHAR(20) NULL DEFAULT 'combined' COMMENT 'combined or separate leave destination',
                            leave_chat_id VARCHAR(100) NULL COMMENT 'Separate Telegram chat ID for leave notifications',
                            branch_routing_mode VARCHAR(20) NULL DEFAULT 'all' COMMENT 'all or by_branch workplace routing',
                            enabled BOOLEAN DEFAULT FALSE COMMENT 'Enable/disable Telegram notifications',
                            notify_leave_requests BOOLEAN DEFAULT FALSE,
                            notify_leave_decisions BOOLEAN DEFAULT FALSE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_telegram_settings_id (id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_attendance_settings (
                            id INTEGER PRIMARY KEY,
                            bot_token VARCHAR(500) NULL,
                            chat_id VARCHAR(100) NULL,
                            leave_routing_mode VARCHAR(20) NULL DEFAULT 'combined',
                            leave_chat_id VARCHAR(100) NULL,
                            branch_routing_mode VARCHAR(20) NULL DEFAULT 'all',
                            enabled BOOLEAN DEFAULT FALSE,
                            notify_leave_requests BOOLEAN DEFAULT FALSE,
                            notify_leave_decisions BOOLEAN DEFAULT FALSE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                conn.commit()
                logger.info("✅ Created telegram_attendance_settings table")
                # Now insert default row (will run immediately after create)
                existing_tables = inspector.get_table_names()  # Refresh table list

            # Older installations keep working while gaining the optional
            # branch-routing mode during normal API startup.
            if "telegram_attendance_settings" in existing_tables:
                telegram_settings_columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "telegram_attendance_settings"
                    )
                }
                if "branch_routing_mode" not in telegram_settings_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE telegram_attendance_settings "
                            "ADD COLUMN branch_routing_mode VARCHAR(20) "
                            "NULL DEFAULT 'all'"
                        )
                    )
                    conn.commit()
                    logger.info(
                        "✅ Added branch_routing_mode to Telegram settings"
                    )

            if "telegram_branch_notification_routes" not in existing_tables:
                logger.info("Creating Telegram branch notification routes...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_branch_notification_routes (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            settings_id INT NOT NULL,
                            branch_id INT NOT NULL,
                            attendance_chat_id VARCHAR(100) NULL,
                            leave_chat_id VARCHAR(100) NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            UNIQUE KEY uq_telegram_branch_notification_route (settings_id, branch_id),
                            INDEX idx_telegram_branch_route_settings (settings_id),
                            INDEX idx_telegram_branch_route_branch (branch_id),
                            CONSTRAINT fk_telegram_branch_route_settings
                                FOREIGN KEY (settings_id)
                                REFERENCES telegram_attendance_settings(id)
                                ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_branch_notification_routes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            settings_id INTEGER NOT NULL,
                            branch_id INTEGER NOT NULL,
                            attendance_chat_id VARCHAR(100) NULL,
                            leave_chat_id VARCHAR(100) NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(settings_id, branch_id),
                            FOREIGN KEY(settings_id)
                                REFERENCES telegram_attendance_settings(id)
                                ON DELETE CASCADE
                        )
                    """)
                    )
                    conn.execute(
                        text(
                            "CREATE INDEX IF NOT EXISTS "
                            "idx_telegram_branch_route_branch ON "
                            "telegram_branch_notification_routes(branch_id)"
                        )
                    )
                conn.commit()
                logger.info("✅ Created Telegram branch notification routes")
                existing_tables = inspector.get_table_names()
            
            # Ensure default bot token exists (even if table was created earlier)
            if "telegram_attendance_settings" in existing_tables:
                result = conn.execute(text("SELECT COUNT(*) FROM telegram_attendance_settings"))
                row_count = result.scalar()
                if row_count == 0:
                    logger.info("Inserting default bot token into telegram_attendance_settings...")
                    if is_mysql:
                        conn.execute(
                            text("""
                            INSERT INTO telegram_attendance_settings (id, bot_token, chat_id, enabled, created_at, updated_at)
                            VALUES (1, '8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw', NULL, FALSE, NOW(), NOW())
                        """)
                        )
                    else:
                        conn.execute(
                            text("""
                            INSERT OR REPLACE INTO telegram_attendance_settings (id, bot_token, chat_id, enabled, created_at, updated_at)
                            VALUES (1, '8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw', NULL, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """)
                        )
                    conn.commit()
                    logger.info("✅ Inserted default bot token: 8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw")
                    logger.info("🤖 Default Bot: @PAMAISNotify_Bot")
                else:
                    logger.info("✓ telegram_attendance_settings table already has data")

            # Create telegram_tracked_chats table
            if "telegram_tracked_chats" not in existing_tables:
                logger.info("Creating telegram_tracked_chats table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_tracked_chats (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            chat_id VARCHAR(100) NOT NULL UNIQUE COMMENT 'Telegram chat ID',
                            chat_title VARCHAR(255) NOT NULL COMMENT 'Group/channel name',
                            chat_type VARCHAR(50) NOT NULL COMMENT 'private, group, supergroup, channel',
                            bot_role VARCHAR(50) DEFAULT 'pending' COMMENT 'pending, notification_only, general',
                            member_verification_enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Require new members to verify before chatting',
                            is_active BOOLEAN DEFAULT TRUE COMMENT 'Bot still in chat',
                            added_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT 'When bot was added',
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_chat_id (chat_id),
                            INDEX idx_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE telegram_tracked_chats (
                            id INTEGER PRIMARY KEY,
                            chat_id VARCHAR(100) NOT NULL UNIQUE,
                            chat_title VARCHAR(255) NOT NULL,
                            chat_type VARCHAR(50) NOT NULL,
                            bot_role VARCHAR(50) DEFAULT 'pending',
                            member_verification_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                            is_active BOOLEAN DEFAULT TRUE,
                            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created telegram_tracked_chats table")

            if "telegram_tracked_chats" in existing_tables:
                try:
                    columns = inspector.get_columns("telegram_tracked_chats")
                    column_names = [col["name"] for col in columns]
                    if "bot_role" not in column_names:
                        logger.info("Adding bot_role column to telegram_tracked_chats table...")
                        if is_mysql:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN bot_role VARCHAR(50) DEFAULT 'pending' COMMENT 'pending, notification_only, general'"))
                        else:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN bot_role VARCHAR(50) DEFAULT 'pending'"))
                        logger.info("✅ Added bot_role column to telegram_tracked_chats")
                    if "bot_token" not in column_names:
                        logger.info("Adding bot_token column to telegram_tracked_chats table...")
                        if is_mysql:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN bot_token VARCHAR(255) NULL COMMENT 'Telegram bot token that owns this chat'"))
                        else:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN bot_token VARCHAR(255) NULL"))
                        logger.info("✅ Added bot_token column to telegram_tracked_chats")
                    if "member_verification_enabled" not in column_names:
                        logger.info("Adding member verification setting to telegram_tracked_chats...")
                        if is_mysql:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN member_verification_enabled BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Require new members to verify before chatting'"))
                        else:
                            conn.execute(text("ALTER TABLE telegram_tracked_chats ADD COLUMN member_verification_enabled BOOLEAN NOT NULL DEFAULT FALSE"))
                        logger.info("✅ Added member_verification_enabled to telegram_tracked_chats")
                except Exception as e:
                    logger.warning(f"Could not check/add columns to telegram_tracked_chats: {e}")

            # Cross-worker idempotency for Telegram webhook retries and the
            # overlapping message/chat_member forms of membership updates.
            existing_tables = inspector.get_table_names()
            if "telegram_webhook_events" not in existing_tables:
                logger.info("Creating telegram_webhook_events table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE telegram_webhook_events (
                            event_key VARCHAR(255) PRIMARY KEY,
                            event_type VARCHAR(50) NOT NULL,
                            update_id BIGINT NULL,
                            chat_id VARCHAR(100) NULL,
                            telegram_user_id VARCHAR(100) NULL,
                            claim_token VARCHAR(32) NOT NULL,
                            processed_at DATETIME(6) NOT NULL,
                            INDEX idx_twe_processed_at (processed_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                          COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE telegram_webhook_events (
                            event_key VARCHAR(255) PRIMARY KEY,
                            event_type VARCHAR(50) NOT NULL,
                            update_id BIGINT NULL,
                            chat_id VARCHAR(100) NULL,
                            telegram_user_id VARCHAR(100) NULL,
                            claim_token VARCHAR(32) NOT NULL,
                            processed_at DATETIME NOT NULL
                        )
                    """))
                    conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_twe_processed_at
                        ON telegram_webhook_events(processed_at)
                    """))
                conn.commit()
                logger.info("✅ Created telegram_webhook_events table")

            # Per-General-Group automatic file/link moderation.
            existing_tables = inspector.get_table_names()
            if "telegram_chat_moderation_settings" not in existing_tables:
                logger.info("Creating telegram_chat_moderation_settings table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE telegram_chat_moderation_settings (
                            chat_id VARCHAR(100) PRIMARY KEY,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            file_policy VARCHAR(20) NOT NULL,
                            blocked_extensions TEXT NOT NULL,
                            allowed_extensions TEXT NOT NULL,
                            link_policy VARCHAR(20) NOT NULL,
                            allowed_domains TEXT NOT NULL,
                            exempt_admins BOOLEAN NOT NULL DEFAULT FALSE,
                            send_warning BOOLEAN NOT NULL DEFAULT TRUE,
                            updated_by INT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE telegram_chat_moderation_settings (
                            chat_id VARCHAR(100) PRIMARY KEY,
                            enabled BOOLEAN NOT NULL DEFAULT 1,
                            file_policy VARCHAR(20) NOT NULL,
                            blocked_extensions TEXT NOT NULL,
                            allowed_extensions TEXT NOT NULL,
                            link_policy VARCHAR(20) NOT NULL,
                            allowed_domains TEXT NOT NULL,
                            exempt_admins BOOLEAN NOT NULL DEFAULT 0,
                            send_warning BOOLEAN NOT NULL DEFAULT 1,
                            updated_by INTEGER NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                logger.info("✅ Created telegram_chat_moderation_settings table")

            existing_tables = inspector.get_table_names()
            if "telegram_moderation_events" not in existing_tables:
                logger.info("Creating telegram_moderation_events table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE telegram_moderation_events (
                            event_id VARCHAR(36) PRIMARY KEY,
                            chat_id VARCHAR(100) NOT NULL,
                            message_id VARCHAR(100) NULL,
                            telegram_user_id VARCHAR(100) NULL,
                            username VARCHAR(255) NULL,
                            content_type VARCHAR(50) NOT NULL,
                            file_name VARCHAR(500) NULL,
                            domain VARCHAR(255) NULL,
                            reason VARCHAR(500) NOT NULL,
                            action VARCHAR(50) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_tme_chat_id (chat_id),
                            INDEX idx_tme_created_at (created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE telegram_moderation_events (
                            event_id VARCHAR(36) PRIMARY KEY,
                            chat_id VARCHAR(100) NOT NULL,
                            message_id VARCHAR(100) NULL,
                            telegram_user_id VARCHAR(100) NULL,
                            username VARCHAR(255) NULL,
                            content_type VARCHAR(50) NOT NULL,
                            file_name VARCHAR(500) NULL,
                            domain VARCHAR(255) NULL,
                            reason VARCHAR(500) NOT NULL,
                            action VARCHAR(50) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                logger.info("✅ Created telegram_moderation_events table")

            # Create telegram_bot_auth_codes table
            existing_tables = inspector.get_table_names()
            if "telegram_bot_auth_codes" not in existing_tables:
                logger.info("Creating telegram_bot_auth_codes table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_bot_auth_codes (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            code VARCHAR(6) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            expires_at DATETIME NOT NULL,
                            used_at DATETIME NULL,
                            used_for_chat_id VARCHAR(100) NULL,
                            intended_role VARCHAR(50) NOT NULL DEFAULT 'pending',
                            INDEX idx_tbac_code (code),
                            INDEX idx_tbac_expires_at (expires_at),
                            INDEX idx_tbac_used_at (used_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_bot_auth_codes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            code VARCHAR(6) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            expires_at DATETIME NOT NULL,
                            used_at DATETIME NULL,
                            used_for_chat_id VARCHAR(100) NULL,
                            intended_role VARCHAR(50) NOT NULL DEFAULT 'pending'
                        )
                    """))
                conn.commit()
                logger.info("✅ Created telegram_bot_auth_codes table")

            existing_tables = inspector.get_table_names()
            if "telegram_bot_auth_codes" in existing_tables:
                auth_code_columns = {
                    column["name"]
                    for column in inspector.get_columns("telegram_bot_auth_codes")
                }
                if "intended_role" not in auth_code_columns:
                    conn.execute(text("""
                        ALTER TABLE telegram_bot_auth_codes
                        ADD COLUMN intended_role VARCHAR(50) NOT NULL
                        DEFAULT 'pending'
                    """))
                    conn.commit()
                    logger.info("✅ Added intended_role to Telegram auth codes")

            # Create telegram_group_members table
            if "telegram_group_members" not in existing_tables:
                logger.info("Creating telegram_group_members table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_group_members (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            telegram_user_id BIGINT NOT NULL,
                            group_chat_id BIGINT NOT NULL,
                            first_name VARCHAR(255) DEFAULT NULL,
                            last_name VARCHAR(255) DEFAULT NULL,
                            username VARCHAR(255) DEFAULT NULL,
                            language_code VARCHAR(10) DEFAULT NULL,
                            is_bot TINYINT(1) DEFAULT 0,
                            phone VARCHAR(50) DEFAULT NULL,
                            group_title VARCHAR(255) DEFAULT NULL,
                            is_verified TINYINT(1) DEFAULT 0,
                            verified_at DATETIME DEFAULT NULL,
                            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_tgm_user_id (telegram_user_id),
                            INDEX idx_tgm_group_id (group_chat_id),
                            UNIQUE KEY uq_tgm_user_group (telegram_user_id, group_chat_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_group_members (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            telegram_user_id BIGINT NOT NULL,
                            group_chat_id BIGINT NOT NULL,
                            first_name VARCHAR(255),
                            last_name VARCHAR(255),
                            username VARCHAR(255),
                            language_code VARCHAR(10),
                            is_bot INTEGER DEFAULT 0,
                            phone VARCHAR(50),
                            group_title VARCHAR(255),
                            is_verified INTEGER DEFAULT 0,
                            verified_at DATETIME,
                            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
                            UNIQUE (telegram_user_id, group_chat_id)
                        )
                    """))
                conn.commit()
                logger.info("✅ Created telegram_group_members table")

            # Create user_financials table
            if "user_financials" not in existing_tables:
                logger.info("Creating user_financials table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE user_financials (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            bank_name VARCHAR(100),
                            bank_account_number VARCHAR(50),
                            bank_account_name VARCHAR(100),
                            nssf_number VARCHAR(50),
                            nssf_employee_id VARCHAR(50),
                            spouse_status TINYINT(1),
                            dependent_count INT,
                            is_resident TINYINT(1),
                            base_salary DECIMAL(12,2),
                            currency VARCHAR(10),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
                            INDEX idx_financials_user (user_id),
                            UNIQUE KEY unique_user_financials (user_id)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE user_financials (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            bank_name VARCHAR(100),
                            bank_account_number VARCHAR(50),
                            bank_account_name VARCHAR(100),
                            nssf_number VARCHAR(50),
                            nssf_employee_id VARCHAR(50),
                            spouse_status BOOLEAN,
                            dependent_count INTEGER,
                            is_resident BOOLEAN,
                            base_salary DECIMAL(12,2),
                            currency VARCHAR(10),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
                            UNIQUE(user_id)
                        )
                    """)
                    )
                logger.info("✅ Created user_financials table")

            # Create work_locations table
            if "work_locations" not in existing_tables:
                logger.info("Creating work_locations table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE work_locations (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            latitude FLOAT(10,8) NOT NULL,
                            longitude FLOAT(11,8) NOT NULL,
                            radius_meters INT NOT NULL DEFAULT 100,
                            branch_id INT,
                            is_active TINYINT(1) DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            created_by INT,
                            updated_by INT,
                            INDEX idx_location_branch (branch_id),
                            INDEX idx_location_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE work_locations (
                            id INTEGER PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            latitude REAL NOT NULL,
                            longitude REAL NOT NULL,
                            radius_meters INTEGER NOT NULL DEFAULT 100,
                            branch_id INTEGER,
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            created_by INTEGER,
                            updated_by INTEGER
                        )
                    """)
                    )
                logger.info("✅ Created work_locations table")

            # Create salary_bonuses table
            if "salary_bonuses" not in existing_tables:
                logger.info("Creating salary_bonuses table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_bonuses (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT,
                            name VARCHAR(100) NOT NULL,
                            description VARCHAR(255),
                            type ENUM('FIXED_AMOUNT','HOURLY_RATE','PERCENTAGE') NOT NULL,
                            amount FLOAT NOT NULL,
                            is_enabled TINYINT(1),
                            effective_date DATE NOT NULL,
                            end_date DATE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
                            INDEX idx_bonus_user (user_id),
                            INDEX idx_bonus_type (type),
                            INDEX idx_bonus_effective (effective_date)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_bonuses (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER,
                            name VARCHAR(100) NOT NULL,
                            description VARCHAR(255),
                            type VARCHAR(20) NOT NULL,
                            amount REAL NOT NULL,
                            is_enabled BOOLEAN,
                            effective_date DATE NOT NULL,
                            end_date DATE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME
                        )
                    """)
                    )
                logger.info("✅ Created salary_bonuses table")

            # Create salary_deductions table
            if "salary_deductions" not in existing_tables:
                logger.info("Creating salary_deductions table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_deductions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT,
                            attendance_setting_id INT,
                            name VARCHAR(100) NOT NULL,
                            description VARCHAR(255),
                            type ENUM('FIXED_AMOUNT','HOURLY_RATE','PERCENTAGE') NOT NULL,
                            amount FLOAT NOT NULL,
                            is_enabled TINYINT(1),
                            effective_date DATE NOT NULL,
                            end_date DATE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
                            INDEX idx_deduction_user (user_id),
                            INDEX idx_deduction_type (type),
                            INDEX idx_deduction_effective (effective_date)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_deductions (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER,
                            attendance_setting_id INTEGER,
                            name VARCHAR(100) NOT NULL,
                            description VARCHAR(255),
                            type VARCHAR(20) NOT NULL,
                            amount REAL NOT NULL,
                            is_enabled BOOLEAN,
                            effective_date DATE NOT NULL,
                            end_date DATE,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME
                        )
                    """)
                    )
                logger.info("✅ Created salary_deductions table")

            # Create salary_history table
            if "salary_history" not in existing_tables:
                logger.info("Creating salary_history table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_history (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            financial_id INT NOT NULL,
                            previous_amount DECIMAL(12,2),
                            new_amount DECIMAL(12,2) NOT NULL,
                            change_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                            reason VARCHAR(255),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_salary_history_financial (financial_id),
                            INDEX idx_salary_history_change_date (change_date)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE salary_history (
                            id INTEGER PRIMARY KEY,
                            financial_id INTEGER NOT NULL,
                            previous_amount DECIMAL(12,2),
                            new_amount DECIMAL(12,2) NOT NULL,
                            change_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                            reason VARCHAR(255),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created salary_history table")

            # Create bonus_deduction_rules table
            if "bonus_deduction_rules" not in existing_tables:
                logger.info("Creating bonus_deduction_rules table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE bonus_deduction_rules (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            type VARCHAR(50) NOT NULL,
                            calculation_type VARCHAR(50),
                            amount DECIMAL(12,2) NOT NULL,
                            is_active TINYINT(1),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_rules_type (type),
                            INDEX idx_rules_calculation (calculation_type),
                            INDEX idx_rules_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE bonus_deduction_rules (
                            id INTEGER PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            type VARCHAR(50) NOT NULL,
                            calculation_type VARCHAR(50),
                            amount DECIMAL(12,2) NOT NULL,
                            is_active BOOLEAN,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created bonus_deduction_rules table")

            # ---------------------------------------------------------
            # 7. Add Your New Tables Here
            # ---------------------------------------------------------

            # Create telegram_otp_sessions table (for Telethon-based OTP login)
            if "telegram_otp_sessions" not in existing_tables:
                logger.info("Creating telegram_otp_sessions table...")
                if is_mysql:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_otp_sessions (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            phone VARCHAR(50) NOT NULL,
                            phone_code_hash VARCHAR(255) NOT NULL,
                            session_string TEXT NULL,
                            expires_at DATETIME NOT NULL,
                            used_at DATETIME NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            registration_token_hash VARCHAR(64) NULL,
                            registration_expires_at DATETIME NULL,
                            registration_used_at DATETIME NULL,
                            UNIQUE KEY uq_telegram_otp_sessions_phone (phone),
                            INDEX idx_tos_expires (expires_at),
                            INDEX idx_tos_registration_token (registration_token_hash)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS telegram_otp_sessions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            phone VARCHAR(50) NOT NULL,
                            phone_code_hash VARCHAR(255) NOT NULL,
                            session_string TEXT NULL,
                            expires_at DATETIME NOT NULL,
                            used_at DATETIME NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            registration_token_hash VARCHAR(64) NULL,
                            registration_expires_at DATETIME NULL,
                            registration_used_at DATETIME NULL,
                            UNIQUE (phone)
                        )
                    """))
                conn.commit()
                logger.info("✅ Created telegram_otp_sessions table")

            # Create results_top_students table
            if "results_top_students" not in existing_tables:
                logger.info("Creating results_top_students table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE results_top_students (
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
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE results_top_students (
                            id INTEGER PRIMARY KEY,
                            featured_batch_id VARCHAR(36) NOT NULL,
                            academic_id INTEGER NOT NULL,
                            program_id INTEGER NOT NULL,
                            grade_id INTEGER NOT NULL,
                            shift_id INTEGER NOT NULL,
                            grade_type_id INTEGER,
                            student_id INTEGER NOT NULL,
                            rank INTEGER NOT NULL,
                            average DECIMAL(10,2),
                            grade VARCHAR(20),
                            marks_system_id INTEGER,
                            result_name VARCHAR(255),
                            exam_name VARCHAR(255),
                            exam_type VARCHAR(50),
                            period VARCHAR(50),
                            is_active INTEGER NOT NULL DEFAULT 1,
                            featured_by INTEGER,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created results_top_students table")

            # Create app_branding_settings table
            if "app_branding_settings" not in existing_tables:
                logger.info("Creating app_branding_settings table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE app_branding_settings (
                            id INT PRIMARY KEY,
                            icon_name VARCHAR(120) NOT NULL DEFAULT 'school_rounded',
                            top_text VARCHAR(80) NOT NULL DEFAULT 'PAMA',
                            bottom_text VARCHAR(120) NOT NULL DEFAULT 'INTERNATIONAL SCHOOL',
                            icon_background_color VARCHAR(20) NOT NULL DEFAULT '#1E5BD8',
                            icon_color VARCHAR(20) NOT NULL DEFAULT '#FFFFFF',
                            top_text_color VARCHAR(20) NOT NULL DEFAULT '#22252A',
                            bottom_text_color VARCHAR(20) NOT NULL DEFAULT '#6F7280',
                            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                    conn.execute(
                        text("""
                        INSERT INTO app_branding_settings
                            (id, icon_name, top_text, bottom_text, icon_background_color, icon_color, top_text_color, bottom_text_color)
                        VALUES
                            (1, 'school_rounded', 'PAMA', 'INTERNATIONAL SCHOOL', '#1E5BD8', '#FFFFFF', '#22252A', '#6F7280')
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE app_branding_settings (
                            id INTEGER PRIMARY KEY,
                            icon_name VARCHAR(120) NOT NULL DEFAULT 'school_rounded',
                            top_text VARCHAR(80) NOT NULL DEFAULT 'PAMA',
                            bottom_text VARCHAR(120) NOT NULL DEFAULT 'INTERNATIONAL SCHOOL',
                            icon_background_color VARCHAR(20) NOT NULL DEFAULT '#1E5BD8',
                            icon_color VARCHAR(20) NOT NULL DEFAULT '#FFFFFF',
                            top_text_color VARCHAR(20) NOT NULL DEFAULT '#22252A',
                            bottom_text_color VARCHAR(20) NOT NULL DEFAULT '#6F7280',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                    conn.execute(
                        text("""
                        INSERT INTO app_branding_settings
                            (id, icon_name, top_text, bottom_text, icon_background_color, icon_color, top_text_color, bottom_text_color)
                        VALUES
                            (1, 'school_rounded', 'PAMA', 'INTERNATIONAL SCHOOL', '#1E5BD8', '#FFFFFF', '#22252A', '#6F7280')
                    """)
                    )
                logger.info("✅ Created app_branding_settings table")

            if "app_branding_settings" in existing_tables:
                try:
                    columns = inspector.get_columns("app_branding_settings")
                    column_names = [col["name"] for col in columns]

                    missing_columns = [
                        ("icon_name", "VARCHAR(120) NOT NULL DEFAULT 'school_rounded'"),
                        ("top_text", "VARCHAR(80) NOT NULL DEFAULT 'PAMA'"),
                        (
                            "bottom_text",
                            "VARCHAR(120) NOT NULL DEFAULT 'INTERNATIONAL SCHOOL'",
                        ),
                        (
                            "icon_background_color",
                            "VARCHAR(20) NOT NULL DEFAULT '#1E5BD8'",
                        ),
                        ("icon_color", "VARCHAR(20) NOT NULL DEFAULT '#FFFFFF'"),
                        ("top_text_color", "VARCHAR(20) NOT NULL DEFAULT '#22252A'"),
                        ("bottom_text_color", "VARCHAR(20) NOT NULL DEFAULT '#6F7280'"),
                    ]

                    for col_name, col_def in missing_columns:
                        if col_name not in column_names:
                            conn.execute(
                                text(
                                    f"ALTER TABLE app_branding_settings ADD COLUMN {col_name} {col_def}"
                                )
                            )
                            logger.info(f"✅ Added {col_name} to app_branding_settings")
                except Exception as branding_col_err:
                    logger.warning(
                        f"Could not patch app_branding_settings columns: {branding_col_err}"
                    )

            # Create splash_ads table
            if "splash_ads" not in existing_tables:
                logger.info("Creating splash_ads table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE splash_ads (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            image_url VARCHAR(500) NOT NULL,
                            duration_seconds INT NOT NULL DEFAULT 5,
                            target_url VARCHAR(500),
                            is_active TINYINT(1) NOT NULL DEFAULT 1,
                            start_date DATETIME,
                            end_date DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            INDEX idx_splash_ads_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE splash_ads (
                            id INTEGER PRIMARY KEY,
                            image_url VARCHAR(500) NOT NULL,
                            duration_seconds INTEGER NOT NULL DEFAULT 5,
                            target_url VARCHAR(500),
                            is_active BOOLEAN NOT NULL DEFAULT 1,
                            start_date DATETIME,
                            end_date DATETIME,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created splash_ads table")

            # Create parent_student_link_requests table
            if "parent_student_link_requests" not in existing_tables:
                logger.info("Creating parent_student_link_requests table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE parent_student_link_requests (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            parent_id INT NOT NULL,
                            student_id INT NOT NULL,
                            status VARCHAR(50) DEFAULT 'pending',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE,
                            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE parent_student_link_requests (
                            id INTEGER PRIMARY KEY,
                            parent_id INTEGER NOT NULL,
                            student_id INTEGER NOT NULL,
                            status VARCHAR(50) DEFAULT 'pending',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE,
                            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
                        )
                    """)
                    )
                logger.info("✅ Created parent_student_link_requests table")

            # Add short_code to subjects
            if "subjects" in existing_tables:
                try:
                    columns = inspector.get_columns("subjects")
                    column_names = [col["name"] for col in columns]
                    if "short_code" not in column_names:
                        logger.info("Adding short_code column to subjects table...")
                        if is_mysql:
                            conn.execute(
                                text(
                                    "ALTER TABLE subjects ADD COLUMN short_code VARCHAR(50) DEFAULT NULL"
                                )
                            )
                        else:
                            conn.execute(
                                text(
                                    "ALTER TABLE subjects ADD COLUMN short_code VARCHAR(50) DEFAULT NULL"
                                )
                            )
                        logger.info("✅ Added short_code to subjects")
                except Exception as e:
                    logger.warning(f"Could not check/add short_code to subjects: {e}")

            # Example: Create a new feature table
            # if 'new_feature' not in existing_tables:
            #     logger.info("Creating new_feature table...")
            #     conn.execute(text("""
            #         CREATE TABLE new_feature (
            #             id INT AUTO_INCREMENT PRIMARY KEY,
            #             name VARCHAR(100) NOT NULL,
            #             description TEXT,
            #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            #         )
            #     """))
            #     logger.info("✅ Created new_feature table")

            # Create a new migration (only if you modify SQLAlchemy models)
            # alembic revision --autogenerate -m "Add new feature"

            # Apply the migration
            # alembic upgrade head

            # ===== AUTO-CREATE LEARNING SCHEDULE TABLES =====
            logger.info("Checking learning schedule tables...")

            # Import learning models
            from .models.learning import (
                LearningTimeSlot,
                LearningClassSchedule,
                LearningSessionLog,
                LearningScheduleException,
                LearningTimeSlotScope,
            )

            learning_tables = {
                "learning_time_slots": LearningTimeSlot,
                "learning_time_slot_scopes": LearningTimeSlotScope,
                "learning_class_schedules": LearningClassSchedule,
                "learning_session_logs": LearningSessionLog,
                "learning_schedule_exceptions": LearningScheduleException,
            }

            for table_name, model in learning_tables.items():
                if table_name not in existing_tables:
                    logger.info(f"Creating table: {table_name}")
                    try:
                        model.__table__.create(engine, checkfirst=True)
                        logger.info(f"✅ Created {table_name}")
                    except Exception as table_err:
                        logger.warning(f"Could not create {table_name}: {table_err}")
                else:
                    logger.debug(f"✓ Table {table_name} already exists")

                    # Check for missing columns in existing tables
                    if table_name == "learning_time_slots":
                        try:
                            columns = inspector.get_columns("learning_time_slots")
                            column_names = [col["name"] for col in columns]

                            if "grade_group_id" not in column_names:
                                logger.info(
                                    "Adding grade_group_id column to learning_time_slots..."
                                )
                                if is_mysql:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slots ADD COLUMN grade_group_id INT"
                                        )
                                    )
                                    conn.execute(
                                        text(
                                            "CREATE INDEX ix_learning_time_slots_grade_group_id ON learning_time_slots(grade_group_id)"
                                        )
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slots ADD COLUMN grade_group_id INTEGER"
                                        )
                                    )
                                logger.info(
                                    "✅ Added grade_group_id to learning_time_slots"
                                )

                            if "grade_id" not in column_names:
                                logger.info(
                                    "Adding grade_id column to learning_time_slots..."
                                )
                                if is_mysql:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slots ADD COLUMN grade_id INT"
                                        )
                                    )
                                    conn.execute(
                                        text(
                                            "CREATE INDEX ix_learning_time_slots_grade_id ON learning_time_slots(grade_id)"
                                        )
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slots ADD COLUMN grade_id INTEGER"
                                        )
                                    )
                                logger.info("✅ Added grade_id to learning_time_slots")

                        except Exception as e:
                            logger.warning(
                                f"Could not check/add columns to learning_time_slots: {e}"
                            )

                    # Check for missing columns in learning_time_slot_scopes
                    if table_name == "learning_time_slot_scopes":
                        try:
                            columns = inspector.get_columns("learning_time_slot_scopes")
                            column_names = [col["name"] for col in columns]

                            if "shift_id" not in column_names:
                                logger.info(
                                    "Adding shift_id column to learning_time_slot_scopes..."
                                )
                                if is_mysql:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slot_scopes ADD COLUMN shift_id INT DEFAULT NULL COMMENT 'Optional shift restriction'"
                                        )
                                    )
                                    conn.execute(
                                        text(
                                            "CREATE INDEX ix_learning_scopes_shift_id ON learning_time_slot_scopes(shift_id)"
                                        )
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE learning_time_slot_scopes ADD COLUMN shift_id INTEGER"
                                        )
                                    )
                                logger.info(
                                    "✅ Added shift_id to learning_time_slot_scopes"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Could not check/add columns to learning_time_slot_scopes: {e}"
                            )

                    # Fix grade_type_id column type in learning_class_schedules
                    if table_name == "background_cert":
                        try:
                            columns = inspector.get_columns("background_cert")
                            column_names = [col["name"] for col in columns]

                            if "orientation" not in column_names:
                                print("Adding orientation column to background_cert...")
                                if is_mysql:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE background_cert ADD COLUMN orientation VARCHAR(20) DEFAULT 'landscape' NOT NULL"
                                        )
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE background_cert ADD COLUMN orientation VARCHAR(20) DEFAULT 'landscape'"
                                        )
                                    )
                                print("✅ Added orientation column to background_cert")
                            else:
                                print("✓ background_cert.orientation already exists")

                            if "grade_group_id" not in column_names:
                                print("Adding grade_group_id column to background_cert...")
                                conn.execute(
                                    text(
                                        "ALTER TABLE background_cert ADD COLUMN grade_group_id INT NULL"
                                    )
                                )
                                print("✅ Added grade_group_id column to background_cert")
                            else:
                                print("✓ background_cert.grade_group_id already exists")
                        except Exception as e:
                            logger.warning(
                                f"Could not check/add columns to background_cert: {e}"
                            )

                    if table_name == "certificate_settings":
                        try:
                            columns = inspector.get_columns("certificate_settings")
                            column_names = [col["name"] for col in columns]

                            if "orientation" not in column_names:
                                print("Adding orientation column to certificate_settings...")
                                if is_mysql:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE certificate_settings ADD COLUMN orientation VARCHAR(20) DEFAULT 'landscape' NOT NULL"
                                        )
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "ALTER TABLE certificate_settings ADD COLUMN orientation VARCHAR(20) DEFAULT 'landscape'"
                                        )
                                    )
                                print("✅ Added orientation column")
                            else:
                                print("✓ certificate_settings.orientation already exists")
                        except Exception as e:
                            logger.warning(
                                f"Could not check/add orientation to certificate_settings: {e}"
                            )

                    # Fix grade_type_id column type in learning_class_schedules
                    if table_name == "learning_class_schedules":
                        try:
                            columns = inspector.get_columns("learning_class_schedules")
                            for col in columns:
                                if col["name"] == "grade_type_id":
                                    # Check if it's VARCHAR instead of INT
                                    col_type = str(col["type"]).upper()
                                    if "VARCHAR" in col_type or "CHAR" in col_type:
                                        logger.info(
                                            "Fixing grade_type_id column type from VARCHAR to INT..."
                                        )
                                        if is_mysql:
                                            conn.execute(
                                                text(
                                                    "ALTER TABLE learning_class_schedules "
                                                    "MODIFY COLUMN grade_type_id INT NULL "
                                                    "COMMENT 'Specific single grade type ID for this schedule'"
                                                )
                                            )
                                        else:
                                            # For SQLite, would need to recreate table
                                            conn.execute(
                                                text(
                                                    "ALTER TABLE learning_class_schedules "
                                                    "ALTER COLUMN grade_type_id TYPE INTEGER"
                                                )
                                            )
                                        logger.info(
                                            "✅ Fixed grade_type_id column type to INT"
                                        )
                                        break
                        except Exception as e:
                            logger.warning(
                                f"Could not check/fix grade_type_id column: {e}"
                            )

            logger.info("✅ Learning schedule tables verified")

            # Backfill grade data for existing schedules (runs after table checks)
            try:
                logger.info("Checking for schedules missing grade data...")
                if is_mysql:
                    backfill_result = conn.execute(
                        text("""
                        UPDATE learning_class_schedules lcs
                        JOIN grade g ON g.group_id = lcs.grade_group_id 
                            AND g.academic_id = lcs.academic_id
                        SET lcs.grade_id = g.id,
                            lcs.grade_type_id = CAST(SUBSTRING_INDEX(g.grade_type_id, ',', 1) AS UNSIGNED)
                        WHERE lcs.grade_id IS NULL
                    """)
                    )
                    updated_count = backfill_result.rowcount
                    if updated_count > 0:
                        logger.info(
                            f"✅ Backfilled grade_id and grade_type_id for {updated_count} schedules"
                        )
                    else:
                        logger.info("✓ All schedules already have grade data")
            except Exception as backfill_err:
                logger.warning(f"Could not backfill grade data: {backfill_err}")

            # ---------------------------------------------------------
            # 5. Profile Frames System Tables
            # ---------------------------------------------------------
            if "profile_frames" not in existing_tables:
                logger.info("Creating profile_frames table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE profile_frames (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            title VARCHAR(255) NULL,
                            image_url VARCHAR(500) NOT NULL,
                            is_active TINYINT(1) DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_profile_frames_active (is_active)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE profile_frames (
                            id INTEGER PRIMARY KEY,
                            title VARCHAR(255) NULL,
                            image_url VARCHAR(500) NOT NULL,
                            is_active BOOLEAN DEFAULT 1,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    )
                logger.info("✅ Created profile_frames table")

            if "profile_frame_history" not in existing_tables:
                logger.info("Creating profile_frame_history table...")
                if is_mysql:
                    conn.execute(
                        text("""
                        CREATE TABLE profile_frame_history (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            user_id INT NOT NULL,
                            frame_id INT NULL,
                            generated_image_url VARCHAR(500) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            INDEX idx_profile_frame_history_user (user_id),
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (frame_id) REFERENCES profile_frames(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """)
                    )
                else:
                    conn.execute(
                        text("""
                        CREATE TABLE profile_frame_history (
                            id INTEGER PRIMARY KEY,
                            user_id INTEGER NOT NULL,
                            frame_id INTEGER NULL,
                            generated_image_url VARCHAR(500) NOT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                            FOREIGN KEY (frame_id) REFERENCES profile_frames(id) ON DELETE SET NULL
                        )
                    """)
                    )
                logger.info("✅ Created profile_frame_history table")

            # ---------------------------------------------------------
            # Auto-patch: add new columns to profile_frames
            # ---------------------------------------------------------
            if is_mysql:
                try:
                    columns_to_check = [
                        ('sort_order', 'INT NOT NULL DEFAULT 0'),
                        ('deleted_at', 'DATETIME NULL'),
                        ('user_id', 'INT NULL'),
                        ('is_public', 'BOOLEAN DEFAULT 1'),
                        ('is_featured', 'BOOLEAN DEFAULT 0'),
                        ('slug', 'VARCHAR(255) NULL UNIQUE')
                    ]
                    
                    for col_name, col_def in columns_to_check:
                        has_col = conn.execute(text(f"""
                            SELECT COUNT(*) FROM information_schema.COLUMNS
                            WHERE TABLE_SCHEMA = DATABASE()
                              AND TABLE_NAME = 'profile_frames'
                              AND COLUMN_NAME = '{col_name}'
                        """)).scalar()
                        
                        if not has_col:
                            conn.execute(text(f"ALTER TABLE profile_frames ADD COLUMN {col_name} {col_def}"))
                            logger.info(f"✅ Added {col_name} to profile_frames")
                except Exception as patch_err:
                    logger.warning(f"profile_frames column patch warning: {patch_err}")
            elif is_sqlite:
                try:
                    columns = inspector.get_columns("profile_frames")
                    column_names = [col["name"] for col in columns]
                    
                    columns_to_add = {
                        'sort_order': 'INTEGER DEFAULT 0',
                        'deleted_at': 'DATETIME',
                        'user_id': 'INTEGER',
                        'is_public': 'BOOLEAN DEFAULT 1',
                        'is_featured': 'BOOLEAN DEFAULT 0',
                        'slug': 'VARCHAR(255) UNIQUE'
                    }
                    
                    for col_name, col_def in columns_to_add.items():
                        if col_name not in column_names:
                            conn.execute(text(f"ALTER TABLE profile_frames ADD COLUMN {col_name} {col_def}"))
                            logger.info(f"✅ Added {col_name} to profile_frames")
                except Exception as patch_err:
                    logger.warning(f"profile_frames sqlite column patch warning: {patch_err}")

            conn.commit()

    except Exception as e:
        logger.error(f"❌ Database migration failed: {e}")
        # Don't fail startup for migration issues - log and continue
        logger.warning("Continuing with application startup despite migration issues")


# Configure logging
if settings.is_development:
    # More verbose logging for development
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        if settings.log_format == "text"
        else "%(levelname)s: %(message)s",
    )
else:
    # Cleaner logging for production
    # Safely convert log_level string to logging constant
    try:
        log_level_value = getattr(logging, str(settings.log_level).upper(), logging.INFO)
        # Validate it's an integer (logging levels are integers)
        if not isinstance(log_level_value, int):
            log_level_value = logging.INFO
    except Exception:
        log_level_value = logging.INFO
    
    logging.basicConfig(
        level=log_level_value,
        format="%(levelname)s: %(message)s"
        if settings.log_format == "text"
        else "%(levelname)s: %(message)s",
    )

logger = logging.getLogger(__name__)

_OTP_CLEANUP_INTERVAL_SEC = 300  # 5 minutes


async def _otp_cache_cleanup_loop() -> None:
    """Periodically drop expired in-memory OTP entries and finished lockouts."""
    from .services.email_service import cleanup_expired_otps

    while True:
        try:
            await asyncio.sleep(_OTP_CLEANUP_INTERVAL_SEC)
            cleanup_expired_otps()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Periodic OTP cache cleanup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import os as _os
    from .core.render_keepalive import (
        resolve_render_keepalive_url,
        run_render_keepalive,
    )

    _worker_id = int(_os.environ.get("WORKER_ID", "1"))
    _is_primary_worker = _worker_id == 1

    logger.info(
        f"Starting {settings.app_name} v{settings.app_version} [worker #{_worker_id}]"
    )
    logger.info(f"Environment: {settings.environment}")
    masked_url = settings.database_url
    if "@" in masked_url:
        masked_url = masked_url.replace(masked_url.split("@")[0].split(":")[-1], "***")
    logger.info(f"Connecting to Database: {masked_url}")

    # ─── HEAVY STARTUP: Only run on primary worker (worker #1) ──────────────────
    # Workers 2-4 skip migrations entirely so they boot in seconds.
    # Migrations are idempotent — running them once per deploy is sufficient.
    if _is_primary_worker:
        try:
            from .core.auto_deps import auto_check_and_install_dependencies
            auto_check_and_install_dependencies()
        except Exception as e:
            logger.warning(f"Auto-dependency check encountered issue: {e}")

    if _is_primary_worker and settings.auto_migrate_on_startup:
        logger.info("🔧 Primary worker — running startup migrations...")

        # 0. Run Alembic migrations programmatically (paths anchored to API root so cwd does not matter)
        try:
            logger.info("Running Alembic migrations (upgrade head)...")
            _api_root = Path(__file__).resolve().parent.parent
            _alembic_ini = _api_root / "config" / "alembic.ini"
            if not _alembic_ini.is_file():
                raise FileNotFoundError(f"Alembic config not found: {_alembic_ini}")
            alembic_cfg = Config(str(_alembic_ini))
            _script_loc = _api_root / "config" / "alembic"
            alembic_cfg.set_main_option("script_location", str(_script_loc))
            alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
            command.upgrade(alembic_cfg, "head")
            logger.info("✅ Alembic migrations applied successfully.")
        except Exception as e:
            logger.error(f"❌ Alembic migration failed: {e}", exc_info=True)

        # 1. Automatic Schema Sync (Create missing tables/columns based on Models)
        try:
            sync_database_schema(engine, Base.metadata)
        except Exception as e:
            logger.error(f"Auto-migrate failed: {e}")

        # 2. Run manual migrations (Schema patches & raw SQL tables)
        await run_database_migrations()

        # 3. Run legacy/core migrations script (idempotent)
        try:
            run_migrations()
        except Exception as e:
            logger.error(f"Legacy migrations failed: {e}")
            logger.warning("Continuing startup despite legacy migration errors")

        # 4. Create performance indexes for frequently queried columns
        try:
            from .core.auto_index import apply_index_migrations

            applied, skipped, errors = apply_index_migrations(engine)
            if applied > 0:
                logger.info(f"✅ Applied {applied} new performance indexes ({skipped} already existed)")
            else:
                logger.info(f"✅ All performance indexes up-to-date ({skipped} indexes verified)")
        except Exception as e:
            logger.warning(f"Could not create performance indexes: {e}")

        # 5. Create attendance audit & statistics tables
        try:
            from .core.auto_migrate_attendance import run_attendance_migrations

            run_attendance_migrations(engine)
        except Exception as e:
            logger.warning(f"Attendance migration error: {e}")

        # 6. Ensure Telegram settings default row exists
        try:
            from sqlalchemy import text, inspect
            
            with engine.connect() as conn:
                inspector = inspect(engine)
                
                # Check if table exists cross-database
                if inspector.has_table("telegram_attendance_settings"):
                    # Check if default row exists
                    result = conn.execute(text("""
                        SELECT COUNT(*) FROM telegram_attendance_settings
                    """))
                    row_count = result.scalar()
                    
                    if row_count == 0:
                        # Insert default row safely without NOW() since created_at has defaults
                        is_mysql = engine.dialect.name == "mysql"
                        if is_mysql:
                            conn.execute(text("""
                                INSERT INTO telegram_attendance_settings (id, bot_token, chat_id, enabled, created_at, updated_at)
                                VALUES (1, '8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw', NULL, FALSE, NOW(), NOW())
                            """))
                        else:
                            conn.execute(text("""
                                INSERT OR REPLACE INTO telegram_attendance_settings (id, bot_token, chat_id, enabled, created_at, updated_at)
                                VALUES (1, '8686190656:AAEl84Nkz7WwDe1SMn323iNV93BnIUeTvfw', NULL, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """))
                        conn.commit()
                        logger.info("✅ Created default Telegram settings row")
                    else:
                        logger.info("✓ Telegram settings table already has data")
                else:
                    logger.warning("⚠️ telegram_attendance_settings table does not exist yet")
        except Exception as e:
            logger.warning(f"Could not ensure Telegram settings: {e}")

        # Seed Permissions
        try:
            db = SessionLocal()
            check_and_update_schema(db)
            seed_permissions(db)
            db.close()
        except Exception as e:
            logger.error(f"Error seeding permissions: {e}")

        # Cleanup expired OTPs and lockouts on startup
        try:
            from .services.email_service import cleanup_expired_otps

            cleanup_expired_otps()
            logger.info("✅ OTP cache cleanup completed on startup")
        except Exception as e:
            logger.warning(f"OTP cache cleanup failed on startup: {e}")

        logger.info("✅ Primary worker startup complete.")
    elif not settings.auto_migrate_on_startup:
        logger.info(
            "⏭️ AUTO_MIGRATE_ON_STARTUP is disabled — skipping startup migrations."
        )
    else:
        logger.info(
            f"⚡ Worker #{_worker_id} — skipping migrations (primary worker handles them). Ready to serve."
        )

    # Start schedule reminder cron (fires every minute, sends FCM 15min before class)
    # IMPORTANT: Only run scheduler in ONE worker process to avoid 4× duplicate notifications.
    # Gunicorn sets WORKER_ID starting from 1. We only run on worker 1 (or if var not set).
    _scheduler = None
    _has_leader_lock = False
    _leader_lock_fh = None
    if settings.background_jobs_enabled:
        try:
            from .services.background_job_scheduler import (
                try_acquire_background_job_lock,
            )

            _leader_lock_fh = try_acquire_background_job_lock()
            if _leader_lock_fh is None:
                raise BlockingIOError("background-job leader lock is busy")
            _has_leader_lock = True
            logger.info(f"👑 Worker #{_worker_id} acquired leader lock — starting primary cron tasks.")
        except ImportError:
            _has_leader_lock = _is_primary_worker
            logger.warning("fcntl not available. Falling back to primary worker check.")
        except Exception as e:
            logger.info(f"⏭️  Worker #{_worker_id} failed to acquire leader lock: {e} — running as regular request handler.")
            if _leader_lock_fh:
                try:
                    _leader_lock_fh.close()
                except Exception:
                    pass
                _leader_lock_fh = None
    else:
        logger.info(
            "⏭️  BACKGROUND_JOBS_ENABLED is disabled — skipping scheduled jobs."
        )

    def _start_background_jobs():
        try:
            from .services.background_job_scheduler import (
                start_background_job_scheduler,
            )

            scheduler = start_background_job_scheduler()
            logger.info(
                "✅ Schedule reminder cron started (every 1 minute) [primary leader worker]"
            )
            logger.info(
                "✅ Cache cleanup cron started (every 5 minutes) [primary leader worker]"
            )
            logger.info(
                "✅ Pending-student cleanup cron started (daily 23:00 ICT, 7-day expiry) [primary leader worker]"
            )
            logger.info(
                "✅ Parent attendance notification cleanup cron started "
                "(daily 23:05 ICT, 7-day retention) [primary leader worker]"
            )
            logger.info(
                "✅ Reminder/wish notification cleanup cron started "
                "(daily 23:50 ICT; reminders wiped, wishes 3-day retention) "
                "[primary leader worker]"
            )
            return scheduler
        except Exception as e:
            logger.error(f"❌ Failed to start scheduled jobs: {e}")
            return None

    if _has_leader_lock:
        _scheduler = _start_background_jobs()
    else:
        logger.info(
            f"⏭️  Worker #{_worker_id} is waiting to take over scheduled jobs if needed"
        )

    # OTP cleanup: only leader worker runs this (avoids 4 workers doing same DB delete)
    otp_cleanup_task = None
    if _has_leader_lock:
        otp_cleanup_task = asyncio.create_task(_otp_cache_cleanup_loop())
        logger.info(
            f"✅ OTP DB cleanup scheduled (every {_OTP_CLEANUP_INTERVAL_SEC}s) [primary leader worker]"
        )
    else:
        logger.info(f"⏭️  OTP DB cleanup skipped (worker #{_worker_id}, not leader)")

    # Gunicorn recycles workers after max_requests. A replacement can start
    # before the old leader releases its file lock, so a one-time lock attempt
    # can permanently stop every cron job. Every worker keeps polling; exactly
    # one takes over within a few seconds after leadership becomes available.
    scheduler_leader_watchdog_task = None
    if settings.background_jobs_enabled:
        async def _watch_scheduler_leadership() -> None:
            nonlocal _has_leader_lock, _leader_lock_fh, _scheduler
            nonlocal otp_cleanup_task

            while True:
                if _has_leader_lock:
                    if _scheduler is None or not _scheduler.running:
                        _scheduler = _start_background_jobs()
                    await asyncio.sleep(5)
                    continue

                try:
                    from .services.background_job_scheduler import (
                        try_acquire_background_job_lock,
                    )

                    candidate_lock_fh = try_acquire_background_job_lock()
                except ImportError:
                    # Non-POSIX development hosts keep the existing primary
                    # worker fallback; production Linux always has fcntl.
                    return
                except Exception:
                    await asyncio.sleep(5)
                    continue

                if candidate_lock_fh is None:
                    await asyncio.sleep(5)
                    continue

                _leader_lock_fh = candidate_lock_fh
                _has_leader_lock = True
                logger.info(
                    "👑 Worker #%s took over background-job leadership",
                    _worker_id,
                )
                _scheduler = _start_background_jobs()
                if otp_cleanup_task is None:
                    otp_cleanup_task = asyncio.create_task(
                        _otp_cache_cleanup_loop()
                    )

        scheduler_leader_watchdog_task = asyncio.create_task(
            _watch_scheduler_leadership()
        )

    # Start DB pub/sub polling loop — cross-worker WebSocket broadcasting (free, no Redis)
    from .api.v1.websocket import start_poll_loop

    ws_poll_task = await start_poll_loop()
    from .api.v1.websocket import bind_event_loop

    bind_event_loop(asyncio.get_running_loop())
    logger.info("✅ WebSocket DB pub/sub polling loop started (every 500ms)")

    # Start rate limit storage cleanup
    rate_limit_cleanup_task = asyncio.create_task(_cleanup_rate_limit_storage())
    logger.info("✅ Rate limit memory cleanup task started")

    # Render free services spin down after an idle period. This optional,
    # Render-host-restricted heartbeat is disabled everywhere by default and is
    # run only by the primary worker when explicitly enabled on Render.
    render_keepalive_task = None
    if _is_primary_worker and settings.render_keepalive_enabled:
        render_keepalive_url = resolve_render_keepalive_url(
            settings.render_keepalive_url,
            _os.environ.get("RENDER_EXTERNAL_URL", ""),
        )
        if render_keepalive_url:
            render_keepalive_task = asyncio.create_task(
                run_render_keepalive(
                    render_keepalive_url,
                    settings.render_keepalive_interval_seconds,
                )
            )
            logger.info(
                "✅ Render keepalive enabled (every %ss)",
                settings.render_keepalive_interval_seconds,
            )
        else:
            logger.error(
                "RENDER_KEEPALIVE_ENABLED is true, but no valid HTTPS "
                "*.onrender.com target is configured"
            )

    yield

    # Shutdown
    if scheduler_leader_watchdog_task:
        scheduler_leader_watchdog_task.cancel()
        try:
            await scheduler_leader_watchdog_task
        except asyncio.CancelledError:
            pass

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Schedule reminder cron stopped")
    if otp_cleanup_task:
        otp_cleanup_task.cancel()
        try:
            await otp_cleanup_task
        except asyncio.CancelledError:
            pass

    rate_limit_cleanup_task.cancel()
    try:
        await rate_limit_cleanup_task
    except asyncio.CancelledError:
        pass

    if render_keepalive_task:
        render_keepalive_task.cancel()
        try:
            await render_keepalive_task
        except asyncio.CancelledError:
            pass

    ws_poll_task.cancel()
    try:
        await ws_poll_task
    except asyncio.CancelledError:
        pass

    if _leader_lock_fh:
        try:
            import fcntl
            fcntl.flock(_leader_lock_fh, fcntl.LOCK_UN)
            _leader_lock_fh.close()
            logger.info("Released leader lock successfully")
        except Exception as e:
            logger.error(f"Error releasing leader lock: {e}")

    logger.info("Shutting down application")


# Initialize FastAPI app with production settings
app = FastAPI(
    title=settings.app_name,
    description="A comprehensive API for managing students, teachers, and classes",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

# Add middleware in order (important: order matters!)

# 1. Request ID Middleware - Adds unique ID to each request for tracing
from .middleware import RequestIDMiddleware, UserContextMiddleware, LoggingMiddleware
app.add_middleware(RequestIDMiddleware)
logger.info("✅ Request ID middleware added")

# 2. Logging Middleware - Logs all requests with timing
app.add_middleware(LoggingMiddleware)
logger.info("✅ Logging middleware added")

# 3. Add security middleware
if settings.is_production:
    # SECURITY: Use configured allowed_hosts in production (no wildcards)
    if settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # type: ignore
    else:
        logger.warning(
            "Production mode but ALLOWED_HOSTS is empty: TrustedHostMiddleware is not "
            "enabled, so the Host header is not restricted. Set ALLOWED_HOSTS to your API "
            "hostnames (e.g. pamais.onrender.com)."
        )

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
logger.info("✅ GZip response compression middleware added")

# Add CORS middleware with production settings.
#
# A wildcard origin combined with credentials lets ANY website make
# authenticated requests to this API from a victim's browser. Starlette echoes
# the caller's origin back when allow_origins is ["*"], so the browser's usual
# refusal to combine "*" with credentials does not save us here. Deployments
# that really want a wildcard (e.g. an internal box) keep working, but
# credentials are dropped rather than silently handing them out, and the
# combination is logged loudly so it cannot pass unnoticed.
_cors_allows_any_origin = "*" in (settings.cors_origins or [])
_cors_allow_credentials = not _cors_allows_any_origin
if _cors_allows_any_origin:
    logger.error(
        "SECURITY: CORS_ORIGINS is ['*']. Credentialed cross-origin requests are "
        "disabled for safety. Set CORS_ORIGINS to your real front-end origins."
    )

app.add_middleware(
    CORSMiddleware,  # type: ignore
    allow_origins=settings.cors_origins,  # type: ignore
    allow_credentials=_cors_allow_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


# API Timing middleware
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
    logger.info(f"{request.method} {request.url.path} took {process_time:.2f}ms")
    return response


# Rate limiting middleware
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

_rate_limit_lock: asyncio.Lock  # initialised in lifespan
_rate_limit_locks: dict[str, asyncio.Lock] = {}
rate_limit_storage: dict[str, list] = defaultdict(list)


async def _cleanup_rate_limit_storage():
    """Periodically evict IPs whose windows have expired to prevent memory growth."""
    while True:
        await asyncio.sleep(60)  # run every minute
        cutoff = datetime.now() - timedelta(seconds=settings.rate_limit_window)
        stale = [
            ip for ip, ts in rate_limit_storage.items() if not ts or ts[-1] < cutoff
        ]
        for ip in stale:
            rate_limit_storage.pop(ip, None)
            _rate_limit_locks.pop(ip, None)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Rate limiting enabled in production
    if settings.is_production and request.client:
        # X-Forwarded-For is a client-supplied header: anyone can rotate it and
        # get a fresh bucket, which makes this limiter decorative. It is only
        # believed when the direct peer is a reverse proxy listed in
        # TRUSTED_PROXY_RANGES. While that is unset we keep the previous
        # behaviour, because tightening it without the operator configuring the
        # load balancer's range would put every request into one shared bucket.
        from .utils.client_ip import rate_limit_key

        client_ip = rate_limit_key(request)
        if not client_ip:
            return await call_next(request)

        # Per-IP lock prevents check-then-act race under concurrent requests
        if client_ip not in _rate_limit_locks:
            _rate_limit_locks[client_ip] = asyncio.Lock()
        async with _rate_limit_locks[client_ip]:
            current_time = datetime.now()

            # Clean old entries for this IP
            rate_limit_storage[client_ip] = [
                timestamp
                for timestamp in rate_limit_storage[client_ip]
                if current_time - timestamp
                < timedelta(seconds=settings.rate_limit_window)
            ]

            # Check rate limit
            if len(rate_limit_storage[client_ip]) >= settings.rate_limit_requests:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again later."},
                )

            # Add current request
            rate_limit_storage[client_ip].append(current_time)

    response = await call_next(request)
    return response


# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    if settings.is_production:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


# Security
security = HTTPBearer()


# Preserve structured HTTP errors, including details containing datetime or
# enum values, without accidentally converting their intended 4xx status into
# an unrelated 500 during JSON rendering.
app.add_exception_handler(
    StarletteHTTPException,
    json_safe_http_exception_handler,
)


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error. Please check logs."
            if settings.is_development
            else "Internal Server Error"
        },
    )


# Include API router
app.include_router(api_router, prefix="/api/v1")  # type: ignore
app.include_router(desktop_api_router, prefix="/api/desktop")
app.include_router(web_api_router, prefix="/api/web")

# Mount static files for uploads (ads images)
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
from .core.push_assets import (
    CERTIFICATE_PUSH_IMAGE_RELATIVE,
    resolve_certificate_push_image_path,
    seed_certificate_push_image,
)

seed_certificate_push_image()


@app.get(CERTIFICATE_PUSH_IMAGE_RELATIVE, include_in_schema=False)
async def serve_certificate_push_notification_image():
    """
    Public URL for FCM / parent app (PUBLIC_API_BASE_URL + this path).
    Serves from uploads/push, falling back to app/static/push from Git.
    """
    path = resolve_certificate_push_image_path()
    if path is None or not path.is_file():
        return JSONResponse(
            status_code=404,
            content={
                "detail": (
                    "Certificate push image missing. "
                    "Commit app/static/push/notification_certificate.jpg and redeploy."
                ),
            },
        )
    return FileResponse(path, media_type="image/jpeg")


@app.api_route(
    "/uploads/news/videos/{file_name}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def stream_local_news_video(file_name: str, request: Request):
    """Serve local MP4 files with byte ranges for startup, buffering, and seek."""
    from .services.http_range import parse_single_byte_range

    # This route deliberately accepts only the generated flat filenames.
    if Path(file_name).name != file_name or not file_name.endswith(".mp4"):
        return JSONResponse(status_code=404, content={"detail": "Video not found"})
    video_path = uploads_dir / "news" / "videos" / file_name
    if not video_path.is_file():
        return JSONResponse(status_code=404, content={"detail": "Video not found"})

    file_size = video_path.stat().st_size
    try:
        requested_range = parse_single_byte_range(
            request.headers.get("range"),
            file_size,
        )
    except ValueError:
        return Response(
            status_code=416,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{file_size}",
            },
        )

    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
    }
    if requested_range is None:
        if request.method == "HEAD":
            return Response(
                headers={**common_headers, "Content-Length": str(file_size)},
                media_type="video/mp4",
            )
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers=common_headers,
        )

    start, end = requested_range
    content_length = end - start + 1
    headers = {
        **common_headers,
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
    }
    if request.method == "HEAD":
        return Response(status_code=206, headers=headers, media_type="video/mp4")

    def iter_file_range():
        remaining = content_length
        with video_path.open("rb") as source:
            source.seek(start)
            while remaining > 0:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file_range(),
        status_code=206,
        headers=headers,
        media_type="video/mp4",
    )


app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

# Include WebSocket endpoint
from .api.v1.websocket import websocket_endpoint

app.websocket("/ws")(websocket_endpoint)

# =============================================================
# 🔗 DEEP LINK VERIFICATION FILES
# These endpoints are required by Android (App Links) and iOS (Universal Links)
# to automatically open the PAMAIS app without prompting the user.
# Android verifies: GET /.well-known/assetlinks.json
# iOS verifies:     GET /.well-known/apple-app-site-association
# =============================================================

@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def android_assetlinks():
    """Android App Links verification for this deployment's package."""
    return JSONResponse(
        content=[
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": settings.android_application_id,
                    "sha256_cert_fingerprints": settings.android_sha256_list
                    or [
                        "18:DF:B4:DA:AD:CE:FF:24:10:AA:A5:36:1C:C0:54:06:A6:7F:73:57:79:3E:98:0D:E3:04:4E:A1:F9:E0:8F:85"
                    ],
                },
            }
        ],
        headers={"Content-Type": "application/json"},
    )


@app.get("/.well-known/apple-app-site-association", include_in_schema=False)
async def ios_apple_app_site_association():
    """iOS Universal Links verification for this deployment's bundle id."""
    return JSONResponse(
        content={
            "applinks": {
                "apps": [],
                "details": [
                    {
                        "appID": settings.ios_app_id_for_association,
                        "paths": ["/*"],
                    }
                ],
            }
        },
        headers={"Content-Type": "application/json"},
    )

from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse

templates = Jinja2Templates(directory="app/templates")


def _mobile_app_auto_launch_script(app_uri: str, intent_path: str) -> str:
    """Try the app once, then leave a user-gesture fallback for strict browsers."""
    scheme = settings.deep_link_scheme
    package = settings.android_application_id
    app_title = settings.mobile_app_title.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
<script>
  (function () {{
    var appUri = "{app_uri}";
    var isAndroid = /Android/i.test(navigator.userAgent);
    var isIOS = /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var params = new URLSearchParams(window.location.search);
    var manualFallback = params.get("manual") === "1";
    var fallbackUrl = window.location.origin + window.location.pathname + "?manual=1";
    var appTitle = "{app_title}";
    var intentUri = "intent://{intent_path}#Intent;scheme={scheme};" +
      "package={package};S.browser_fallback_url=" +
      encodeURIComponent(fallbackUrl) + ";end";
    var button = document.getElementById("open-pamais");
    var status = document.getElementById("launch-status");

    if (button) {{
      button.href = isAndroid ? intentUri : appUri;
      button.addEventListener("click", function () {{
        if (status) {{
          status.style.display = "block";
          status.textContent = "Opening " + appTitle + "…";
        }}
      }});
    }}

    if (manualFallback || (!isAndroid && !isIOS)) return;
    if (status) {{
      status.style.display = "block";
      status.textContent = "Opening " + appTitle + "…";
    }}

    // Telegram and other in-app browsers may block this without a tap. The
    // explicit-package Android intent and the visible button cover both cases.
    window.location.replace(isAndroid ? intentUri : appUri);
    window.setTimeout(function () {{
      if (status) {{
        status.textContent = "Not opening automatically? Tap Open " + appTitle + " below.";
      }}
    }}, 1800);
  }})();
</script>"""


@app.get("/leave/{request_id}", response_class=HTMLResponse, include_in_schema=False)
async def leave_request_app_link(request_id: int):
    """Safe browser fallback when the mobile app cannot open the leave link."""
    normalized_request_id = int(request_id)
    app_title = settings.mobile_app_title
    app_uri = f"{settings.deep_link_scheme}://leave/{normalized_request_id}"
    launch_script = _mobile_app_auto_launch_script(
        app_uri,
        f"leave/{normalized_request_id}",
    )
    play_store = settings.play_store_url
    app_store = settings.app_store_url or play_store
    store_id = settings.ios_app_store_id
    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="apple-itunes-app" content="app-id={store_id}, app-argument={app_uri}">
  <title>Open leave request · {app_title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(145deg, #eff6ff, #f8fafc); color: #0f172a; }}
    main {{ width: min(100%, 420px); background: white; padding: 28px;
      border: 1px solid #dbeafe; border-radius: 24px; text-align: center;
      box-shadow: 0 20px 55px rgba(15, 23, 42, .10); }}
    .icon {{ width: 64px; height: 64px; margin: 0 auto 16px; display: grid;
      place-items: center; border-radius: 18px; background: #dbeafe; font-size: 30px; }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    p {{ margin: 0 0 22px; color: #64748b; line-height: 1.5; }}
    a {{ display: block; padding: 14px 16px; border-radius: 12px;
      text-decoration: none; font-weight: 700; }}
    .open {{ color: white; background: #1677f2; margin-bottom: 12px; }}
    #launch-status {{ display: none; margin: -10px 0 16px; color: #1677f2;
      font-size: 13px; font-weight: 600; }}
    .stores {{ display: flex; gap: 10px; }}
    .stores a {{ flex: 1; color: #1677f2; background: #eff6ff; font-size: 13px; }}
    small {{ display: block; margin-top: 18px; color: #94a3b8; line-height: 1.4; }}
  </style>
</head>
<body><main>
  <div class="icon">🗓️</div>
  <h1>Leave request</h1>
  <p>Open {app_title} to securely view this request. Your account permissions will be checked in the app.</p>
  <p id="launch-status" aria-live="polite"></p>
  <a class="open" id="open-pamais" href="{app_uri}">Open {app_title}</a>
  <div class="stores">
    <a href="{app_store}">App Store</a>
    <a href="{play_store}">Google Play</a>
  </div>
  <small>No leave details or approval permission are stored in this link.</small>
</main>{launch_script}</body></html>""")


@app.get("/form/{form_id}", response_class=HTMLResponse, include_in_schema=False)
async def form_app_link(form_id: int):
    """Browser fallback when the mobile app cannot open a shared form link."""
    normalized_form_id = int(form_id)
    app_title = settings.mobile_app_title
    app_uri = f"{settings.deep_link_scheme}://form/{normalized_form_id}"
    launch_script = _mobile_app_auto_launch_script(
        app_uri,
        f"form/{normalized_form_id}",
    )
    play_store = settings.play_store_url
    app_store = settings.app_store_url or play_store
    store_id = settings.ios_app_store_id
    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="apple-itunes-app" content="app-id={store_id}, app-argument={app_uri}">
  <title>Complete form · {app_title}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(145deg, #ecfdf5, #f8fafc); color: #0f172a; }}
    main {{ width: min(100%, 420px); background: white; padding: 28px;
      border: 1px solid #bbf7d0; border-radius: 24px; text-align: center;
      box-shadow: 0 20px 55px rgba(15, 23, 42, .10); }}
    .icon {{ width: 64px; height: 64px; margin: 0 auto 16px; display: grid;
      place-items: center; border-radius: 18px; background: #dcfce7; font-size: 30px; }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    p {{ margin: 0 0 22px; color: #64748b; line-height: 1.5; }}
    a {{ display: block; padding: 14px 16px; border-radius: 12px;
      text-decoration: none; font-weight: 700; }}
    .open {{ color: white; background: #1D6F42; margin-bottom: 12px; }}
    #launch-status {{ display: none; margin: -10px 0 16px; color: #1D6F42;
      font-size: 13px; font-weight: 600; }}
    .stores {{ display: flex; gap: 10px; }}
    .stores a {{ flex: 1; color: #1D6F42; background: #ecfdf5; font-size: 13px; }}
    small {{ display: block; margin-top: 18px; color: #94a3b8; line-height: 1.4; }}
  </style>
</head>
<body><main>
  <div class="icon">📝</div>
  <h1>School form</h1>
  <p>Open {app_title} to complete this form. You may need to sign in with your school account.</p>
  <p id="launch-status" aria-live="polite"></p>
  <a class="open" id="open-pamais" href="{app_uri}">Open form in {app_title}</a>
  <div class="stores">
    <a href="{app_store}">App Store</a>
    <a href="{play_store}">Google Play</a>
  </div>
  <small>If the app does not open automatically, install {app_title} and tap the button again.</small>
</main>{launch_script}</body></html>""")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Simple root that could also be a template, but keeping existing logic for now
    return JSONResponse(
        content={
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
            "environment": settings.environment,
        }
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request):
    """Serve the Privacy Policy HTML page (branded from deployment env)."""
    return templates.TemplateResponse(
        "privacy.html",
        _legal_page_context(request),
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    """Serve the Terms of Service HTML page (branded from deployment env)."""
    return templates.TemplateResponse(
        "terms.html",
        _legal_page_context(request),
    )


def _legal_page_context(request: Request) -> dict:
    """Build privacy/terms template vars entirely from deployment settings."""
    from datetime import datetime, timezone

    phone = (settings.support_phone or "").strip()
    telegram = (settings.support_telegram_url or "").strip()
    telegram_label = ""
    if telegram:
        telegram_label = telegram.rstrip("/").rsplit("/", 1)[-1]
        if telegram_label and not telegram_label.startswith("@"):
            telegram_label = f"@{telegram_label}"
    phone_tel = "".join(ch for ch in phone if ch.isdigit() or ch == "+")

    base = (settings.public_api_base_url or "").strip().rstrip("/")
    effective = (settings.legal_effective_date or "").strip()
    if not effective:
        effective = datetime.now(timezone.utc).strftime("%B %Y")

    return {
        "request": request,
        "app_name": settings.legal_app_name,
        "app_short_name": settings.mobile_app_title,
        "app_version": settings.app_version,
        "effective_date": effective,
        "support_phone": phone,
        "support_phone_tel": phone_tel or phone,
        "support_telegram_url": telegram,
        "support_telegram_label": telegram_label or telegram,
        "privacy_url": f"{base}/privacy" if base else "/privacy",
        "terms_url": f"{base}/terms" if base else "/terms",
        "google_sign_in_enabled": bool((settings.google_client_id or "").strip()),
        "ai_chat_enabled": bool((settings.deepseek_api_key or "").strip()),
        "firebase_enabled": bool((settings.firebase_project_id or "").strip()),
    }

@app.get("/health")
async def health_check():
    """
    Deep health check that verifies database connectivity.
    """
    try:
        # Check database connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db_status = "disconnected"
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "detail": str(e)
                if settings.is_development
                else "Database connection failed",
            },
        )

    return {
        "status": "healthy",
        "database": db_status,
        "timestamp": time.time(),
        "version": settings.app_version,
        "environment": settings.environment,
    }


@app.get("/metrics")
async def metrics():
    """Basic metrics endpoint for monitoring"""
    pool = engine.pool
    return {
        "active_connections": getattr(pool, "size", lambda: 0)()
        if hasattr(pool, "size")
        else 0,
        "checked_out_connections": getattr(pool, "checkedout", lambda: 0)()
        if hasattr(pool, "checkedout")
        else 0,
        "overflow_connections": getattr(pool, "overflow", lambda: 0)()
        if hasattr(pool, "overflow")
        else 0,
        "checked_in_connections": getattr(pool, "checkedin", lambda: 0)()
        if hasattr(pool, "checkedin")
        else 0,
    }


@app.get("/app/download", include_in_schema=False)
async def app_download_smart_link(request: Request):
    """
    One marketing URL for QR codes: mobile browsers are redirected to the correct
    store; desktop gets a simple page with both store links.
    """
    play_store = settings.play_store_url
    app_store = settings.app_store_url or play_store
    app_title = settings.mobile_app_title
    app_name = settings.legal_app_name
    ua = (request.headers.get("user-agent") or "").lower()
    if any(s in ua for s in ("iphone", "ipad", "ipod")):
        return RedirectResponse(app_store, status_code=302)
    if "android" in ua:
        return RedirectResponse(play_store, status_code=302)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Download {app_title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(145deg, #0f172a, #1e293b);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      max-width: 400px;
      width: 100%;
      background: rgba(30, 41, 59, 0.85);
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 20px;
      padding: 28px;
      text-align: center;
    }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    p {{ color: #94a3b8; font-size: 14px; line-height: 1.5; margin-bottom: 22px; }}
    a {{
      display: block;
      width: 100%;
      padding: 14px 18px;
      border-radius: 12px;
      font-weight: 600;
      text-decoration: none;
      margin-bottom: 12px;
      font-size: 15px;
    }}
    .ios {{
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      color: #fff;
    }}
    .android {{
      background: rgba(34, 197, 94, 0.15);
      color: #4ade80;
      border: 1px solid rgba(74, 222, 128, 0.35);
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Download {app_name}</h1>
    <p>Scan the poster QR on your phone to open the right store automatically. On desktop, pick your platform:</p>
    <a class="ios" href="{app_store}">Download on the App Store</a>
    <a class="android" href="{play_store}">Get it on Google Play</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/app/smart-download", include_in_schema=False)
async def app_smart_download(request: Request, android: str, ios: str):
    """
    Custom smart link for QR codes.
    One QR encodes a single URL, but this endpoint can redirect to different
    store links depending on the device (iOS vs Android).
    """

    def _validate_http_url(raw: str) -> str:
        url = (raw or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL")
        if len(url) > 2048:
            raise ValueError("URL too long")
        return url

    try:
        android_url = _validate_http_url(android)
        ios_url = _validate_http_url(ios)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid android/ios URL. Use http/https only."},
        )

    ua = (request.headers.get("user-agent") or "").lower()
    if any(s in ua for s in ("iphone", "ipad", "ipod")):
        return RedirectResponse(ios_url, status_code=302)
    if "android" in ua:
        return RedirectResponse(android_url, status_code=302)

    # Desktop fallback: show both buttons.
    android_esc = html_lib.escape(android_url, quote=True)
    ios_esc = html_lib.escape(ios_url, quote=True)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Download PAMAIS</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(145deg, #0f172a, #1e293b);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      max-width: 420px;
      width: 100%;
      background: rgba(30, 41, 59, 0.85);
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 20px;
      padding: 28px;
      text-align: center;
    }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    p {{ color: #94a3b8; font-size: 14px; line-height: 1.5; margin-bottom: 22px; }}
    a {{
      display: block;
      width: 100%;
      padding: 14px 18px;
      border-radius: 12px;
      font-weight: 600;
      text-decoration: none;
      margin-bottom: 12px;
      font-size: 15px;
    }}
    .ios {{
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      color: #fff;
    }}
    .android {{
      background: rgba(34, 197, 94, 0.15);
      color: #4ade80;
      border: 1px solid rgba(74, 222, 128, 0.35);
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Download</h1>
    <p>Pick your platform:</p>
    <a class="ios" href="{ios_esc}" target="_blank" rel="noopener noreferrer">App Store</a>
    <a class="android" href="{android_esc}" target="_blank" rel="noopener noreferrer">Google Play</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


@app.post("/app/short-links", include_in_schema=False)
async def create_short_link(payload: dict, request: Request):
    """
    Create a short URL for custom iOS/Android store links so the QR stays clean.
    Returns: { "url": "https://<domain>/l/<code>", "code": "<code>" }
    """
    android = (payload.get("android") or "").strip()
    ios = (payload.get("ios") or "").strip()

    def _validate_http_url(raw: str) -> str:
        url = (raw or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL")
        if len(url) > 2048:
            raise ValueError("URL too long")
        return url

    try:
        android_url = _validate_http_url(android)
        ios_url = _validate_http_url(ios)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid android/ios URL. Use http/https only."},
        )

    # Create a short unique code
    db = SessionLocal()
    try:
        for _ in range(6):
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:10]
            exists = (
                db.query(SmartDownloadLink).filter(SmartDownloadLink.code == code).first()
            )
            if exists:
                continue
            link = SmartDownloadLink(code=code, android_url=android_url, ios_url=ios_url)
            db.add(link)
            db.commit()
            db.refresh(link)
            base = str(request.base_url).rstrip("/")
            return {"code": code, "url": f"{base}/l/{code}"}
    finally:
        db.close()

    return JSONResponse(status_code=500, content={"error": "Failed to create short link"})


@app.get("/l/{code}", include_in_schema=False)
async def resolve_short_link(code: str, request: Request):
    """
    Resolve a short link and redirect based on device.
    """
    db = SessionLocal()
    try:
        link = db.query(SmartDownloadLink).filter(SmartDownloadLink.code == code).first()
    finally:
        db.close()

    if not link:
        return HTMLResponse(content="Link not found", status_code=404)

    ua = (request.headers.get("user-agent") or "").lower()
    if any(s in ua for s in ("iphone", "ipad", "ipod")):
        return RedirectResponse(link.ios_url, status_code=302)
    if "android" in ua:
        return RedirectResponse(link.android_url, status_code=302)

    android_esc = html_lib.escape(link.android_url, quote=True)
    ios_esc = html_lib.escape(link.ios_url, quote=True)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Download</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(145deg, #0f172a, #1e293b);
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}
    .card {{
      max-width: 420px;
      width: 100%;
      background: rgba(30, 41, 59, 0.85);
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 20px;
      padding: 28px;
      text-align: center;
    }}
    h1 {{ font-size: 22px; margin-bottom: 8px; }}
    p {{ color: #94a3b8; font-size: 14px; line-height: 1.5; margin-bottom: 22px; }}
    a {{
      display: block;
      width: 100%;
      padding: 14px 18px;
      border-radius: 12px;
      font-weight: 600;
      text-decoration: none;
      margin-bottom: 12px;
      font-size: 15px;
    }}
    .ios {{
      background: linear-gradient(135deg, #6366f1, #8b5cf6);
      color: #fff;
    }}
    .android {{
      background: rgba(34, 197, 94, 0.15);
      color: #4ade80;
      border: 1px solid rgba(74, 222, 128, 0.35);
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Download</h1>
    <p>Pick your platform:</p>
    <a class="ios" href="{ios_esc}" target="_blank" rel="noopener noreferrer">App Store</a>
    <a class="android" href="{android_esc}" target="_blank" rel="noopener noreferrer">Google Play</a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=settings.is_development
    )


# =============================================================
# 🪪 PUBLIC EMPLOYEE PORTFOLIO ROUTE
# Accessible directly via QR code scan: https://{host}/portfolio/{identifier}
# =============================================================
@app.get("/portfolio/{identifier}", response_class=HTMLResponse, include_in_schema=False)
async def employee_portfolio_page(identifier: str, request: Request):
    from .services.portfolio_html_service import render_portfolio_html, render_not_found_html
    from .models import User, Department, Position, Branch, SystemSettings

    db = SessionLocal()
    try:
        ident = identifier.strip()
        filter_cond = (User.uniqueId == ident)

        if ident.isdigit():
            filter_cond = filter_cond | (User.id == int(ident))
        elif "-" in ident:
            parts = ident.split("-")
            if parts[-1].isdigit():
                filter_cond = filter_cond | (User.id == int(parts[-1]))

        user = db.query(User).filter(filter_cond).first()
        if not user:
            return HTMLResponse(content=render_not_found_html(ident), status_code=404)

        # Privacy Protection: If accessed via numeric ID (e.g. 19) or department code (e.g. ITD-0019),
        # immediately redirect to the employee's random uniqueId so users cannot guess other employees' URLs!
        if user.uniqueId and ident != user.uniqueId:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"/portfolio/{user.uniqueId}", status_code=307)

        dept = db.query(Department).filter(Department.id == user.departmentId).first() if user.departmentId else None
        pos = db.query(Position).filter(Position.id == user.positionId).first() if user.positionId else None
        branch = db.query(Branch).filter(Branch.id == user.workplace).first() if user.workplace else None
        settings = db.query(SystemSettings).first()

        dept_code = getattr(dept, "code", "EMP") or "EMP"
        emp_code = f"{dept_code}-{user.id:04d}"

        photo_url = user.image if user.image else ""
        if photo_url and not photo_url.startswith(("http://", "https://", "data:")):
            photo_url = photo_url.lstrip("/")
            photo_url = f"{str(request.base_url).rstrip('/')}/{photo_url}"

        school_kh = getattr(branch, "app_display_name", None) or getattr(settings, "enterpriseName", None) or "សាលាអន្តរជាតិ ប៉ាម៉ា"
        school_en = getattr(branch, "branch_name", None) or getattr(settings, "system_name", None) or "PAMA International School"
        school_logo = getattr(branch, "image_header_path", None) or getattr(branch, "image_header", None) or ""
        if school_logo and not school_logo.startswith(("http://", "https://", "data:")):
            school_logo = f"{str(request.base_url).rstrip('/')}/{school_logo.lstrip('/')}"

        data = {
            "id": user.id,
            "uniqueId": user.uniqueId or emp_code,
            "employeeId": emp_code,
            "cardNo": emp_code,
            "khmerName": user.kName,
            "latinName": user.eName,
            "positionKhmer": getattr(pos, "translate", None) or getattr(pos, "position", None),
            "positionLatin": getattr(pos, "position", None),
            "departmentKhmer": getattr(dept, "translate", None) or getattr(dept, "department", None),
            "departmentLatin": getattr(dept, "department", None),
            "branchName": getattr(branch, "branch_name", None) or "Main Campus",
            "gender": user.gender,
            "genderLatin": "Female" if user.gender in ["ស្រី", "Female"] else "Male",
            "dob": str(user.dob) if user.dob else None,
            "nationality": user.nationality,
            "religion": user.religion,
            "phone": user.phone,
            "email": user.email,
            "telegram": user.telegramId,
            "address": f"{user.village or ''} {user.commune or ''} {user.district or ''} {user.province or ''}".strip(),
            "pAddress": f"{user.pVillage or ''} {user.pCommune or ''} {user.pDistrict or ''} {user.pProvince or ''}".strip(),
            "identityNumber": user.identityNumber,
            "startWork": str(user.startWork) if user.startWork else None,
            "education": user.education,
            "photoUrl": photo_url,
            "schoolNameKhmer": school_kh,
            "schoolNameLatin": school_en,
            "schoolLogo": school_logo,
            "schoolPhone": "012/093 746046",
            "schoolWebsite": str(request.base_url).rstrip('/'),
            "directorName": getattr(branch, "director_kName", None) or "PHON Hoklaim",
        }

        return HTMLResponse(content=render_portfolio_html(data), status_code=200)
    finally:
        db.close()


# =============================================================
# 🔗 FRAME SLUG CATCH-ALL ROUTE
# Must be registered LAST so it does not shadow /api/*, /health, etc.
# When a user opens https://pamais.duckdns.org/{slug} in a browser,
# this returns a landing page that:
#   - Immediately tries to open the PAMAIS app via Universal / App Link
#   - Shows a fallback "Open in App" button if auto-open fails
#   - Displays the frame name so the user knows what they clicked
# =============================================================
@app.get("/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def frame_slug_landing(slug: str, request: Request):
    from .models.profile_frame import ProfileFrame as PF
    db = SessionLocal()
    try:
        frame = db.query(PF).filter(PF.slug == slug, PF.is_active == True).first()
    finally:
        db.close()

    if not frame:
        return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Frame Not Found – PAMAIS</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a; color: #e2e8f0; display: flex;
            align-items: center; justify-content: center; min-height: 100vh; padding: 24px; }}
    .card {{ background: #1e293b; border-radius: 20px; padding: 40px 32px;
             max-width: 400px; width: 100%; text-align: center; border: 1px solid #334155; }}
    h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 8px; color: #f8fafc; }}
    p {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size:48px;margin-bottom:16px;">🔍</div>
    <h1>Frame Not Found</h1>
    <p>The link <strong>/{slug}</strong> does not exist or has been removed.</p>
  </div>
</body>
</html>""", status_code=404)

    frame_title = frame.title or "Custom Frame"
    app_link = f"https://pamais.duckdns.org/{slug}"
    fallback_url = f"https://pamais.duckdns.org/{slug}?fb=1"
    fallback_encoded = fallback_url.replace(":", "%3A").replace("/", "%2F").replace("?", "%3F").replace("=", "%3D")
    android_intent = (
        f"intent://pamais.duckdns.org/{slug}"
        f"#Intent;scheme=https;package=com.pamais.edu.kh;"
        f"S.browser_fallback_url={fallback_encoded};end"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <title>{frame_title} – PAMAIS</title>
  <meta name="apple-itunes-app" content="app-id=6759542788, app-argument={app_link}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{
      font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
      min-height:100vh;display:flex;align-items:center;justify-content:center;
      padding:20px;background:#080810;overflow:hidden;
    }}
    .bg{{position:fixed;inset:0;z-index:0}}
    .blob{{position:absolute;border-radius:50%;filter:blur(90px);opacity:.3;
      animation:float 7s ease-in-out infinite alternate}}
    .b1{{width:500px;height:500px;background:#4f46e5;top:-150px;left:-120px;animation-delay:0s}}
    .b2{{width:380px;height:380px;background:#7c3aed;bottom:-100px;right:-80px;animation-delay:2.5s}}
    .b3{{width:220px;height:220px;background:#0ea5e9;top:40%;left:55%;animation-delay:5s}}
    @keyframes float{{from{{transform:scale(1) translateY(0)}}to{{transform:scale(1.12) translateY(-20px)}}}}
    .card{{
      position:relative;z-index:1;
      background:rgba(10,11,25,.88);
      backdrop-filter:blur(28px);-webkit-backdrop-filter:blur(28px);
      border:1px solid rgba(255,255,255,.07);
      border-radius:28px;padding:44px 32px 36px;
      max-width:380px;width:100%;text-align:center;
      box-shadow:0 40px 80px rgba(0,0,0,.7),0 0 0 1px rgba(255,255,255,.03) inset;
    }}
    .icon{{
      width:84px;height:84px;margin:0 auto 20px;
      background:linear-gradient(135deg,#6366f1,#8b5cf6);
      border-radius:24px;display:flex;align-items:center;justify-content:center;
      font-size:40px;box-shadow:0 14px 36px rgba(99,102,241,.5);
    }}
    .badge{{
      display:inline-flex;align-items:center;gap:5px;
      background:rgba(99,102,241,.12);color:#a5b4fc;
      font-size:10px;font-weight:700;letter-spacing:.1em;
      padding:5px 14px;border-radius:999px;margin-bottom:20px;
      border:1px solid rgba(99,102,241,.22);text-transform:uppercase;
    }}
    h1{{font-size:22px;font-weight:800;color:#f1f5f9;line-height:1.3;margin-bottom:10px}}
    .subtitle{{color:#64748b;font-size:14px;line-height:1.65;margin-bottom:30px}}
    /* Opening state */
    #state{{margin-bottom:26px;display:none}}
    .ring{{
      width:54px;height:54px;margin:0 auto 14px;
      border:3px solid rgba(99,102,241,.18);border-top-color:#6366f1;
      border-radius:50%;animation:spin .75s linear infinite;
    }}
    @keyframes spin{{to{{transform:rotate(360deg)}}}}
    #state p{{color:#a5b4fc;font-size:15px;font-weight:600}}
    #state small{{color:#475569;font-size:12px;display:block;margin-top:5px}}
    /* Button */
    #btn{{
      display:flex;align-items:center;justify-content:center;gap:10px;
      width:100%;padding:17px 24px;
      background:linear-gradient(135deg,#6366f1,#8b5cf6);
      color:#fff;font-size:16px;font-weight:700;
      border-radius:16px;border:none;cursor:pointer;text-decoration:none;
      box-shadow:0 10px 28px rgba(99,102,241,.45);
      transition:transform .15s,box-shadow .15s,opacity .15s;margin-bottom:14px;
    }}
    #btn:hover{{transform:translateY(-1px);box-shadow:0 14px 36px rgba(99,102,241,.55)}}
    #btn:active{{transform:scale(.97);opacity:.9}}
    .or{{display:flex;align-items:center;gap:10px;color:#1e293b;font-size:12px;margin-bottom:14px}}
    .or::before,.or::after{{content:'';flex:1;height:1px;background:rgba(255,255,255,.06)}}
    .hint{{color:#334155;font-size:12px;line-height:1.5}}
    .hint a{{color:#6366f1;text-decoration:none}}
  </style>
</head>
<body>
  <div class="bg"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div></div>
  <div class="card">
    <div class="icon">🎨</div>
    <div class="badge">✦ PAMAIS Profile Frame</div>
    <h1>{frame_title}</h1>
    <p class="subtitle" id="sub">Opening PAMAIS app for you…</p>

    <div id="state">
      <div class="ring"></div>
      <p>Launching PAMAIS</p>
      <small>Just a moment…</small>
    </div>

    <a id="btn" href="{app_link}"><span>📱</span><span id="bl">Open in PAMAIS</span></a>
    <div class="or">or</div>
    <p class="hint">Don't have the app?
      <a href="https://play.google.com/store/apps/details?id=com.pamais.edu.kh">Get it on Play Store</a>
    </p>
  </div>

  <script>
    var isAndroid=/Android/i.test(navigator.userAgent);
    var isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent);
    var isFallback=window.location.search.indexOf('fb=1')!==-1;
    var scheme="pamais://{slug}";
    var intent="{android_intent}";
    var btn=document.getElementById('btn');
    var state=document.getElementById('state');
    var sub=document.getElementById('sub');
    var bl=document.getElementById('bl');

    function opening(){{
      state.style.display='block';
      sub.style.display='none';
      btn.style.background='rgba(99,102,241,.12)';
      btn.style.boxShadow='none';
      btn.style.border='1px solid rgba(99,102,241,.25)';
      btn.style.color='#a5b4fc';
      bl.textContent='Not opening? Tap here';
    }}
    function fallback(){{
      state.style.display='none';
      sub.style.display='block';
      sub.textContent='Tap below to open this profile frame in the PAMAIS app.';
      btn.style.background='linear-gradient(135deg,#6366f1,#8b5cf6)';
      btn.style.boxShadow='0 10px 28px rgba(99,102,241,.45)';
      btn.style.border='none';
      btn.style.color='#fff';
      bl.textContent='Open in PAMAIS';
    }}
    btn.addEventListener('click',function(){{fallback();}});

    if(isFallback){{
      fallback();
      btn.href=scheme;
    }}else if(isAndroid){{
      opening();
      btn.href=intent;
      window.location.href=intent;
      setTimeout(fallback,2500);
    }}else if(isIOS){{
      opening();
      btn.href=scheme;
      window.location.href=scheme;
      setTimeout(fallback,2500);
    }}else{{
      sub.textContent='Open this link on your mobile device to launch the PAMAIS app.';
      btn.href="{app_link}";
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200)
