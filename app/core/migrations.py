"""
Run database migrations on startup.
"""
import logging
import re
from sqlalchemy import inspect, text
from ..core.database import engine

logger = logging.getLogger(__name__)


def run_migrations():
    """Run pending database migrations."""
    print("Running database migrations...")
    
    with engine.connect() as connection:
        # Migration 1: Add user_type column to message_group_members
        _migrate_user_type_column(connection)
        
        # Migration 2: Create message_group_bans table
        _migrate_group_bans_table(connection)
        
        # Migration 3: Create message_group_settings table
        _migrate_group_settings_table(connection)
        
        # Migration 4: Add moderation fields to group_messages
        _migrate_message_moderation_fields(connection)
        
        # Migration 5: Add description to message_groups
        _migrate_group_description(connection)
        
        # Migration 6: Create pinned messages table
        _migrate_pinned_messages_table(connection)
        
        # Migration 7: Create message reactions table
        
        # Migration 8: Add timestamps to all tables
        _migrate_add_timestamps(connection)
        _migrate_message_reactions_table(connection)
        _migrate_settings_security_toggles(connection)
        _migrate_parent_token_version(connection)

        # Migration 9: Make user image nullable
        _migrate_user_image_nullable(connection)

        # Migration 10: Create users_resource table
        _migrate_create_user_resources_table(connection)

        # Migration 11: Create users_social_links table
        _migrate_create_user_social_links_table(connection)

        # Migration 13: Cleanup unused snake_case columns from users table
        _migrate_cleanup_snake_case_columns(connection)

        # Migration 14: Make student image nullable
        _migrate_student_image_nullable(connection)
        
        # Migration 15: Create parent_student_link_requests table
        _migrate_parent_student_link_requests_table(connection)

        # Migration 16: Add social media URLs to settings
        _migrate_settings_social_links(connection)

        # Migration 17: Add social media URLs to academic programs
        _migrate_academic_program_social_links(connection)

        # Migration 18: Create dynamic forms tables
        _migrate_dynamic_forms_tables(connection)

        # Migration 19: Form enhancements (multiple submissions & number field)
        _migrate_dynamic_form_enhancements(connection)

        # Migration 20: Form cover image & display-only fields
        _migrate_form_image_and_display_only(connection)

        # Migration 21: Add start_date and end_date to forms
        _migrate_form_schedule_dates(connection)
        
        # Migration 22: Add earned_percentage to attendance records
        _migrate_earned_percentage_column(connection)

        # Migration 23: Add multilingual fields to school_overviews
        _migrate_school_overview_translations(connection)

        # Migration 24: Add token_version to users for JWT revocation
        _migrate_user_token_version(connection)

        # Migration 25: Add group_image column to message_groups
        _migrate_group_image(connection)

        # Migration 26: pickup custom announcement URL per student
        _migrate_student_pickup_audio_url(connection)

        # Migration 27: branch pickup geofence radius + student extra pickup branches
        _migrate_pickup_branch_radius_and_student_extra_branches(connection)

        # Migration 28: branch map lat/lng as DOUBLE (full GPS precision; FLOAT/DECIMAL truncated)
        _migrate_branch_map_coordinates_double(connection)

        # Migration 29: default pickup geofence radius 100 m (NULL → 100, new rows DEFAULT 100)
        _migrate_default_pickup_radius_100(connection)

        # Migration 30: staff must start pickup calling session; parents see status until enabled
        _migrate_pickup_calling_enabled(connection)

        # Migration 31: attribute each pickup request to a branch (for admin queue per campus)
        _migrate_pickup_requests_pickup_branch_id(connection)

        # Migration 32: hall calling on/off per campus (parents see status only for their branch)
        _migrate_pickup_branch_calling_table(connection)

        # Migration 33: school documents table (admin PDF docs in School Community section)
        _migrate_school_documents_table(connection)

        # Migration 34: drop deprecated location columns from attendance_records
        _migrate_drop_deprecated_attendance_location_columns(connection)

        # Migration 35: Add sort_order and deleted_at to profile_frames
        _migrate_profile_frames(connection)

        # Migration 36: Add background_url to background_cert (Flutter image-URL field)
        _migrate_background_cert_url(connection)

        # Migration 37: Add snapshot columns to demo_cert + signature/stamp URL columns to branch
        _migrate_cert_snapshot_and_branch_assets(connection)

        # Migration 38: Convert snapshot_cert_date from VARCHAR to DATE
        _migrate_cert_date_to_date(connection)

        # Migration 39: School marketplace — listing condition filter
        _migrate_market_listing_condition(connection)
        _migrate_market_store_cover(connection)

        # Migration 40: School marketplace — bilingual category names + icon_key
        _migrate_market_category_i18n(connection)

        # Migration 41: Leave requests replacement note
        _migrate_leave_replacement_note(connection)

        # Migration 42: Manual staff leave audit + explicit creator permission
        _migrate_manual_staff_leave(connection)

        # Migration 43: Audited policy deductions from staff leave balances
        _migrate_leave_balance_adjustments(connection)

        # Migration 44: Wait after checkout before starting another session
        _migrate_attendance_session_transition_wait(connection)

        # Migration 45: Marketplace renewals and seller broadcast quota log
        _migrate_market_listing_renewals(connection)

        # Migration 46: One primary phone per employee for attendance
        _migrate_attendance_primary_devices(connection)

        # Migration 47: Independent read-only access to all leave requests
        _migrate_leave_approver_view_all(connection)

        # Migration 48: Server-controlled marketplace welcome dialog
        _migrate_market_settings(connection)

        # Migration 49: Rate-limited approver reminders from read-only reviewers
        _migrate_leave_review_reminders(connection)

        # Migration 50: Backward-compatible primary video media for news
        _migrate_news_video_media(connection)

        # Migration 51: Preserve YouTube source when mirroring to first-party MP4
        _migrate_news_video_original_url(connection)

        # Migration 52: Repair notification preference defaults/backfill caused
        # by generic schema sync adding NOT NULL booleans without DEFAULT 1.
        _migrate_device_notification_preferences(connection)

        # Migration 53: move every legacy binary value to StorageService and
        # convert the database column to a URL/path string.
        _migrate_all_binary_media_to_resources(connection)

        # Migration 54: schema formerly created on demand by the desktop app.
        # Schema ownership now stays entirely on the API/server side.
        _migrate_desktop_owned_tables(connection)

        # Migration 55: default avatar resources are UI fallbacks, not student
        # photos.  Clear the two known migration-era placeholder resource paths
        # so clients can accurately flag students without a real image.
        _migrate_student_placeholder_image_paths(connection)

        # Migration 56: make the shared Flutter/desktop certificate URL fields
        # authoritative after migration 53 converted legacy media to paths.
        _migrate_certificate_resource_url_fields(connection)

        # Migration 57: temporary compatibility for already-released desktop
        # builds that still require students.image to be a database byte array.
        # Current API clients continue to receive StorageService resource URLs.
        _migrate_legacy_student_image_blob_compatibility(connection)

        # Migration 58: class-bound homework publishing. Schedules now retain
        # their shift so parent recipients can be resolved without crossing
        # otherwise-identical morning/afternoon classes.
        _migrate_learning_homework(connection)

        # Migration 59: per-subject grading composition and subject attendance.
        _migrate_subject_grading(connection)

        # Migration 60: bound automatic attendance marks to an explicit period.
        _migrate_subject_grading_attendance_period(connection)

        # Migration 61: monthly leave cap. Days over the cap stay granted but
        # cost no annual allowance and are reported as unpaid.
        _migrate_leave_monthly_cap(connection)

        # Migration 62: make Telegram OTP resend deterministic and bind a
        # verified phone to one short-lived, one-use registration proof.
        _migrate_telegram_otp_security(connection)

    print("Database migrations completed.")


def _migrate_telegram_otp_security(connection):
    """Upgrade the raw Telegram OTP table used by the public auth flow."""
    try:
        inspector = inspect(connection)
        if "telegram_otp_sessions" not in inspector.get_table_names():
            id_definition = (
                "INT AUTO_INCREMENT PRIMARY KEY"
                if connection.dialect.name == "mysql"
                else "INTEGER PRIMARY KEY AUTOINCREMENT"
            )
            connection.execute(
                text(
                    f"""
                    CREATE TABLE telegram_otp_sessions (
                        id {id_definition},
                        phone VARCHAR(50) NOT NULL,
                        phone_code_hash VARCHAR(255) NOT NULL,
                        session_string TEXT NULL,
                        expires_at DATETIME NOT NULL,
                        used_at DATETIME NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        registration_token_hash VARCHAR(64) NULL,
                        registration_expires_at DATETIME NULL,
                        registration_used_at DATETIME NULL
                    )
                    """
                )
            )
            connection.commit()
            inspector = inspect(connection)

        columns = {
            column["name"]
            for column in inspector.get_columns("telegram_otp_sessions")
        }
        additions = {
            "registration_token_hash": "VARCHAR(64) NULL",
            "registration_expires_at": "DATETIME NULL",
            "registration_used_at": "DATETIME NULL",
        }
        for column_name, definition in additions.items():
            if column_name not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE telegram_otp_sessions "
                        f"ADD COLUMN {column_name} {definition}"
                    )
                )

        # Historical schema only had a non-unique phone index, so its MySQL
        # ON DUPLICATE KEY clause inserted a new row on every resend. Keep the
        # latest row for each phone before adding the intended unique key.
        indexes = inspector.get_indexes("telegram_otp_sessions")
        unique_constraints = inspector.get_unique_constraints(
            "telegram_otp_sessions"
        )
        phone_is_unique = any(
            item.get("unique") and item.get("column_names") == ["phone"]
            for item in indexes
        ) or any(
            item.get("column_names") == ["phone"]
            for item in unique_constraints
        )
        if not phone_is_unique:
            if connection.dialect.name == "mysql":
                connection.execute(
                    text(
                        """
                        DELETE older
                        FROM telegram_otp_sessions AS older
                        JOIN telegram_otp_sessions AS newer
                          ON newer.phone = older.phone
                         AND newer.id > older.id
                        """
                    )
                )
            else:
                connection.execute(
                    text(
                        """
                        DELETE FROM telegram_otp_sessions
                        WHERE id NOT IN (
                            SELECT MAX(id)
                            FROM telegram_otp_sessions
                            GROUP BY phone
                        )
                        """
                    )
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_telegram_otp_sessions_phone "
                    "ON telegram_otp_sessions(phone)"
                )
            )

        refreshed_indexes = inspect(connection).get_indexes(
            "telegram_otp_sessions"
        )
        if not any(
            item.get("name") == "idx_tos_registration_token"
            for item in refreshed_indexes
        ):
            connection.execute(
                text(
                    "CREATE INDEX idx_tos_registration_token "
                    "ON telegram_otp_sessions(registration_token_hash)"
                )
            )
        connection.commit()
        print("  ✓ Telegram OTP security schema ready")
    except Exception as exc:
        connection.rollback()
        print(f"  ✗ Telegram OTP security migration error: {exc}")
        raise


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quoted_identifier(value):
    if not _SAFE_IDENTIFIER_RE.match(str(value)):
        raise ValueError(f"Unsafe database identifier: {value}")
    return f"`{value}`"


def _resource_extension(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif", "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if data.startswith(b"%PDF"):
        return ".pdf", "application/pdf"
    return ".bin", "application/octet-stream"


def _existing_resource_text(data):
    try:
        value = data.decode("utf-8").strip()
    except (UnicodeDecodeError, AttributeError):
        return None
    if not value or "\x00" in value or len(value) > 1000:
        return None
    if value.startswith(("http://", "https://", "/uploads/", "uploads/")):
        return value
    return None


_STUDENT_PLACEHOLDER_RESOURCE_FILENAMES = (
    "20540f6d70b83c50118327c1905bdebec2050e8fc2c72d66316675fd8c4b9459.jpg",
    "35211a0a93fcce0c523b6e12e6f2138cad4eac39978044339b9ef2b8bd723f75.jpg",
)


def _migrate_student_placeholder_image_paths(connection):
    """Clear resource paths that are exact copies of the built-in avatars.

    These content-addressed files were created by the legacy binary-to-resource
    migration when no real student photo had been selected.  The desktop keeps
    rendering its local gender-specific placeholder, while a NULL database
    value now accurately represents that the student has no uploaded photo.
    """
    try:
        parameters = {
            f"placeholder_{index}": f"%/{filename}"
            for index, filename in enumerate(_STUDENT_PLACEHOLDER_RESOURCE_FILENAMES)
        }
        conditions = " OR ".join(
            f"LOWER(image) LIKE :placeholder_{index}"
            for index in range(len(_STUDENT_PLACEHOLDER_RESOURCE_FILENAMES))
        )
        result = connection.execute(text(f"""
            UPDATE students
            SET image = NULL
            WHERE image IS NOT NULL AND ({conditions})
        """), parameters)
        connection.commit()
        if result.rowcount:
            print(f"  ✓ Cleared {result.rowcount} default student avatar resource path(s)")
    except Exception as exc:
        print(f"  ✗ Student placeholder image migration error: {exc}")
        connection.rollback()
        raise


def _migrate_certificate_resource_url_fields(connection):
    """Backfill shared certificate URL fields from migrated compatibility paths.

    Migration 53 converts legacy binary values to resource paths in their
    original columns. Flutter already reads the dedicated URL fields, and the
    desktop now does the same. Copy only recognized resource paths into empty
    URL fields so the operation is safe and idempotent.
    """
    mappings = (
        ("background_cert", "background_url", "background_image"),
        ("branch", "signature_url", "director_signature"),
        ("branch", "stamp_url", "stamp"),
    )

    try:
        for table_name, target_column, source_column in mappings:
            table_sql = _quoted_identifier(table_name)
            target_sql = _quoted_identifier(target_column)
            source_sql = _quoted_identifier(source_column)
            result = connection.execute(text(f"""
                UPDATE {table_sql}
                SET {target_sql} = TRIM({source_sql})
                WHERE ({target_sql} IS NULL OR TRIM({target_sql}) = '')
                  AND {source_sql} IS NOT NULL
                  AND TRIM({source_sql}) <> ''
                  AND (
                    LOWER(TRIM({source_sql})) LIKE 'http://%'
                    OR LOWER(TRIM({source_sql})) LIKE 'https://%'
                    OR LOWER(TRIM({source_sql})) LIKE '/uploads/%'
                    OR LOWER(TRIM({source_sql})) LIKE 'uploads/%'
                  )
            """))
            if result.rowcount:
                print(
                    f"  ✓ Backfilled {result.rowcount} "
                    f"{table_name}.{target_column} resource path(s)"
                )
        connection.commit()
    except Exception as exc:
        print(f"  ✗ Certificate resource URL migration error: {exc}")
        connection.rollback()
        raise


def _migrate_all_binary_media_to_resources(connection):
    """Move all MySQL binary columns to durable URL/path resources.

    Columns are discovered from information_schema so an obscure legacy media
    field cannot remain unnoticed. The operation is idempotent: converted
    VARCHAR columns are absent from the next discovery query.
    """
    import hashlib

    from ..services.storage_service import StorageService

    binary_columns = connection.execute(text("""
        SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND DATA_TYPE IN (
            'tinyblob', 'blob', 'mediumblob', 'longblob', 'binary', 'varbinary'
          )
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """)).fetchall()

    for table_name, column_name, is_nullable in binary_columns:
        table_sql = _quoted_identifier(table_name)
        column_sql = _quoted_identifier(column_name)
        print(f"  - Migrating binary media {table_name}.{column_name} to resources...")

        primary_keys = connection.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
        """), {"table_name": table_name}).scalars().all()
        for key in primary_keys:
            _quoted_identifier(key)

        selected_columns = [*primary_keys, column_name]
        select_sql = ", ".join(_quoted_identifier(name) for name in selected_columns)
        rows = connection.execute(text(
            f"SELECT {select_sql} FROM {table_sql} "
            f"WHERE {column_sql} IS NOT NULL AND OCTET_LENGTH({column_sql}) > 0"
        )).mappings().all()

        for row in rows:
            raw_value = row[column_name]
            if isinstance(raw_value, memoryview):
                raw_value = raw_value.tobytes()
            if isinstance(raw_value, str):
                resource_url = raw_value
                original_value = raw_value.encode("utf-8")
            else:
                original_value = bytes(raw_value)
                resource_url = _existing_resource_text(original_value)

            if not resource_url:
                extension, content_type = _resource_extension(original_value)
                digest = hashlib.sha256(original_value).hexdigest()
                resource_url = StorageService.upload_file(
                    original_value,
                    f"desktop-migration/{table_name}/{column_name}",
                    f"{digest}{extension}",
                    content_type,
                )
            if not resource_url:
                raise RuntimeError(
                    f"Could not store resource for {table_name}.{column_name}; "
                    "the database column was not converted"
                )

            if primary_keys:
                where_sql = " AND ".join(
                    f"{_quoted_identifier(key)} = :pk_{index}"
                    for index, key in enumerate(primary_keys)
                )
                parameters = {
                    f"pk_{index}": row[key]
                    for index, key in enumerate(primary_keys)
                }
            else:
                # Rare legacy tables without a primary key are updated one
                # matching row at a time. Repeated identical values are safe.
                where_sql = f"{column_sql} = :legacy_binary_value LIMIT 1"
                parameters = {"legacy_binary_value": original_value}
            parameters["resource_url"] = resource_url
            connection.execute(
                text(
                    f"UPDATE {table_sql} SET {column_sql} = :resource_url "
                    f"WHERE {where_sql}"
                ),
                parameters,
            )

        null_sql = "NULL" if str(is_nullable).upper() == "YES" else "NOT NULL"
        connection.execute(text(
            f"ALTER TABLE {table_sql} MODIFY COLUMN {column_sql} "
            f"VARCHAR(1000) {null_sql}"
        ))
        connection.commit()
        print(f"  ✓ {table_name}.{column_name} is URL-backed")


def _migrate_legacy_student_image_blob_compatibility(connection):
    """Migrate legacy student image BLOBs to file URL resource paths (VARCHAR).

    Stores avatar paths in `users_resource.avatar` and `students.image` as VARCHAR(255),
    ensuring lightweight database performance and URL-based media handling.
    """
    from ..services.legacy_student_image import (
        publish_legacy_student_image,
        resource_text_from_bytes,
    )

    column = connection.execute(text("""
        SELECT DATA_TYPE, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'students'
          AND COLUMN_NAME = 'image'
        LIMIT 1
    """)).first()
    if column is None:
        return

    data_type = str(column[0] or "").lower()
    binary_types = {"tinyblob", "blob", "mediumblob", "longblob", "binary", "varbinary"}

    if data_type in binary_types:
        rows = connection.execute(text("""
            SELECT s.id, s.image, s.updated_at, ur.avatar, ur.updated_at
            FROM students s
            LEFT JOIN users_resource ur
              ON ur.user_id = s.id AND ur.user_type = 'student'
            WHERE s.image IS NOT NULL AND OCTET_LENGTH(s.image) > 0
            ORDER BY s.id
        """)).fetchall()

        prepared = []
        for student_id, raw_value, student_updated_at, avatar_url, avatar_updated_at in rows:
            if isinstance(raw_value, memoryview):
                raw_value = raw_value.tobytes()
            if isinstance(raw_value, str):
                resource_url = raw_value.strip()
            else:
                existing_bytes = bytes(raw_value)
                resource_url = resource_text_from_bytes(existing_bytes)
                if not resource_url:
                    try:
                        resource_url = publish_legacy_student_image(existing_bytes)
                    except Exception:
                        resource_url = None
            if not resource_url and avatar_url:
                resource_url = str(avatar_url).strip()
            prepared.append((int(student_id), resource_url))

        # Modify column to VARCHAR(255)
        connection.execute(text(
            "ALTER TABLE `students` MODIFY COLUMN `image` VARCHAR(255) NULL"
        ))

        for student_id, resource_url in prepared:
            if resource_url:
                connection.execute(
                    text("UPDATE students SET image = :image WHERE id = :student_id"),
                    {"image": resource_url, "student_id": student_id},
                )
                connection.execute(text("""
                    INSERT INTO users_resource (
                        user_id, user_type, avatar, cover_focus_y,
                        status, created_at, updated_at
                    ) VALUES (
                        :student_id, 'student', :resource_url, 0,
                        1, NOW(), NOW()
                    )
                    ON DUPLICATE KEY UPDATE
                        avatar = VALUES(avatar),
                        status = 1,
                        updated_at = NOW()
                """), {"student_id": student_id, "resource_url": resource_url})
            else:
                connection.execute(
                    text("UPDATE students SET image = NULL WHERE id = :student_id"),
                    {"student_id": student_id},
                )

        connection.commit()
        print(
            f"  ✓ students.image migrated from BLOB to VARCHAR(255) URL paths; "
            f"processed {len(prepared)} student photo(s)"
        )


def _migrate_desktop_owned_tables(connection):
    """Create server-owned tables that legacy desktop builds created locally."""

    statements = (
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INT NOT NULL AUTO_INCREMENT,
            username VARCHAR(255) NOT NULL,
            computer_name VARCHAR(255) NULL,
            computer_user_name VARCHAR(255) NULL,
            computer_unique_id VARCHAR(255) NULL,
            mac_address VARCHAR(255) NULL,
            motherboard_serial VARCHAR(255) NULL,
            processor_id VARCHAR(255) NULL,
            windows_product_id VARCHAR(255) NULL,
            operating_system TEXT NULL,
            user_name VARCHAR(255) NULL,
            app_version VARCHAR(50) NULL,
            edition VARCHAR(50) NULL,
            is_success BOOLEAN NOT NULL,
            failure_reason TEXT NULL,
            login_time DATETIME NOT NULL,
            ip_address VARCHAR(45) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_login_attempt_username (username),
            INDEX idx_login_attempt_time (login_time),
            INDEX idx_login_attempt_computer (computer_unique_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS student_activity_logs (
            id INT NOT NULL AUTO_INCREMENT,
            student_id INT NOT NULL,
            action_type VARCHAR(50) NOT NULL,
            action_label VARCHAR(255) NOT NULL,
            description TEXT NULL,
            performed_by INT NOT NULL DEFAULT 0,
            performed_by_name VARCHAR(255) NULL,
            source_form VARCHAR(100) NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            INDEX idx_student_activity_student (student_id),
            INDEX idx_student_activity_action (action_type),
            INDEX idx_student_activity_created (created_at),
            INDEX idx_student_activity_user (performed_by)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS attendance_log (
            id INT NOT NULL AUTO_INCREMENT,
            student_id INT NOT NULL,
            scan_time DATETIME NOT NULL,
            scan_type VARCHAR(20) NOT NULL DEFAULT 'arrival',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_attendance_log_student_time (student_id, scan_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS medal_points_setup (
            program_name VARCHAR(255) NOT NULL,
            gold_pts DOUBLE NOT NULL DEFAULT 0,
            silver_pts DOUBLE NOT NULL DEFAULT 0,
            bronze_pts DOUBLE NOT NULL DEFAULT 0,
            diamond_pts DOUBLE NOT NULL DEFAULT 0,
            participation_pts DOUBLE NOT NULL DEFAULT 0,
            PRIMARY KEY (program_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_calculate_sign_subjects (
            id INT NOT NULL AUTO_INCREMENT,
            exam_calculate_sign_id INT NOT NULL,
            subject_id INT NOT NULL,
            created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_sign_subject_sign (exam_calculate_sign_id),
            INDEX idx_sign_subject_subject (subject_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS marks_system_subjects (
            id INT NOT NULL AUTO_INCREMENT,
            marks_system_id INT NOT NULL,
            subject_id INT NOT NULL,
            created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uq_marks_system_subject (
                marks_system_id,
                subject_id
            ),
            INDEX idx_marks_system_subject_system (marks_system_id),
            INDEX idx_marks_system_subject_subject (subject_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS background_cards (
            id INT NOT NULL AUTO_INCREMENT,
            front_image VARCHAR(1000) NULL,
            back_image VARCHAR(1000) NULL,
            card_model VARCHAR(255) NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    )

    try:
        for statement in statements:
            connection.execute(text(statement))

        # Older installations may already have login_attempts without fields
        # added by later desktop builds.
        for column_name, definition in (
            ("app_version", "VARCHAR(50) NULL"),
            ("edition", "VARCHAR(50) NULL"),
        ):
            exists = connection.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'login_attempts'
                  AND COLUMN_NAME = :column_name
            """), {"column_name": column_name}).scalar()
            if int(exists or 0) == 0:
                connection.execute(text(
                    f"ALTER TABLE login_attempts ADD COLUMN "
                    f"{_quoted_identifier(column_name)} {definition}"
                ))

        exam_table_exists = connection.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'exam_calculate_sign'
        """)).scalar()
        if int(exam_table_exists or 0) > 0:
            for column_name, definition in (
                ("exam_type", "VARCHAR(50) NULL"),
                ("sign_code", "VARCHAR(10) NULL"),
            ):
                exists = connection.execute(text("""
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'exam_calculate_sign'
                      AND COLUMN_NAME = :column_name
                """), {"column_name": column_name}).scalar()
                if int(exists or 0) == 0:
                    connection.execute(text(
                        f"ALTER TABLE exam_calculate_sign ADD COLUMN "
                        f"{_quoted_identifier(column_name)} {definition}"
                    ))

            connection.execute(text("""
                UPDATE exam_calculate_sign
                SET exam_type = CASE
                    WHEN sign_code = 'YEAR' THEN 'yearly'
                    WHEN sign_code IN ('RSEM1', 'RSEM2') THEN 'semester'
                    ELSE 'input'
                END
                WHERE exam_type IS NULL OR exam_type = ''
            """))

        connection.commit()
        print("  Desktop support tables are server-owned and ready")
    except Exception as exc:
        connection.rollback()
        print(f"  Desktop support table migration error: {exc}")
        raise


_DEVICE_NOTIFICATION_PREFERENCE_COLUMNS = (
    "notifications_enabled",
    "attendance_notifications_enabled",
    "leave_notifications_enabled",
    "message_notifications_enabled",
    "announcement_notifications_enabled",
    "market_notifications_enabled",
    "other_notifications_enabled",
)


def _notification_default_is_enabled(value) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "b'1'"}


def _migrate_device_notification_preferences(connection):
    """Make notification opt-out explicit and repair the one-time zero backfill."""
    try:
        rows = connection.execute(text("""
            SELECT COLUMN_NAME, COLUMN_DEFAULT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'device_tokens'
              AND COLUMN_NAME IN (
                'notifications_enabled',
                'attendance_notifications_enabled',
                'leave_notifications_enabled',
                'message_notifications_enabled',
                'announcement_notifications_enabled',
                'market_notifications_enabled',
                'other_notifications_enabled'
              )
        """)).fetchall()
        defaults = {str(row[0]): row[1] for row in rows}
        original_columns = [
            column
            for column in _DEVICE_NOTIFICATION_PREFERENCE_COLUMNS
            if column in defaults
        ]
        broken_default_columns = [
            column
            for column in original_columns
            if not _notification_default_is_enabled(defaults[column])
        ]

        # MySQL populated existing rows with zero when the generic schema sync
        # added these NOT NULL columns without a default. Repair only the exact
        # all-off signature, and only while the broken schema default proves
        # this installation is affected. Once defaults are fixed this never
        # runs again, preserving later intentional opt-outs.
        if original_columns and broken_default_columns:
            all_off = " AND ".join(
                f"COALESCE(`{column}`, 0) = 0" for column in original_columns
            )
            set_enabled = ", ".join(
                f"`{column}` = 1" for column in original_columns
            )
            result = connection.execute(
                text(f"UPDATE device_tokens SET {set_enabled} WHERE {all_off}")
            )
            logger.warning(
                "Re-enabled %s device token row(s) corrupted by missing "
                "notification preference defaults",
                int(result.rowcount or 0),
            )
            connection.commit()

        for column in _DEVICE_NOTIFICATION_PREFERENCE_COLUMNS:
            if column not in defaults:
                connection.execute(text(
                    "ALTER TABLE device_tokens "
                    f"ADD COLUMN `{column}` BOOLEAN NOT NULL DEFAULT 1"
                ))
            elif not _notification_default_is_enabled(defaults[column]):
                connection.execute(text(
                    "ALTER TABLE device_tokens "
                    f"MODIFY COLUMN `{column}` BOOLEAN NOT NULL DEFAULT 1"
                ))
        connection.commit()
        print("  ✓ Device notification preference defaults ready")
    except Exception as e:
        print(f"  ✗ Device notification preference migration error: {e}")
        connection.rollback()
        raise


def _migrate_news_video_original_url(connection):
    """Keep the source URL so a mirrored video can be rolled back safely."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'news'
              AND COLUMN_NAME = 'video_original_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding news.video_original_url...")
            connection.execute(text(
                "ALTER TABLE news ADD COLUMN video_original_url VARCHAR(1000) NULL"
            ))
        connection.commit()
        print("  ✓ News video source rollback field ready")
    except Exception as e:
        print(f"  ✗ News video source migration error: {e}")
        connection.rollback()
        raise


def _migrate_news_video_media(connection):
    """Add nullable video metadata while preserving every image-only news row."""
    try:
        additions = (
            ("media_type", "VARCHAR(20) NOT NULL DEFAULT 'image'"),
            ("video_source", "VARCHAR(20) NULL"),
            ("video_url", "VARCHAR(1000) NULL"),
            ("video_thumbnail_url", "VARCHAR(1000) NULL"),
            ("video_duration_seconds", "INT NULL"),
        )
        for column_name, definition in additions:
            result = connection.execute(text(f"""
                SELECT COUNT(*) AS c
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'news'
                  AND COLUMN_NAME = '{column_name}'
            """))
            if result.fetchone()[0] == 0:
                print(f"  - Adding news.{column_name}...")
                connection.execute(text(
                    f"ALTER TABLE news ADD COLUMN {column_name} {definition}"
                ))
        connection.execute(text("""
            UPDATE news SET media_type = 'image'
            WHERE media_type IS NULL OR media_type NOT IN ('image', 'video')
        """))
        connection.commit()
        print("  ✓ News video media fields ready")
    except Exception as e:
        print(f"  ✗ News video media migration error: {e}")
        connection.rollback()
        raise


def _migrate_leave_review_reminders(connection):
    """Persist per-request reminder cooldown state across API restarts."""
    try:
        additions = (
            ("review_reminder_count", "INT NOT NULL DEFAULT 0"),
            ("last_review_reminder_at", "DATETIME NULL"),
        )
        for column_name, definition in additions:
            result = connection.execute(text(f"""
                SELECT COUNT(*) AS c
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'leave_requests'
                  AND COLUMN_NAME = '{column_name}'
            """))
            if result.fetchone()[0] == 0:
                print(f"  - Adding leave_requests.{column_name}...")
                connection.execute(text(
                    "ALTER TABLE leave_requests "
                    f"ADD COLUMN {column_name} {definition}"
                ))
        connection.execute(text("""
            UPDATE leave_requests
            SET review_reminder_count = 0
            WHERE review_reminder_count IS NULL
        """))
        connection.commit()
        print("  ✓ Leave review reminder cooldown fields ready")
    except Exception as e:
        print(f"  ✗ Leave review reminder migration error: {e}")
        connection.rollback()
        raise


def _migrate_market_settings(connection):
    """Create the singleton marketplace experience settings table."""
    try:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS market_settings (
                id INT NOT NULL DEFAULT 1,
                welcome_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                welcome_skip_seconds INT NOT NULL DEFAULT 30,
                welcome_version INT NOT NULL DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            )
        """))
        connection.commit()
        print("  ✓ market_settings table ready")
    except Exception as e:
        print(f"  ✗ market_settings migration error: {e}")


def _migrate_background_cert_url(connection):
    """
    Add `background_url` VARCHAR(500) column to the existing `background_cert` table.

    The legacy desktop app stored background images as binary data in that table.
    All clients now use image URLs instead. This column holds the
    URL returned by StorageService after the admin uploads via the API.
    We also make the legacy `background_image` column NULLable.

    Idempotent: skipped silently if the column already exists.
    """
    try:
        # Keep the compatibility column nullable and URL-only.  Do not recreate
        # the former binary type on an existing installation.
        result = connection.execute(text("""
            SELECT IS_NULLABLE, DATA_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'background_image'
        """))
        row = result.fetchone()
        if row and (row[0].upper() == 'NO' or row[1].lower() != 'varchar'):
            print("  - Making background_image nullable and URL-only...")
            connection.execute(text("""
                ALTER TABLE background_cert
                MODIFY COLUMN background_image VARCHAR(1000) NULL
            """))
            connection.commit()
            print("  ✓ background_cert.background_image is now nullable")

        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'background_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding background_url to background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                ADD COLUMN background_url VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ background_cert.background_url column added")
        else:
            print("  ✓ background_cert.background_url already exists")

        # Note: We previously added `grade_group_id` INT NULL. We now drop it.
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'grade_group_id'
        """))
        if result.fetchone()[0] > 0:
            print("  - Dropping grade_group_id from background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                DROP COLUMN grade_group_id
            """))
            connection.commit()
            print("  ✓ background_cert.grade_group_id column dropped")
            
        # Add grade_group_ids (JSON string array)
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'grade_group_ids'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding grade_group_ids to background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                ADD COLUMN grade_group_ids VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ background_cert.grade_group_ids column added")
            
        # Add grade_ids (JSON string array)
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'grade_ids'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding grade_ids to background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                ADD COLUMN grade_ids VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ background_cert.grade_ids column added")
            
        # Also ensure created_at exists
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'created_at'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding created_at to background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                ADD COLUMN created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP
            """))
            connection.commit()
            print("  ✓ background_cert.created_at column added")
            
        # Also ensure updated_at exists
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'background_cert'
              AND COLUMN_NAME  = 'updated_at'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding updated_at to background_cert...")
            connection.execute(text("""
                ALTER TABLE background_cert
                ADD COLUMN updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            """))
            connection.commit()
            print("  ✓ background_cert.updated_at column added")
            
    except Exception as e:
        print(f"  ✗ background_cert migration error: {e}")
        connection.rollback()


def _migrate_cert_snapshot_and_branch_assets(connection):
    """
    Migration 37:
    (a) Add 6 snapshot columns to `demo_cert` so each issued certificate
        freezes the exact assets used at generation time.
    (b) Add `signature_url` and `stamp_url` columns to `branch` so the
        Flutter API can serve proper image URLs instead of legacy BLOBs.

    Idempotent: each column is skipped if it already exists.
    """
    # ── (a) demo_cert snapshot columns ───────────────────────────────────
    snapshot_cols = [
        ("snapshot_background_url", "VARCHAR(500) NULL"),
        ("snapshot_signature_url",  "VARCHAR(500) NULL"),
        ("snapshot_stamp_url",      "VARCHAR(500) NULL"),
        ("snapshot_cert_date",      "DATE NULL"),
        ("snapshot_director_kname", "VARCHAR(200) NULL"),
        ("snapshot_director_ename", "VARCHAR(200) NULL"),
        ("snapshot_principal_label", "VARCHAR(200) NULL"),
        ("snapshot_address_prefix", "VARCHAR(200) NULL"),
        ("snapshot_date_format", "VARCHAR(50) NULL"),
    ]
    for col_name, col_def in snapshot_cols:
        try:
            r = connection.execute(text("""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME   = 'demo_cert'
                  AND COLUMN_NAME  = :col
            """), {"col": col_name})
            if r.fetchone()[0] == 0:
                print(f"  - Adding demo_cert.{col_name}...")
                connection.execute(text(
                    f"ALTER TABLE demo_cert ADD COLUMN `{col_name}` {col_def}"
                ))
                connection.commit()
                print(f"  ✓ demo_cert.{col_name} added")
            else:
                print(f"  ✓ demo_cert.{col_name} already exists")
        except Exception as e:
            print(f"  ✗ demo_cert.{col_name} migration error: {e}")
            connection.rollback()

    # ── (b) branch asset URL columns ─────────────────────────────────────
    # `director_signature_path` and `stamp_path` already exist in the branch
    # table — those store relative file paths.  We add new dedicated URL
    # columns so the admin can set full image URLs independently.
    branch_cols = [
        ("signature_url", "VARCHAR(500) NULL"),
        ("stamp_url",     "VARCHAR(500) NULL"),
    ]
    for col_name, col_def in branch_cols:
        try:
            r = connection.execute(text("""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME   = 'branch'
                  AND COLUMN_NAME  = :col
            """), {"col": col_name})
            if r.fetchone()[0] == 0:
                print(f"  - Adding branch.{col_name}...")
                connection.execute(text(
                    f"ALTER TABLE branch ADD COLUMN `{col_name}` {col_def}"
                ))
                connection.commit()
                print(f"  ✓ branch.{col_name} added")
            else:
                print(f"  ✓ branch.{col_name} already exists")
        except Exception as e:
            print(f"  ✗ branch.{col_name} migration error: {e}")
            connection.rollback()


def _migrate_cert_date_to_date(connection):
    """
    Change snapshot_cert_date from VARCHAR to DATE,
    since address prefix was split into its own column.
    """
    try:
        # First, NULL out any existing strings that aren't YYYY-MM-DD
        connection.execute(text("""
            UPDATE demo_cert 
            SET snapshot_cert_date = NULL 
            WHERE snapshot_cert_date IS NOT NULL 
              AND snapshot_cert_date NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        """))
        
        # Then alter the column to DATE
        connection.execute(text("ALTER TABLE demo_cert MODIFY COLUMN snapshot_cert_date DATE NULL"))
        connection.commit()
        print("  ✓ demo_cert.snapshot_cert_date type is DATE")
    except Exception as e:
        print(f"  ! Failed to alter snapshot_cert_date: {e}")


def _migrate_profile_frames(connection):
    try:
        # ── Step 0: Ensure the table exists (fresh live-server installs) ──────────
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS profile_frames (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                title       VARCHAR(255) NULL,
                image_url   VARCHAR(500) NOT NULL,
                is_active   TINYINT(1)  NOT NULL DEFAULT 1,
                sort_order  INT         NOT NULL DEFAULT 0,
                status      VARCHAR(20) NOT NULL DEFAULT 'published',
                publish_at  DATETIME    NULL,
                expires_at  DATETIME    NULL,
                user_id     INT         NULL,
                is_public   TINYINT(1)  NOT NULL DEFAULT 1,
                is_featured TINYINT(1)  NOT NULL DEFAULT 0,
                slug        VARCHAR(128) NULL,
                created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at  DATETIME    NULL,
                UNIQUE KEY uq_profile_frames_slug (slug),
                KEY idx_pf_user (user_id),
                KEY idx_pf_status (status, is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        # ── Step 1: Add any missing columns to older installs ─────────────────────
        for col, ddl in [
            ("sort_order",  "ALTER TABLE profile_frames ADD COLUMN sort_order INT NOT NULL DEFAULT 0"),
            ("deleted_at",  "ALTER TABLE profile_frames ADD COLUMN deleted_at DATETIME NULL"),
            ("status",      "ALTER TABLE profile_frames ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'published'"),
            ("publish_at",  "ALTER TABLE profile_frames ADD COLUMN publish_at DATETIME NULL"),
            ("expires_at",  "ALTER TABLE profile_frames ADD COLUMN expires_at DATETIME NULL"),
            ("user_id",     "ALTER TABLE profile_frames ADD COLUMN user_id INT NULL"),
            ("is_public",   "ALTER TABLE profile_frames ADD COLUMN is_public TINYINT(1) NOT NULL DEFAULT 1"),
            ("is_featured", "ALTER TABLE profile_frames ADD COLUMN is_featured TINYINT(1) NOT NULL DEFAULT 0"),
            ("slug",        "ALTER TABLE profile_frames ADD COLUMN slug VARCHAR(128) NULL UNIQUE"),
        ]:
            r = connection.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'profile_frames'
                  AND COLUMN_NAME = '{col}'
            """))
            if r.fetchone()[0] == 0:
                print(f"  - Adding {col} to profile_frames...")
                connection.execute(text(ddl))
                connection.commit()
                print(f"  ✓ {col} added to profile_frames")
            else:
                print(f"  ✓ profile_frames.{col} already exists")

        # ── Step 2: Ensure profile_frame_history table exists ─────────────────────
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS profile_frame_history (
                id                  INT AUTO_INCREMENT PRIMARY KEY,
                user_id             INT         NOT NULL,
                frame_id            INT         NULL,
                generated_image_url VARCHAR(500) NOT NULL,
                created_at          DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_pfh_user (user_id),
                KEY idx_pfh_frame (frame_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()
        print("  ✓ profile_frame_history table ready")

        # ── Step 3: Fix is_active/is_public/is_featured NULL defaults ─────────────
        # These columns were created without a DB-level default via SQLAlchemy
        # create_all. Existing NULL rows and future inserts should default to 1/0.
        for col, fix_ddl, backfill_val in [
            ("is_active",   "ALTER TABLE profile_frames MODIFY COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1",   1),
            ("is_public",   "ALTER TABLE profile_frames MODIFY COLUMN is_public TINYINT(1) NOT NULL DEFAULT 1",   1),
            ("is_featured", "ALTER TABLE profile_frames MODIFY COLUMN is_featured TINYINT(1) NOT NULL DEFAULT 0", 0),
        ]:
            try:
                # Backfill any existing NULLs first (required before NOT NULL)
                connection.execute(text(
                    f"UPDATE profile_frames SET {col} = {backfill_val} WHERE {col} IS NULL"
                ))
                connection.commit()
                connection.execute(text(fix_ddl))
                connection.commit()
                print(f"  ✓ profile_frames.{col} default fixed")
            except Exception:
                connection.rollback()

    except Exception as e:
        print(f"  ✗ profile_frames migration error: {e}")
        connection.rollback()



def _migrate_school_documents_table(connection):
    """Create school_documents table for admin-published PDF documents in School Community."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'school_documents'
        """))
        if result.fetchone()[0] == 0:
            print("  - Creating school_documents table...")
            connection.execute(text("""
                CREATE TABLE school_documents (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    title       VARCHAR(255)  NOT NULL,
                    title_km    VARCHAR(255)  NULL,
                    subtitle    VARCHAR(512)  NULL,
                    subtitle_km VARCHAR(512)  NULL,
                    icon_name   VARCHAR(64)   NOT NULL DEFAULT 'description',
                    pdf_url     VARCHAR(512)  NOT NULL,
                    target_audience VARCHAR(50) NOT NULL DEFAULT 'all',
                    is_active   TINYINT(1)    NOT NULL DEFAULT 1,
                    sort_order  INT           NOT NULL DEFAULT 0,
                    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at  DATETIME      NULL ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_sd_active_order (is_active, sort_order)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            print("  ✓ school_documents table created")
        else:
            print("  ✓ school_documents table already exists")
            # Ensure target_audience column exists on old deployments
            col = connection.execute(text("""
                SELECT COUNT(*) AS c
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'school_documents'
                  AND COLUMN_NAME = 'target_audience'
            """))
            if col.fetchone()[0] == 0:
                print("  - Adding target_audience to school_documents...")
                connection.execute(text("""
                    ALTER TABLE school_documents
                    ADD COLUMN target_audience VARCHAR(50) NOT NULL DEFAULT 'all'
                    AFTER pdf_url
                """))
                connection.commit()
                print("  ✓ target_audience added to school_documents")
    except Exception as e:
        print(f"  ✗ school_documents migration error: {e}")
        connection.rollback()


def _migrate_pickup_branch_calling_table(connection):
    """Pickup: staff hall-calling session is per (academic_id, branch_id), not global."""
    try:
        r = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'pickup_branch_calling'
        """))
        if r.fetchone()[0] == 0:
            print("  - Creating pickup_branch_calling...")
            connection.execute(text("""
                CREATE TABLE pickup_branch_calling (
                    academic_id INT NOT NULL,
                    branch_id INT NOT NULL,
                    calling_enabled TINYINT(1) NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (academic_id, branch_id),
                    KEY idx_pbc_academic (academic_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            print("  ✓ pickup_branch_calling created")
        else:
            print("  ✓ pickup_branch_calling already exists")
    except Exception as e:
        print(f"  ✗ pickup_branch_calling migration error: {e}")
        logger.exception("pickup_branch_calling migration failed")
        connection.rollback()


def _migrate_pickup_requests_pickup_branch_id(connection):
    """Pickup: branch this request is queued under (geofence match or student home branch)."""
    try:
        r = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'pickup_requests'
              AND COLUMN_NAME = 'pickup_branch_id'
        """))
        if r.fetchone()[0] == 0:
            print("  - Adding pickup_branch_id to pickup_requests...")
            connection.execute(text("""
                ALTER TABLE pickup_requests
                ADD COLUMN pickup_branch_id INT NULL
            """))
            connection.commit()
            connection.execute(text("""
                UPDATE pickup_requests pr
                INNER JOIN students s ON pr.student_id = s.id
                SET pr.pickup_branch_id = CAST(s.branch AS UNSIGNED)
                WHERE pr.pickup_branch_id IS NULL
                  AND s.branch IS NOT NULL
                  AND TRIM(s.branch) REGEXP '^[0-9]+$'
            """))
            connection.commit()
            print("  ✓ pickup_branch_id added and backfilled from students.branch")
        else:
            print("  ✓ pickup_requests.pickup_branch_id already exists")
    except Exception as e:
        print(f"  ✗ pickup_branch_id migration error: {e}")
        logger.exception("pickup_branch_id migration failed")
        connection.rollback()


def _migrate_pickup_calling_enabled(connection):
    """Add pickup_settings.calling_enabled — off until staff opens queue and confirms."""
    try:
        r = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'pickup_settings'
              AND COLUMN_NAME = 'calling_enabled'
        """))
        if r.fetchone()[0] == 0:
            print("  - Adding calling_enabled to pickup_settings...")
            connection.execute(text("""
                ALTER TABLE pickup_settings
                ADD COLUMN calling_enabled TINYINT(1) NOT NULL DEFAULT 0
            """))
            connection.commit()
            print("  ✓ calling_enabled added (default off until staff starts session)")
        else:
            print("  ✓ pickup_settings.calling_enabled already exists")
    except Exception as e:
        print(f"  ✗ pickup calling_enabled migration error: {e}")
        connection.rollback()


def _migrate_pickup_branch_radius_and_student_extra_branches(connection):
    """Pickup: optional geofence radius per branch; extra allowed branches per student (JSON)."""
    try:
        r = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'branch'
              AND COLUMN_NAME = 'pickup_radius_meters'
        """))
        if r.fetchone()[0] == 0:
            print("  - Adding pickup_radius_meters to branch...")
            connection.execute(text("""
                ALTER TABLE branch
                ADD COLUMN pickup_radius_meters DECIMAL(12, 2) NULL
            """))
            connection.commit()
            print("  ✓ pickup_radius_meters added to branch")
        else:
            print("  ✓ pickup_radius_meters on branch already exists")

        r2 = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'students'
              AND COLUMN_NAME = 'pickup_extra_branch_ids'
        """))
        if r2.fetchone()[0] == 0:
            print("  - Adding pickup_extra_branch_ids to students...")
            connection.execute(text("""
                ALTER TABLE students
                ADD COLUMN pickup_extra_branch_ids VARCHAR(512) NULL
            """))
            connection.commit()
            print("  ✓ pickup_extra_branch_ids added to students")
        else:
            print("  ✓ pickup_extra_branch_ids already exists")
    except Exception as e:
        print(f"  ✗ pickup branch/student migration error: {e}")
        connection.rollback()


def _migrate_branch_map_coordinates_double(connection):
    """
    MySQL FLOAT or DECIMAL(?,3) truncates coordinates (e.g. 10.1980112 → 10.198).
    Use DOUBLE for latitude/longitude like production mapping apps.
    """
    try:
        for col in ("map_latitude", "map_longitude"):
            row = connection.execute(
                text(
                    """
                    SELECT COLUMN_TYPE FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'branch'
                      AND COLUMN_NAME = :c
                    """
                ),
                {"c": col},
            ).fetchone()
            if not row:
                continue
            col_type = (row[0] or "").lower()
            if "double" in col_type:
                continue
            print(
                f"  - Widening branch.{col} to DOUBLE (was {row[0]!r}) for GPS precision..."
            )
            connection.execute(
                text(f"ALTER TABLE branch MODIFY COLUMN {col} DOUBLE NULL")
            )
            connection.commit()
            print(f"  ✓ branch.{col} is now DOUBLE")
    except Exception as e:
        print(f"  ✗ branch map coordinate precision migration: {e}")
        connection.rollback()


def _migrate_default_pickup_radius_100(connection):
    """
    Pickup geofence: default 100 m for new branches (MySQL DEFAULT 100).
    One-time backfill NULL → 100 so existing campuses get a radius without admin edits.
    After that, admins who clear radius (NULL) keep geofence off — we must not re-run the
    backfill on every API start.
    """
    try:
        r = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'branch'
                  AND COLUMN_NAME = 'pickup_radius_meters'
                """
            )
        )
        if r.fetchone()[0] == 0:
            print("  ✓ pickup_radius_meters column missing; skip default-radius migration")
            return

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS _schema_patches (
                    patch_id VARCHAR(128) NOT NULL PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.commit()

        patch_id = "branch_pickup_radius_null_to_100_v1"
        already = connection.execute(
            text(
                "SELECT 1 FROM _schema_patches WHERE patch_id = :p LIMIT 1"
            ),
            {"p": patch_id},
        ).fetchone()
        if already is None:
            connection.execute(
                text(
                    """
                    UPDATE branch SET pickup_radius_meters = 100
                    WHERE pickup_radius_meters IS NULL
                    """
                )
            )
            connection.commit()
            connection.execute(
                text("INSERT INTO _schema_patches (patch_id) VALUES (:p)"),
                {"p": patch_id},
            )
            connection.commit()
            print("  ✓ One-time backfill: branch.pickup_radius_meters NULL → 100m")

        defrow = connection.execute(
            text(
                """
                SELECT COLUMN_DEFAULT FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'branch'
                  AND COLUMN_NAME = 'pickup_radius_meters'
                """
            )
        ).fetchone()
        need_alter = True
        if defrow and defrow[0] is not None:
            try:
                d = str(defrow[0]).strip().strip("'\"")
                if abs(float(d) - 100.0) < 1e-9:
                    need_alter = False
            except (TypeError, ValueError):
                pass
        if need_alter:
            connection.execute(
                text(
                    """
                    ALTER TABLE branch
                    MODIFY COLUMN pickup_radius_meters DECIMAL(12, 2) NULL DEFAULT 100
                    """
                )
            )
            connection.commit()
            print("  ✓ branch.pickup_radius_meters DEFAULT 100 for new rows")
        else:
            print("  ✓ branch.pickup_radius_meters DEFAULT 100 already set")
    except Exception as e:
        print(f"  ✗ default pickup radius migration: {e}")
        connection.rollback()


def _migrate_student_pickup_audio_url(connection):
    """Add pickup_audio_url to students for child-pickup voice announcements."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'students'
              AND COLUMN_NAME = 'pickup_audio_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding pickup_audio_url column to students...")
            connection.execute(text("""
                ALTER TABLE students
                ADD COLUMN pickup_audio_url VARCHAR(512) NULL
            """))
            connection.commit()
            print("  ✓ pickup_audio_url column added")
        else:
            print("  ✓ pickup_audio_url column already exists")
    except Exception as e:
        print(f"  ✗ pickup_audio_url migration error: {e}")
        connection.rollback()


def _migrate_group_image(connection):
    """Add group_image column to message_groups table."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_groups'
            AND COLUMN_NAME = 'group_image'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding group_image column to message_groups...")
            connection.execute(text("""
                ALTER TABLE message_groups
                ADD COLUMN group_image VARCHAR(255) NULL
            """))
            connection.commit()
            print("  ✓ group_image column added")
        else:
            print("  ✓ group_image column already exists")
    except Exception as e:
        print(f"  ✗ group_image migration error: {e}")
        connection.rollback()


def _migrate_earned_percentage_column(connection):
    """Add earned_percentage field to attendance_records table."""
    try:
        # Check if column exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'attendance_records'
            AND COLUMN_NAME = 'earned_percentage'
        """))
        
        column_exists = result.fetchone()[0] > 0
        
        if not column_exists:
            print("  - Adding earned_percentage field to attendance_records...")
            
            connection.execute(text("""
                ALTER TABLE attendance_records
                ADD COLUMN earned_percentage FLOAT DEFAULT 0
            """))
            connection.commit()
            
            print("  ✓ Earned percentage field added")
        else:
            print("  ✓ Earned percentage field already exists")
            
    except Exception as e:
        print(f"  ✗ earned_percentage migration error: {e}")
        connection.rollback()
        # Non-blocking


def _migrate_user_token_version(connection):
    """Add token_version column to users table for JWT revocation."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'users'
              AND COLUMN_NAME = 'token_version'
        """))
        column_exists = result.fetchone()[0] > 0

        if not column_exists:
            print("  - Adding token_version field to users...")
            connection.execute(text("""
                ALTER TABLE users
                ADD COLUMN token_version INT NOT NULL DEFAULT 1
            """))
            connection.commit()
            print("  ✓ token_version field added to users")
        else:
            print("  ✓ token_version field already exists on users")
    except Exception as e:
        print(f"  ✗ token_version migration error: {e}")
        connection.rollback()
        # Non-blocking



def _migrate_dynamic_forms_tables(connection):
    """Create all dynamic forms tables if they don't exist."""
    try:
        # forms
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS forms (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT NULL,
                target_role ENUM('all','parents','students','teachers') NOT NULL DEFAULT 'all',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_forms_active (is_active),
                INDEX idx_forms_role (target_role)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        # form_fields
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS form_fields (
                id INT AUTO_INCREMENT PRIMARY KEY,
                form_id INT NOT NULL,
                field_type ENUM('short_text','long_text','dropdown','checkboxes','radio',
                                'date','time','child_selector','image','file') NOT NULL,
                label VARCHAR(255) NOT NULL,
                description TEXT NULL,
                is_required BOOLEAN NOT NULL DEFAULT FALSE,
                `order` INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE,
                INDEX idx_fields_form (form_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        # form_field_options
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS form_field_options (
                id INT AUTO_INCREMENT PRIMARY KEY,
                field_id INT NOT NULL,
                label VARCHAR(255) NOT NULL,
                value VARCHAR(255) NOT NULL,
                `order` INT NOT NULL DEFAULT 0,
                FOREIGN KEY (field_id) REFERENCES form_fields(id) ON DELETE CASCADE,
                INDEX idx_options_field (field_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        # form_submissions
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS form_submissions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                form_id INT NOT NULL,
                user_id INT NOT NULL,
                user_type ENUM('all','parents','students','teachers') NOT NULL,
                submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (form_id) REFERENCES forms(id) ON DELETE CASCADE,
                INDEX idx_submissions_form (form_id),
                INDEX idx_submissions_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        # form_submission_values
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS form_submission_values (
                id INT AUTO_INCREMENT PRIMARY KEY,
                submission_id INT NOT NULL,
                field_id INT NOT NULL,
                value TEXT NULL,
                FOREIGN KEY (submission_id) REFERENCES form_submissions(id) ON DELETE CASCADE,
                FOREIGN KEY (field_id) REFERENCES form_fields(id) ON DELETE CASCADE,
                INDEX idx_values_submission (submission_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        connection.commit()

        print("  ✓ Dynamic forms tables ready")

    except Exception as e:
        print(f"  ✗ Dynamic forms migration error: {e}")
        connection.rollback()
        raise


def _migrate_dynamic_form_enhancements(connection):
    """Add allow_multiple_submissions to forms and 'number' to form_fields ENUM."""
    try:
        # Check if column exists
        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'forms'
            AND COLUMN_NAME = 'allow_multiple_submissions'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding allow_multiple_submissions to forms...")
            connection.execute(text("""
                ALTER TABLE forms
                ADD COLUMN allow_multiple_submissions BOOLEAN NOT NULL DEFAULT FALSE
            """))
            connection.commit()
            print("  ✓ Added allow_multiple_submissions")
        
        # Add image_url to form_fields
        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'form_fields'
            AND COLUMN_NAME = 'image_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding image_url to form_fields...")
            connection.execute(text("""
                ALTER TABLE form_fields
                ADD COLUMN image_url VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ Added image_url to form_fields")
        
        # Update ENUM type for form_fields
        print("  - Updating form_fields field_type ENUM to include 'number'...")
        connection.execute(text("""
            ALTER TABLE form_fields
            MODIFY COLUMN field_type ENUM('short_text','long_text','number','dropdown','checkboxes','radio',
                                          'date','time','child_selector','image','file') NOT NULL
        """))
        connection.commit()
        print("  ✓ Updated form_fields field_type ENUM")
    except Exception as e:
        print(f"  ✗ Dynamic form enhancements migration error: {e}")
        connection.rollback()
        raise

def _migrate_form_image_and_display_only(connection):
    """Add image_url to forms table and display_only to form_fields table."""
    try:
        # Add image_url to forms
        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'forms'
            AND COLUMN_NAME = 'image_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding image_url to forms...")
            connection.execute(text("""
                ALTER TABLE forms
                ADD COLUMN image_url VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ Added image_url to forms")
        else:
            print("  ✓ image_url already exists on forms")

        # Add display_only to form_fields
        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'form_fields'
            AND COLUMN_NAME = 'display_only'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding display_only to form_fields...")
            connection.execute(text("""
                ALTER TABLE form_fields
                ADD COLUMN display_only BOOLEAN NOT NULL DEFAULT FALSE
            """))
            connection.commit()
            print("  ✓ Added display_only to form_fields")
        else:
            print("  ✓ display_only already exists on form_fields")

    except Exception as e:
        print(f"  ✗ form image/display_only migration error: {e}")
        connection.rollback()
        raise


def _migrate_form_schedule_dates(connection):
    """Add start_date and end_date columns to the forms table."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'forms'
            AND COLUMN_NAME = 'start_date'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding start_date to forms...")
            connection.execute(text("""
                ALTER TABLE forms
                ADD COLUMN start_date DATETIME NULL
            """))
            connection.commit()
            print("  ✓ Added start_date")
        else:
            print("  ✓ start_date already exists on forms")

        result = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'forms'
            AND COLUMN_NAME = 'end_date'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding end_date to forms...")
            connection.execute(text("""
                ALTER TABLE forms
                ADD COLUMN end_date DATETIME NULL
            """))
            connection.commit()
            print("  ✓ Added end_date")
        else:
            print("  ✓ end_date already exists on forms")

    except Exception as e:
        print(f"  ✗ form schedule dates migration error: {e}")
        connection.rollback()
        raise


def _migrate_settings_social_links(connection):
    """Add social media URL columns to the settings table."""
    try:
        # Check existing columns
        result = connection.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'settings'
        """))
        existing_cols = {row[0] for row in result.fetchall()}
        
        new_cols = [
            'facebook_url',
            'telegram_url',
            'youtube_url',
            'instagram_url',
            'tiktok_url'
        ]
        
        for col in new_cols:
            if col not in existing_cols:
                print(f"  - Adding {col} to settings...")
                connection.execute(text(f"""
                    ALTER TABLE settings
                    ADD COLUMN {col} VARCHAR(255) NULL
                """))
                connection.commit()
                print(f"  ✓ Added {col}")
            else:
                print(f"  ✓ {col} already exists")
                
    except Exception as e:
        print(f"  ✗ error migrating settings social links: {e}")
        connection.rollback()
        raise


def _migrate_user_type_column(connection):
    """Add user_type column to message_group_members if it doesn't exist."""
    try:
        # Check if column exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_group_members' 
            AND COLUMN_NAME = 'user_type'
        """))
        
        column_exists = result.fetchone()[0] > 0
        
        if not column_exists:
            print("  - Adding user_type column to message_group_members...")
            
            # Add the column with default value
            connection.execute(text("""
                ALTER TABLE message_group_members 
                ADD COLUMN user_type ENUM('teacher', 'parent', 'student', 'employee') 
                NULL DEFAULT 'teacher'
            """))
            connection.commit()
            
            # Backfill: Mark parents by checking if user_id exists in parents table
            print("  - Backfilling user_type for existing members...")
            connection.execute(text("""
                UPDATE message_group_members mgm
                INNER JOIN parents p ON mgm.user_id = p.id
                LEFT JOIN users u ON mgm.user_id = u.id
                SET mgm.user_type = 'parent'
                WHERE u.id IS NULL AND mgm.user_type IS NULL
            """))
            connection.commit()
            
            # Set default for any remaining NULL values
            connection.execute(text("""
                UPDATE message_group_members 
                SET user_type = 'teacher' 
                WHERE user_type IS NULL
            """))
            connection.commit()
            
            # Make column NOT NULL
            connection.execute(text("""
                ALTER TABLE message_group_members 
                MODIFY COLUMN user_type ENUM('teacher', 'parent', 'student', 'employee') 
                NOT NULL DEFAULT 'teacher'
            """))
            connection.commit()
            
            print("  ✓ user_type migration completed")
        else:
            print("  ✓ user_type column already exists")
            
    except Exception as e:
        print(f"  ✗ user_type migration error: {e}")
        connection.rollback()
        raise


def _migrate_group_bans_table(connection):
    """Create message_group_bans table if it doesn't exist."""
    try:
        # Check if table exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_group_bans'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating message_group_bans table...")
            
            connection.execute(text("""
                CREATE TABLE message_group_bans (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id INT NOT NULL,
                    user_id INT NOT NULL,
                    user_type ENUM('teacher', 'parent', 'student', 'employee') NOT NULL,
                    banned_by INT NOT NULL,
                    reason VARCHAR(500),
                    banned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE,
                    INDEX idx_group_user (group_id, user_id),
                    INDEX idx_active (is_active),
                    INDEX idx_expires (expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            
            print("  ✓ message_group_bans table created")
        else:
            print("  ✓ message_group_bans table already exists")
            
    except Exception as e:
        print(f"  ✗ group_bans migration error: {e}")
        connection.rollback()
        raise


def _migrate_group_settings_table(connection):
    """Create message_group_settings table if it doesn't exist."""
    try:
        # Check if table exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_group_settings'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating message_group_settings table...")
            
            connection.execute(text("""
                CREATE TABLE message_group_settings (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id INT NOT NULL UNIQUE,
                    can_send_text BOOLEAN NOT NULL DEFAULT TRUE,
                    can_send_files BOOLEAN NOT NULL DEFAULT TRUE,
                    can_send_images BOOLEAN NOT NULL DEFAULT TRUE,
                    can_send_voice BOOLEAN NOT NULL DEFAULT TRUE,
                    only_admins_can_post BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            
            # Create default settings for existing groups
            print("  - Creating default settings for existing groups...")
            connection.execute(text("""
                INSERT INTO message_group_settings (group_id)
                SELECT id FROM message_groups
                WHERE id NOT IN (SELECT group_id FROM message_group_settings)
            """))
            connection.commit()
            
            print("  ✓ message_group_settings table created")
        else:
            print("  ✓ message_group_settings table already exists")
            
    except Exception as e:
        print(f"  ✗ group_settings migration error: {e}")
        connection.rollback()
        raise


def _migrate_message_moderation_fields(connection):
    """Add moderation fields to messages table (GroupMessage model)."""
    try:
        # Check if messages table exists (model __tablename__ = 'messages')
        table_result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'messages'
        """))
        if table_result.fetchone()[0] == 0:
            print("  ✓ messages table not found, skipping moderation migration")
            return
        # Check if deleted_by column exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'messages'
            AND COLUMN_NAME = 'deleted_by'
        """))
        
        deleted_by_exists = result.fetchone()[0] > 0
        
        if not deleted_by_exists:
            print("  - Adding moderation fields to messages...")
            
            connection.execute(text("""
                ALTER TABLE messages
                ADD COLUMN deleted_by INT NULL,
                ADD COLUMN deleted_at DATETIME NULL,
                ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
                ADD INDEX idx_hidden (is_hidden),
                ADD INDEX idx_deleted (deleted_at)
            """))
            connection.commit()
            
            print("  ✓ Message moderation fields added")
        else:
            print("  ✓ Message moderation fields already exist")
            
    except Exception as e:
        print(f"  ✗ message moderation migration error: {e}")
        connection.rollback()
        raise



def _migrate_group_description(connection):
    """Add description field to message_groups table."""
    try:
        # Check if description column exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_groups'
            AND COLUMN_NAME = 'description'
        """))
        
        description_exists = result.fetchone()[0] > 0
        
        if not description_exists:
            print("  - Adding description field to message_groups...")
            
            connection.execute(text("""
                ALTER TABLE message_groups
                ADD COLUMN description TEXT NULL
            """))
            connection.commit()
            
            print("  ✓ Group description field added")
        else:
            print("  ✓ Group description field already exists")
            
    except Exception as e:
        print(f"  ✗ group description migration error: {e}")
        connection.rollback()
        raise


def _migrate_pinned_messages_table(connection):
    """Create message_pinned table if it doesn't exist."""
    try:
        # Check if table exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_pinned'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating message_pinned table...")
            
            connection.execute(text("""
                CREATE TABLE message_pinned (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    group_id INT NOT NULL,
                    message_id INT NOT NULL,
                    pinned_by INT NOT NULL,
                    pinned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES message_groups(id) ON DELETE CASCADE,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    INDEX idx_group (group_id),
                    UNIQUE KEY unique_pinned_message (group_id, message_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            
            print("  ✓ message_pinned table created")
        else:
            print("  ✓ message_pinned table already exists")
            
    except Exception as e:
        print(f"  ✗ pinned messages migration error: {e}")
        connection.rollback()
        raise


def _migrate_message_reactions_table(connection):
    """Create message_reactions table if it doesn't exist."""
    try:
        # Check if table exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_reactions'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating message_reactions table...")
            
            connection.execute(text("""
                CREATE TABLE message_reactions (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    message_id INT NOT NULL,
                    user_id INT NOT NULL,
                    user_type VARCHAR(20) NOT NULL DEFAULT 'teacher',
                    reaction VARCHAR(10) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    INDEX idx_message (message_id),
                    UNIQUE KEY unique_user_reaction (message_id, user_id, user_type, reaction)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            
            print("  ✓ message_reactions table created")
        else:
            print("  ✓ message_reactions table already exists")

        _migrate_message_reactions_user_type(connection)

    except Exception as e:
        print(f"  ✗ message reactions migration error: {e}")
        connection.rollback()
        raise


def _migrate_message_reactions_user_type(connection):
    """Add message_reactions.user_type and backfill it.

    Without this column a reaction is identified by a bare user_id, which is
    ambiguous: parents, students and employees have independent ID sequences, so
    parent #57 could delete employee #57's reaction. Every other chat table
    already carries user_type.
    """
    try:
        has_column = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'message_reactions'
            AND COLUMN_NAME = 'user_type'
        """)).fetchone()[0] > 0

        if not has_column:
            print("  - Adding message_reactions.user_type...")
            connection.execute(text(
                "ALTER TABLE message_reactions "
                "ADD COLUMN user_type VARCHAR(20) NOT NULL DEFAULT 'teacher'"
            ))
            connection.commit()

            # Backfill from the reacting user's membership in that message's
            # group. Only rows with exactly one matching membership can be
            # resolved; anything ambiguous keeps the 'teacher' default and is
            # reported so it can be reviewed by hand.
            connection.execute(text("""
                UPDATE message_reactions r
                JOIN messages m ON m.id = r.message_id
                JOIN message_group_members mgm
                     ON mgm.group_id = m.group_id
                    AND mgm.user_id = r.user_id
                SET r.user_type = mgm.user_type
                WHERE (
                    SELECT COUNT(*) FROM message_group_members x
                    WHERE x.group_id = m.group_id AND x.user_id = r.user_id
                ) = 1
            """))
            connection.commit()

            unresolved = connection.execute(text("""
                SELECT COUNT(*) FROM message_reactions r
                JOIN messages m ON m.id = r.message_id
                WHERE (
                    SELECT COUNT(*) FROM message_group_members x
                    WHERE x.group_id = m.group_id AND x.user_id = r.user_id
                ) <> 1
            """)).fetchone()[0]
            if unresolved:
                print(
                    f"  ! {unresolved} reaction(s) could not be attributed to one "
                    "account and kept user_type='teacher' — review if needed"
                )

            # The old uniqueness key did not include user_type.
            try:
                connection.execute(text(
                    "ALTER TABLE message_reactions DROP INDEX unique_user_reaction"
                ))
                connection.execute(text(
                    "ALTER TABLE message_reactions "
                    "ADD UNIQUE KEY unique_user_reaction (message_id, user_id, user_type, reaction)"
                ))
                connection.commit()
            except Exception as e:
                print(f"  ! could not rebuild unique_user_reaction: {e}")
                connection.rollback()

            print("  ✓ message_reactions.user_type added and backfilled")
        else:
            print("  ✓ message_reactions.user_type already present")

    except Exception as e:
        print(f"  ✗ message_reactions user_type migration error: {e}")
        connection.rollback()
        raise


def _migrate_add_timestamps(connection):
    """Add created_at and updated_at to tables that are missing them."""
    try:
        # Tables that need timestamps
        tables_to_check = [
            'message_group_members',
            'message_group_bans',
            'message_pinned'
        ]
        
        for table in tables_to_check:
            # Check if created_at exists
            result = connection.execute(text(f"""
                SELECT COUNT(*) as count
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND COLUMN_NAME = 'created_at'
            """))
            
            created_at_exists = result.fetchone()[0] > 0
            
            if not created_at_exists:
                print(f"  - Adding created_at to {table}...")
                connection.execute(text(f"""
                    ALTER TABLE {table}
                    ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                """))
                connection.commit()
            
            # Check if updated_at exists
            result = connection.execute(text(f"""
                SELECT COUNT(*) as count
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = '{table}'
                AND COLUMN_NAME = 'updated_at'
            """))
            
            updated_at_exists = result.fetchone()[0] > 0
            
            if not updated_at_exists:
                print(f"  - Adding updated_at to {table}...")
                connection.execute(text(f"""
                    ALTER TABLE {table}
                    ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                """))
                connection.commit()
        
        print("  ✓ Timestamp columns added to all tables")
            
    except Exception as e:
        print(f"  ✗ Timestamp migration error: {e}")
        connection.rollback()
        raise


def _migrate_user_image_nullable(connection):
    """Make the user image URL column nullable and text-only."""
    try:
        # Check if column is already nullable
        result = connection.execute(text("""
            SELECT IS_NULLABLE, DATA_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'users'
            AND COLUMN_NAME = 'image'
        """))
        
        row = result.fetchone()
        if row:
            is_nullable = row[0] == 'YES'
            is_url_column = row[1].lower() == 'varchar'
            
            if not is_nullable or not is_url_column:
                print("  - Making user image column nullable and URL-only...")
                
                connection.execute(text("""
                    ALTER TABLE users
                    MODIFY COLUMN image VARCHAR(1000) NULL
                """))
                connection.commit()
                
                print("  ✓ User image column is now nullable")
            else:
                print("  - student image column already nullable.")
    except Exception as e:
        print(f"  - Error making student image column nullable: {e}: {e}")
        connection.rollback()
        # Don't raise error to avoid blocking startup if this minor migration fails
        # raise


def _migrate_parent_student_link_requests_table(connection):
    """Create parent_student_link_requests table if it doesn't exist."""
    try:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS parent_student_link_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                parent_id INT NOT NULL,
                student_id INT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """))
        connection.commit()
        print("  - parent_student_link_requests table structure ensured.")
    except Exception as e:
        print(f"  - Error creating parent_student_link_requests table: {e}")
        connection.rollback()
        # Don't raise error to avoid blocking startup if this minor migration fails
        # raise


def _migrate_create_user_resources_table(connection):
    """Create users_resource table if it doesn't exist."""
    try:
        # Check if table exists
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'users_resource'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating users_resource table...")
            
            connection.execute(text("""
                CREATE TABLE users_resource (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_id INT NOT NULL,
                    user_type ENUM('teacher', 'student', 'parent', 'employee') NOT NULL,
                    avatar VARCHAR(255) NULL,
                    cover_image VARCHAR(255) NULL,
                    cover_focus_y INT NOT NULL DEFAULT 0,
                    bio TEXT NULL,
                    status_message VARCHAR(255) NULL,
                    social_links JSON NULL,
                    website VARCHAR(255) NULL,
                    status INT NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_user_resource (user_id, user_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            
            print("  ✓ users_resource table created")
        else:
            print("  ✓ users_resource table already exists")
            
            # Check if avatar is BLOB or VARCHAR and migrate if needed
            # This handles the case where user ran the previous version of this migration
            col_result = connection.execute(text("""
                SELECT DATA_TYPE 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'users_resource' 
                AND COLUMN_NAME = 'avatar'
            """))
            row = col_result.fetchone()
            if row and 'blob' in row[0].lower():
                print("  - Converting users_resource.avatar to VARCHAR...")
                connection.execute(text("ALTER TABLE users_resource MODIFY COLUMN avatar VARCHAR(255) NULL"))
                connection.execute(text("ALTER TABLE users_resource MODIFY COLUMN cover_image VARCHAR(255) NULL"))
                connection.commit()
                print("  ✓ Converted users_resource blobs to paths")

            # Ensure cover_focus_y exists and has its canonical server default.
            # Some deployed schemas have the NOT NULL column without DEFAULT 0,
            # which breaks raw compatibility inserts that omit profile fields.
            focus_col = connection.execute(text("""
                SELECT IS_NULLABLE, COLUMN_DEFAULT
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'users_resource' 
                AND COLUMN_NAME = 'cover_focus_y'
            """))
            focus_row = focus_col.fetchone()
            if focus_row is None:
                print("  - Adding cover_focus_y to users_resource...")
                connection.execute(text("""
                    ALTER TABLE users_resource
                    ADD COLUMN cover_focus_y INT NOT NULL DEFAULT 0
                    AFTER cover_image
                """))
                connection.commit()
                print("  ✓ Added cover_focus_y to users_resource")
            elif (
                str(focus_row[0] or "").upper() != "NO"
                or str(focus_row[1]) != "0"
            ):
                print("  - Repairing users_resource.cover_focus_y default...")
                connection.execute(text("""
                    UPDATE users_resource
                    SET cover_focus_y = 0
                    WHERE cover_focus_y IS NULL
                """))
                connection.execute(text("""
                    ALTER TABLE users_resource
                    MODIFY COLUMN cover_focus_y INT NOT NULL DEFAULT 0
                """))
                connection.commit()
                print("  ✓ Repaired users_resource.cover_focus_y default")

            
    except Exception as e:
        print(f"  ✗ users_resource table creation error: {e}")
        connection.rollback()
        raise


def _migrate_create_user_social_links_table(connection):
    """Create users_social_links table and remove JSON column from users_resource."""
    try:
        # 1. Create users_social_links table
        result = connection.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'users_social_links'
        """))
        
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("  - Creating users_social_links table...")
            
            connection.execute(text("""
                CREATE TABLE users_social_links (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_resource_id INT NOT NULL,
                    platform_name VARCHAR(50) NOT NULL,
                    link VARCHAR(500) NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_resource_id) REFERENCES users_resource(id) ON DELETE CASCADE,
                    INDEX idx_social_user_res (user_resource_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """))
            connection.commit()
            print("  ✓ users_social_links table created")
        else:
            print("  ✓ users_social_links table already exists")

        # 2. Drop social_links JSON column from users_resource if it exists
        col_result = connection.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'users_resource' 
            AND COLUMN_NAME = 'social_links'
        """))
        if col_result.fetchone()[0] > 0:
            print("  - Dropping deprecated social_links column from users_resource...")
            connection.execute(text("ALTER TABLE users_resource DROP COLUMN social_links"))
            connection.commit()
            print("  ✓ Dropped social_links column")
            
    except Exception as e:
        print(f"  ✗ users_social_links migration error: {e}")
        connection.rollback()
        raise


def _migrate_user_resource_unique_constraint(connection):
    """Ensure users_resource has a unique constraint on (user_id, user_type)."""
    try:
        # Check if index exists
        result = connection.execute(text("""
            SELECT COUNT(*) 
            FROM information_schema.STATISTICS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'users_resource' 
            AND INDEX_NAME = 'unique_user_resource'
        """))
        
        index_exists = result.fetchone()[0] > 0
        
        if not index_exists:
            # Check if likely conflicting index exists (idx_user_lookup from previous version)
            result_old = connection.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.STATISTICS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'users_resource' 
                AND INDEX_NAME = 'idx_user_lookup'
            """))
            if result_old.fetchone()[0] > 0:
                print("  - Removing old index idx_user_lookup...")
                connection.execute(text("DROP INDEX idx_user_lookup ON users_resource"))
            
            print("  - Adding UNIQUE constraint to users_resource...")
            connection.execute(text("""
                ALTER TABLE users_resource
                ADD UNIQUE KEY unique_user_resource (user_id, user_type)
            """))
            connection.commit()
            print("  ✓ Added UNIQUE constraint to users_resource")
        else:
            print("  ✓ users_resource already has UNIQUE constraint")
            
    except Exception as e:
        # If duplicated data exists, this will fail. We log it but don't stop app.
        print(f"  ✗ Failed to add UNIQUE constraint (duplicate data may exist): {e}")
        connection.rollback()


def _migrate_cleanup_snake_case_columns(connection):
    """Drop unused snake_case columns from users table."""
    # List of columns to drop
    columns_to_drop = [
        'bank_account_number',
        'bank_account_name',
        'bank_name',
        'nssf_number',
        'has_spouse',
        'resident',
        'number_of_dependents',
        'employee_nssf'
    ]
    
    dropped_count = 0
    
    for col in columns_to_drop:
        try:
            # Check if column exists
            result = connection.execute(text(f"""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'users' 
                AND COLUMN_NAME = '{col}'
            """))
            
            if result.fetchone()[0] > 0:
                print(f"  - Dropping unused column '{col}' from users table...")
                connection.execute(text(f"ALTER TABLE users DROP COLUMN {col}"))
                connection.commit()
                dropped_count += 1
        except Exception as e:
            print(f"  ! Failed to drop column '{col}': {e}")
            # Continue to next column despite error
            try:
                connection.rollback()
            except:
                pass

    if dropped_count > 0:
        print(f"  ✓ Dropped {dropped_count} unused snake_case columns")
    else:
        print("  ✓ No unused snake_case columns found (or all cleaned up)")


def _migrate_student_image_nullable(connection):
    """Make the student image URL column nullable and text-only."""
    try:
        # Check if column is already nullable
        result = connection.execute(text("""
            SELECT IS_NULLABLE, DATA_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'students'
            AND COLUMN_NAME = 'image'
        """))
        
        row = result.fetchone()
        if row:
            is_nullable = row[0] == 'YES'
            is_url_column = row[1].lower() == 'varchar'
            print(f"  - Student image nullable status: {row[0]}")
            
            if not is_nullable or not is_url_column:
                print("  - Making student image column nullable and URL-only...")
                
                connection.execute(text("""
                    ALTER TABLE students
                    MODIFY COLUMN image VARCHAR(1000) NULL
                """))
                connection.commit()
                
                print("  ✓ Student image column is now nullable")
            else:
                print("  ✓ Student image column is already nullable")
        else:
            print("  ! Student image column not found (skipping)")
        
    except Exception as e:
        print(f"  ✗ Student image migration error: {e}")
        connection.rollback()

def _migrate_academic_program_social_links(connection):
    """Add social media URL columns to the academic_programs table."""
    try:
        # Check existing columns
        result = connection.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'academic_programs'
        """))
        existing_cols = {row[0] for row in result.fetchall()}
        
        new_cols = [
            'facebook_url',
            'telegram_url',
            'youtube_url',
            'tiktok_url'
        ]
        
        for col in new_cols:
            if col not in existing_cols:
                print(f"  - Adding {col} to academic_programs...")
                connection.execute(text(f"""
                    ALTER TABLE academic_programs
                    ADD COLUMN {col} VARCHAR(255) NULL
                """))
                connection.commit()
                print(f"  ✓ Added {col}")
            else:
                print(f"  ✓ {col} already exists in academic_programs")
                
    except Exception as e:
        print(f"  ✗ error migrating academic_programs social links: {e}")
        connection.rollback()
        raise


def _migrate_school_overview_translations(connection):
    """Add title_en/title_km/content_en/content_km to school_overviews."""
    try:
        result = connection.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'school_overviews'
        """))
        existing_cols = {row[0] for row in result.fetchall()}

        if 'title_en' not in existing_cols:
            print("  - Adding multilingual fields to school_overviews...")
            connection.execute(text("""
                ALTER TABLE school_overviews
                ADD COLUMN title_en VARCHAR(255) NULL,
                ADD COLUMN title_km VARCHAR(255) NULL,
                ADD COLUMN content_en TEXT NULL,
                ADD COLUMN content_km TEXT NULL
            """))
            connection.commit()

            connection.execute(text("""
                UPDATE school_overviews
                SET title_en = COALESCE(title_en, title),
                    content_en = COALESCE(content_en, content)
            """))
            connection.commit()
            print("  ✓ Multilingual fields added to school_overviews")
        else:
            print("  ✓ Multilingual fields already exist on school_overviews")
    except Exception as e:
        print(f"  ✗ school_overviews translations migration error: {e}")
        connection.rollback()


def _migrate_drop_deprecated_attendance_location_columns(connection):
    """Drop deprecated check_in_location_id / check_out_location_id from attendance_records."""
    deprecated_cols = ["check_in_location_id", "check_out_location_id"]
    for col_name in deprecated_cols:
        try:
            result = connection.execute(text("""
                SELECT COUNT(*) AS c
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'attendance_records'
                  AND COLUMN_NAME = :col
            """), {"col": col_name})
            if result.fetchone()[0] > 0:
                print(f"  - Dropping deprecated column {col_name} from attendance_records...")
                connection.execute(text(f"ALTER TABLE attendance_records DROP COLUMN {col_name}"))
                connection.commit()
                print(f"  ✓ Dropped {col_name}")
            else:
                print(f"  ✓ {col_name} already removed")
        except Exception as e:
            print(f"  ✗ Could not drop {col_name}: {e}")
            connection.rollback()


def _migrate_market_listing_condition(connection):
    """Add optional item condition to marketplace listings (new | like_new | used)."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'market_listings'
              AND COLUMN_NAME = 'condition'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding condition to market_listings...")
            connection.execute(text("""
                ALTER TABLE market_listings
                ADD COLUMN `condition` VARCHAR(20) NULL
            """))
            connection.commit()
            print("  ✓ market_listings.condition column added")
        else:
            print("  ✓ market_listings.condition already exists")
    except Exception as e:
        print(f"  ✗ market_listings condition migration error: {e}")
        connection.rollback()
        raise


def _migrate_market_listing_renewals(connection):
    """Add listing renewal timestamps and the community-push audit table."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'market_listings'
              AND COLUMN_NAME = 'renewed_at'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding renewed_at to market_listings...")
            connection.execute(text("""
                ALTER TABLE market_listings
                ADD COLUMN renewed_at DATETIME NULL,
                ADD INDEX ix_market_listings_renewed_at (renewed_at)
            """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS market_listing_broadcasts (
                id INT NOT NULL AUTO_INCREMENT,
                store_id INT NOT NULL,
                listing_id INT NOT NULL,
                publication_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_market_broadcast_store_created (store_id, created_at),
                INDEX ix_market_broadcast_listing_created (listing_id, created_at),
                CONSTRAINT fk_market_broadcast_store
                    FOREIGN KEY (store_id) REFERENCES market_stores(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_market_broadcast_listing
                    FOREIGN KEY (listing_id) REFERENCES market_listings(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        """))
        connection.commit()
        print("  ✓ marketplace renewal and broadcast tables ready")
    except Exception as e:
        print(f"  ✗ marketplace renewal migration error: {e}")
        connection.rollback()
        raise


def _migrate_market_store_cover(connection):
    """Add optional cover image URL to marketplace stores."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'market_stores'
              AND COLUMN_NAME = 'cover_url'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding cover_url to market_stores...")
            connection.execute(text("""
                ALTER TABLE market_stores
                ADD COLUMN cover_url VARCHAR(500) NULL
            """))
            connection.commit()
            print("  ✓ market_stores.cover_url column added")
        else:
            print("  ✓ market_stores.cover_url already exists")
    except Exception as e:
        print(f"  ✗ market_stores cover_url migration error: {e}")
        connection.rollback()
        raise


def _migrate_market_category_i18n(connection):
    """Add bilingual category labels (name_en, name_km) and icon_key to market_categories."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'market_categories'
              AND COLUMN_NAME = 'name_en'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding name_en, name_km, icon_key to market_categories...")
            connection.execute(text("""
                ALTER TABLE market_categories
                ADD COLUMN name_en VARCHAR(100) NULL,
                ADD COLUMN name_km VARCHAR(100) NULL,
                ADD COLUMN icon_key VARCHAR(50) NULL
            """))

        connection.execute(text("""
            UPDATE market_categories
            SET name_en = COALESCE(NULLIF(TRIM(name_en), ''), name),
                name_km = CASE
                    WHEN name_km IS NULL OR TRIM(name_km) = '' THEN
                        CASE name
                            WHEN 'Books' THEN 'សៀវភៅ'
                            WHEN 'Uniform' THEN 'ឯកសណ្ឋាន'
                            WHEN 'Food' THEN 'អាហារ'
                            WHEN 'Electronics' THEN 'គ្រឿងអេឡិចត្រូនិច'
                            WHEN 'Other' THEN 'ផ្សេងៗ'
                            ELSE name
                        END
                    ELSE name_km
                END,
                icon_key = CASE
                    WHEN icon_key IS NULL OR TRIM(icon_key) = '' THEN
                        CASE LOWER(name)
                            WHEN 'books' THEN 'books'
                            WHEN 'uniform' THEN 'uniform'
                            WHEN 'food' THEN 'food'
                            WHEN 'electronics' THEN 'electronics'
                            ELSE 'other'
                        END
                    ELSE icon_key
                END
            WHERE name_en IS NULL
               OR TRIM(name_en) = ''
               OR name_km IS NULL
               OR TRIM(name_km) = ''
               OR icon_key IS NULL
               OR TRIM(icon_key) = ''
        """))

        # Ensure NOT NULL on name_en / name_km when columns exist
        for col in ("name_en", "name_km"):
            nullable = connection.execute(text(f"""
                SELECT IS_NULLABLE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'market_categories'
                  AND COLUMN_NAME = '{col}'
            """)).fetchone()
            if nullable and nullable[0].upper() == "YES":
                connection.execute(text(f"""
                    ALTER TABLE market_categories
                    MODIFY COLUMN {col} VARCHAR(100) NOT NULL
                """))

        connection.commit()
        print("  ✓ market_categories i18n columns ready")
    except Exception as e:
        print(f"  ✗ market_categories i18n migration error: {e}")
        connection.rollback()
        raise


def _migrate_leave_replacement_note(connection):
    """Add replacement_note to leave_requests table."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'leave_requests'
              AND COLUMN_NAME = 'replacement_note'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding replacement_note to leave_requests...")
            connection.execute(text("""
                ALTER TABLE leave_requests
                ADD COLUMN replacement_note TEXT NULL
            """))
            connection.commit()
            print("  ✓ leave_requests.replacement_note added")
        else:
            print("  ✓ leave_requests.replacement_note already exists")
    except Exception as e:
        print(f"  ✗ leave_requests.replacement_note migration error: {e}")
        connection.rollback()
        raise


def _migrate_manual_staff_leave(connection):
    """Add manual leave audit columns and the explicit approver privilege."""
    try:
        additions = (
            ("leave_requests", "created_by", "INT NULL"),
            ("leave_requests", "creation_source", "VARCHAR(30) NULL"),
            ("leave_approvers", "can_create_for_staff", "BOOLEAN NULL DEFAULT FALSE"),
        )
        for table_name, column_name, definition in additions:
            result = connection.execute(text(f"""
                SELECT COUNT(*) AS c
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = '{table_name}'
                  AND COLUMN_NAME = '{column_name}'
            """))
            if result.fetchone()[0] == 0:
                print(f"  - Adding {table_name}.{column_name}...")
                connection.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column_name} {definition}"
                    )
                )
        connection.execute(text("""
            UPDATE leave_requests
            SET created_by = user_id,
                creation_source = 'employee'
            WHERE created_by IS NULL OR creation_source IS NULL
        """))
        connection.execute(text("""
            UPDATE leave_approvers
            SET can_create_for_staff = FALSE
            WHERE can_create_for_staff IS NULL
        """))
        connection.commit()
        print("  ✓ Manual staff leave columns ready")
    except Exception as e:
        print(f"  ✗ Manual staff leave migration error: {e}")
        connection.rollback()
        raise


def _migrate_leave_approver_view_all(connection):
    """Add independent all-request visibility without approval authority."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'leave_approvers'
              AND COLUMN_NAME = 'can_view_all_requests'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding leave_approvers.can_view_all_requests...")
            connection.execute(text("""
                ALTER TABLE leave_approvers
                ADD COLUMN can_view_all_requests BOOLEAN NULL DEFAULT FALSE
            """))
        connection.execute(text("""
            UPDATE leave_approvers
            SET can_view_all_requests = FALSE
            WHERE can_view_all_requests IS NULL
        """))
        connection.commit()
        print("  ✓ Leave approver view-all permission ready")
    except Exception as e:
        print(f"  ✗ Leave approver view-all migration error: {e}")
        connection.rollback()
        raise


def _migrate_leave_balance_adjustments(connection):
    """Create the policy-deduction ledger and its dedicated permission."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'leave_approvers'
              AND COLUMN_NAME = 'can_adjust_leave_balance'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding leave_approvers.can_adjust_leave_balance...")
            connection.execute(text("""
                ALTER TABLE leave_approvers
                ADD COLUMN can_adjust_leave_balance BOOLEAN NULL DEFAULT FALSE
            """))

        connection.execute(text("""
            UPDATE leave_approvers
            SET can_adjust_leave_balance = FALSE
            WHERE can_adjust_leave_balance IS NULL
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS leave_balance_adjustments (
                id INT NOT NULL AUTO_INCREMENT,
                user_id INT NOT NULL,
                leave_type_id INT NOT NULL,
                academic_id INT NOT NULL,
                amount_days DOUBLE NOT NULL,
                effective_date DATE NOT NULL,
                reason TEXT NOT NULL,
                created_by INT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                voided_by INT NULL,
                void_reason TEXT NULL,
                voided_at DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_leave_adjustment_user (user_id),
                INDEX ix_leave_adjustment_type (leave_type_id),
                INDEX ix_leave_adjustment_academic (academic_id),
                INDEX ix_leave_adjustment_effective (effective_date),
                INDEX ix_leave_adjustment_status (status),
                CONSTRAINT fk_leave_adjustment_user
                    FOREIGN KEY (user_id) REFERENCES users(id),
                CONSTRAINT fk_leave_adjustment_type
                    FOREIGN KEY (leave_type_id) REFERENCES leave_types(id),
                CONSTRAINT fk_leave_adjustment_creator
                    FOREIGN KEY (created_by) REFERENCES users(id),
                CONSTRAINT fk_leave_adjustment_voider
                    FOREIGN KEY (voided_by) REFERENCES users(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        connection.commit()
        print("  ✓ Leave balance adjustment ledger ready")
    except Exception as e:
        print(f"  ✗ Leave balance adjustment migration error: {e}")
        connection.rollback()
        raise


def _migrate_attendance_session_transition_wait(connection):
    """Add the configurable anti-abuse wait between attendance sessions."""
    try:
        result = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'attendance_system_settings'
              AND COLUMN_NAME = 'session_transition_wait_mins'
        """))
        if result.fetchone()[0] == 0:
            print("  - Adding attendance_system_settings.session_transition_wait_mins...")
            connection.execute(text("""
                ALTER TABLE attendance_system_settings
                ADD COLUMN session_transition_wait_mins INT NOT NULL DEFAULT 10
            """))
        connection.execute(text("""
            UPDATE attendance_system_settings
            SET session_transition_wait_mins = 10
            WHERE session_transition_wait_mins IS NULL
        """))
        connection.commit()
        print("  ✓ Attendance session transition wait ready")
    except Exception as e:
        print(f"  ✗ Attendance session transition wait migration error: {e}")
        connection.rollback()
        raise


def _migrate_attendance_primary_devices(connection):
    """Create primary attendance-phone binding/audit tables and reset grant."""
    try:
        permission_column = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'app_admins'
              AND COLUMN_NAME = 'can_reset_attendance_devices'
        """)).scalar()
        if int(permission_column or 0) == 0:
            print("  - Adding app_admins.can_reset_attendance_devices...")
            connection.execute(text("""
                ALTER TABLE app_admins
                ADD COLUMN can_reset_attendance_devices BOOLEAN NOT NULL DEFAULT FALSE
            """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_primary_devices (
                user_id INT NOT NULL,
                device_id_hash CHAR(64) NOT NULL,
                device_name VARCHAR(255) NOT NULL,
                platform VARCHAR(20) NOT NULL,
                registered_at DATETIME NOT NULL,
                last_changed_at DATETIME NOT NULL,
                change_available_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id),
                INDEX ix_attendance_primary_device_hash (device_id_hash),
                INDEX ix_attendance_primary_device_change (change_available_at),
                CONSTRAINT fk_attendance_primary_device_user
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance_primary_device_events (
                id INT NOT NULL AUTO_INCREMENT,
                user_id INT NOT NULL,
                action VARCHAR(40) NOT NULL,
                actor_user_id INT NULL,
                previous_device_name VARCHAR(255) NULL,
                new_device_name VARCHAR(255) NULL,
                reason TEXT NULL,
                detail_json TEXT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_attendance_device_event_user (user_id),
                INDEX ix_attendance_device_event_actor (actor_user_id),
                INDEX ix_attendance_device_event_action (action),
                INDEX ix_attendance_device_event_created (created_at),
                CONSTRAINT fk_attendance_device_event_user
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                CONSTRAINT fk_attendance_device_event_actor
                    FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        connection.commit()
        print("  ✓ Attendance primary-device binding ready")
    except Exception as e:
        print(f"  ✗ Attendance primary-device migration error: {e}")
        connection.rollback()
        raise


def _migrate_learning_homework(connection):
    """Add schedule shift ownership and homework/attachment tables."""
    try:
        shift_column = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'learning_class_schedules'
              AND COLUMN_NAME = 'shift_id'
        """)).scalar()
        if int(shift_column or 0) == 0:
            print("  - Adding learning_class_schedules.shift_id...")
            connection.execute(text("""
                ALTER TABLE learning_class_schedules
                ADD COLUMN shift_id INT NULL AFTER grade_type_id,
                ADD INDEX ix_learning_class_schedule_shift (shift_id)
            """))

        # Prefer an explicit shift-scoped time-slot assignment for legacy rows.
        connection.execute(text("""
            UPDATE learning_class_schedules lcs
            JOIN learning_time_slot_scopes ltss
              ON ltss.time_slot_id = lcs.time_slot_id
             AND ltss.shift_id IS NOT NULL
             AND (
                  (ltss.scope_type = 'grade' AND ltss.scope_id = lcs.grade_id)
                  OR
                  (ltss.scope_type = 'grade_group' AND ltss.scope_id = lcs.grade_group_id)
             )
            SET lcs.shift_id = ltss.shift_id
            WHERE lcs.shift_id IS NULL
        """))

        # Otherwise backfill only when enrollment data identifies exactly one
        # shift. Ambiguous rows intentionally remain NULL and cannot publish
        # homework until an administrator saves the schedule's class shift.
        connection.execute(text("""
            UPDATE learning_class_schedules lcs
            JOIN (
                SELECT
                    l.academicid,
                    l.programid,
                    g.group_id AS grade_group_id,
                    l.gradeid,
                    l.grade_type_id,
                    MIN(l.shiftid) AS shift_id
                FROM learning l
                JOIN grade g ON g.id = l.gradeid
                WHERE l.shiftid IS NOT NULL
                GROUP BY
                    l.academicid,
                    l.programid,
                    g.group_id,
                    l.gradeid,
                    l.grade_type_id
                HAVING COUNT(DISTINCT l.shiftid) = 1
            ) enrolled
              ON enrolled.academicid = lcs.academic_id
             AND enrolled.programid = lcs.program_id
             AND enrolled.grade_group_id = lcs.grade_group_id
             AND enrolled.gradeid = lcs.grade_id
             AND (enrolled.grade_type_id <=> lcs.grade_type_id)
            SET lcs.shift_id = enrolled.shift_id
            WHERE lcs.shift_id IS NULL
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS learning_homework (
                id INT NOT NULL AUTO_INCREMENT,
                academic_id INT NOT NULL,
                class_schedule_id INT NULL,
                branch_id INT NOT NULL,
                program_id INT NOT NULL,
                grade_group_id INT NOT NULL,
                grade_id INT NULL,
                grade_type_id INT NULL,
                shift_id INT NOT NULL,
                subject_id INT NOT NULL,
                teacher_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                homework_date DATE NOT NULL,
                due_date DATE NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_learning_homework_academic (academic_id),
                INDEX ix_learning_homework_schedule (class_schedule_id),
                INDEX ix_learning_homework_teacher (teacher_id),
                INDEX ix_learning_homework_class (
                    academic_id, program_id, grade_id, shift_id
                ),
                INDEX ix_learning_homework_created (created_at),
                INDEX ix_learning_homework_date (homework_date),
                CONSTRAINT fk_learning_homework_schedule
                    FOREIGN KEY (class_schedule_id)
                    REFERENCES learning_class_schedules(id) ON DELETE SET NULL,
                CONSTRAINT fk_learning_homework_teacher
                    FOREIGN KEY (teacher_id) REFERENCES users(id),
                CONSTRAINT fk_learning_homework_subject
                    FOREIGN KEY (subject_id) REFERENCES subjects(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        homework_date_column = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'learning_homework'
              AND COLUMN_NAME = 'homework_date'
        """)).scalar()
        if int(homework_date_column or 0) == 0:
            connection.execute(text("""
                ALTER TABLE learning_homework
                ADD COLUMN homework_date DATE NULL AFTER description
            """))
            connection.execute(text("""
                UPDATE learning_homework
                SET homework_date = DATE(created_at)
                WHERE homework_date IS NULL
            """))
            connection.execute(text("""
                ALTER TABLE learning_homework
                MODIFY COLUMN homework_date DATE NOT NULL
            """))

        homework_date_index = connection.execute(text("""
            SELECT COUNT(*) AS c
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'learning_homework'
              AND INDEX_NAME = 'ix_learning_homework_date'
        """)).scalar()
        if int(homework_date_index or 0) == 0:
            connection.execute(text("""
                ALTER TABLE learning_homework
                ADD INDEX ix_learning_homework_date (homework_date)
            """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS learning_homework_attachments (
                id INT NOT NULL AUTO_INCREMENT,
                homework_id INT NOT NULL,
                file_url VARCHAR(1000) NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                content_type VARCHAR(150) NOT NULL,
                file_size INT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_learning_homework_attachment_homework (homework_id),
                CONSTRAINT fk_learning_homework_attachment_homework
                    FOREIGN KEY (homework_id)
                    REFERENCES learning_homework(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        connection.commit()
        print("  ✓ Learning homework publishing ready")
    except Exception as e:
        print(f"  ✗ Learning homework migration error: {e}")
        connection.rollback()
        raise


def _migrate_subject_grading(connection):
    """Create per-subject grade plans, component scores, and attendance."""
    try:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS subject_grade_plans (
                id INT NOT NULL AUTO_INCREMENT,
                academic_id INT NOT NULL,
                program_id INT NOT NULL,
                grade_id INT NOT NULL,
                grade_type_id INT NOT NULL DEFAULT 0,
                shift_id INT NOT NULL,
                subject_id INT NOT NULL,
                marks_system_id INT NOT NULL,
                created_by INT NOT NULL,
                updated_by INT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_subject_grade_plan_context (
                    academic_id, program_id, grade_id, grade_type_id,
                    shift_id, subject_id, marks_system_id
                ),
                INDEX ix_subject_grade_plan_subject (subject_id),
                INDEX ix_subject_grade_plan_exam (marks_system_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS subject_grade_components (
                id INT NOT NULL AUTO_INCREMENT,
                plan_id INT NOT NULL,
                name VARCHAR(120) NOT NULL,
                weight_percent DECIMAL(7,2) NOT NULL,
                source_type VARCHAR(30) NOT NULL DEFAULT 'manual',
                sort_order INT NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                INDEX ix_subject_grade_component_plan (plan_id),
                CONSTRAINT fk_subject_grade_component_plan
                    FOREIGN KEY (plan_id) REFERENCES subject_grade_plans(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS subject_grade_scores (
                id INT NOT NULL AUTO_INCREMENT,
                component_id INT NOT NULL,
                student_id INT NOT NULL,
                earned_points DECIMAL(7,2) NOT NULL,
                updated_by INT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_subject_grade_score_student (
                    component_id, student_id
                ),
                INDEX ix_subject_grade_score_student (student_id),
                CONSTRAINT fk_subject_grade_score_component
                    FOREIGN KEY (component_id)
                    REFERENCES subject_grade_components(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS subject_attendance (
                id INT NOT NULL AUTO_INCREMENT,
                student_id INT NOT NULL,
                academic_id INT NOT NULL,
                program_id INT NOT NULL,
                grade_id INT NOT NULL,
                grade_type_id INT NOT NULL DEFAULT 0,
                shift_id INT NOT NULL,
                subject_id INT NOT NULL,
                attendance_date DATE NOT NULL,
                status VARCHAR(20) NOT NULL,
                note VARCHAR(255) NULL,
                teacher_id INT NOT NULL,
                created_by INT NOT NULL,
                updated_by INT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_subject_attendance_context (
                    student_id, academic_id, program_id, grade_id,
                    grade_type_id, shift_id, subject_id, attendance_date
                ),
                INDEX ix_subject_attendance_subject_date (
                    academic_id, program_id, grade_id, grade_type_id,
                    shift_id, subject_id, attendance_date
                ),
                INDEX ix_subject_attendance_student (student_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        connection.commit()
        print("  ✓ Subject grading and attendance ready")
    except Exception as e:
        print(f"  ✗ Subject grading migration error: {e}")
        connection.rollback()
        raise


def _migrate_subject_grading_attendance_period(connection):
    """Store the attendance date range used by each subject grading plan."""
    try:
        for column_name in ("attendance_start_date", "attendance_end_date"):
            exists = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'subject_grade_plans'
                      AND COLUMN_NAME = :column_name
                """),
                {"column_name": column_name},
            ).scalar()
            if int(exists or 0) == 0:
                connection.execute(
                    text(
                        f"ALTER TABLE subject_grade_plans "
                        f"ADD COLUMN {column_name} DATE NULL AFTER marks_system_id"
                    )
                )

        connection.execute(text("""
            UPDATE subject_grade_plans p
            LEFT JOIN marks_system ms ON ms.id = p.marks_system_id
            SET p.attendance_start_date = DATE_FORMAT(
                    COALESCE(ms.for_month, CURRENT_DATE), '%Y-%m-01'
                ),
                p.attendance_end_date = LAST_DAY(
                    COALESCE(ms.for_month, CURRENT_DATE)
                )
            WHERE p.attendance_start_date IS NULL
               OR p.attendance_end_date IS NULL
        """))
        connection.commit()
        print("  ✓ Subject grading attendance periods ready")
    except Exception as e:
        print(f"  ✗ Subject grading attendance-period migration error: {e}")
        connection.rollback()
        raise


def _migrate_leave_monthly_cap(connection):
    """Add the monthly leave cap and the paid/unpaid split it produces.

    day_cost is deliberately left untouched: it stays the record of how much
    leave was taken, while paid_cost/unpaid_cost is a derived split that
    services.leave_monthly_policy can recompute at any time. Backfilling every
    existing day as fully paid keeps behaviour identical until an administrator
    configures a cap.
    """
    try:
        cap_exists = connection.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'leave_types'
              AND COLUMN_NAME = 'max_days_per_month'
        """)).scalar()
        if int(cap_exists or 0) == 0:
            print("  - Adding leave_types.max_days_per_month...")
            connection.execute(text(
                "ALTER TABLE leave_types "
                "ADD COLUMN max_days_per_month DOUBLE NULL AFTER max_days_per_year"
            ))

        for column_name in ("paid_cost", "unpaid_cost"):
            exists = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'leave_request_days'
                      AND COLUMN_NAME = :column_name
                """),
                {"column_name": column_name},
            ).scalar()
            if int(exists or 0) == 0:
                print(f"  - Adding leave_request_days.{column_name}...")
                connection.execute(text(
                    f"ALTER TABLE leave_request_days "
                    f"ADD COLUMN {column_name} DOUBLE NULL AFTER day_cost"
                ))

        connection.execute(text("""
            UPDATE leave_request_days
            SET paid_cost = day_cost,
                unpaid_cost = 0
            WHERE paid_cost IS NULL OR unpaid_cost IS NULL
        """))
        connection.commit()
        print("  ✓ Monthly leave cap columns ready")
    except Exception as e:
        print(f"  ✗ Monthly leave cap migration error: {e}")
        connection.rollback()
        raise


def _migrate_settings_security_toggles(connection):
    """Add settings.phone_conflict_lock_enabled.

    Whether to hard-lock accounts that share a phone number needs to be
    changeable while the office works through the duplicates, and asking someone
    to edit an env file and redeploy for that is not realistic. NULL means the
    environment default still applies.
    """
    try:
        exists = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'settings'
            AND COLUMN_NAME = 'phone_conflict_lock_enabled'
        """)).fetchone()[0] > 0
        if not exists:
            print("  - Adding settings.phone_conflict_lock_enabled...")
            connection.execute(text(
                "ALTER TABLE settings ADD COLUMN phone_conflict_lock_enabled TINYINT(1) NULL"
            ))
            connection.commit()
            print("  \u2713 settings.phone_conflict_lock_enabled added")
        else:
            print("  \u2713 settings.phone_conflict_lock_enabled already present")
    except Exception as e:
        print(f"  \u2717 settings security toggle migration error: {e}")
        connection.rollback()
        raise


def _migrate_parent_token_version(connection):
    """Add parents.token_version so a parent session can be ended remotely.

    Employees have had this for a while. Parents did not, which meant a parent
    holding a 60-day token — including one obtained through the phone login
    before it refused ambiguous numbers — could not be signed out by anybody.

    Defaults to 1. Existing tokens carry no version claim and stay valid until
    the number is bumped, so adding the column logs nobody out.
    """
    try:
        exists = connection.execute(text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'parents'
            AND COLUMN_NAME = 'token_version'
        """)).fetchone()[0] > 0
        if not exists:
            connection.execute(text(
                "ALTER TABLE parents ADD COLUMN token_version INT NULL DEFAULT 1"
            ))
            connection.commit()
        else:
            try:
                connection.execute(text(
                    "ALTER TABLE parents MODIFY COLUMN token_version INT NULL DEFAULT 1"
                ))
                connection.execute(text(
                    "UPDATE parents SET token_version = 1 WHERE token_version IS NULL"
                ))
                connection.commit()
            except Exception:
                pass
    except Exception as e:
        print(f"  ✗ parent token_version migration error: {e}")
        connection.rollback()
        raise


if __name__ == "__main__":
    run_migrations()

