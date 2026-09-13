from datetime import date, datetime
from datetime import timedelta
from decimal import Decimal
import base64
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "desktop_sql.py"
_SPEC = spec_from_file_location("desktop_sql_under_test", _MODULE_PATH)
_MODULE = module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MODULE)

DesktopSqlRejected = _MODULE.DesktopSqlRejected
bind_named_parameters = _MODULE.bind_named_parameters
blank_desktop_media_value = _MODULE.blank_desktop_media_value
decode_desktop_parameters = _MODULE.decode_desktop_parameters
encode_desktop_value = _MODULE.encode_desktop_value
rewrite_student_image_reads = _MODULE.rewrite_student_image_reads
translate_sqlite_compatibility = _MODULE.translate_sqlite_compatibility
validate_desktop_sql = _MODULE.validate_desktop_sql
requires_admin_privilege = _MODULE.requires_admin_privilege
is_sensitive_credential_column = _MODULE.is_sensitive_credential_column
validate_safe_mutation = _MODULE.validate_safe_mutation
extract_mutation_tables = _MODULE.extract_mutation_tables


def test_accepts_legacy_last_insert_id_suffix_as_one_operation():
    sql = validate_desktop_sql(
        "INSERT INTO students (kName) VALUES (@name); SELECT LAST_INSERT_ID();"
    )
    assert sql == "INSERT INTO students (kName) VALUES (@name)"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE students",
        "SELECT SLEEP(10)",
        "SELECT * FROM mysql.user",
        "SELECT 1; DELETE FROM students",
        "LOAD DATA INFILE 'x' INTO TABLE students",
    ],
)
def test_rejects_administrative_and_multi_statement_sql(sql):
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql(sql)


def test_allows_only_controlled_set_statement():
    assert validate_desktop_sql("SET FOREIGN_KEY_CHECKS = 0;") == "SET FOREIGN_KEY_CHECKS = 0"
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("SET sql_mode = ''")


def test_show_is_limited_to_table_and_column_metadata():
    assert validate_desktop_sql("SHOW TABLES") == "SHOW TABLES"
    assert validate_desktop_sql("SHOW COLUMNS FROM branch") == "SHOW COLUMNS FROM branch"
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("SHOW VARIABLES")


def test_parameter_binding_preserves_mysql_system_variables():
    sql, values = bind_named_parameters(
        "SELECT @studentId, @@session.time_zone",
        {"@studentId": 42},
    )
    assert sql == "SELECT :studentId, @@session.time_zone"
    assert values == {"studentId": 42}


def test_parameter_binding_matches_ado_names_case_insensitively():
    sql, values = bind_named_parameters(
        "SELECT @AcademicId, @academicid",
        {"@AcademicId": 2},
    )
    assert sql == "SELECT :AcademicId, :AcademicId"
    assert values == {"AcademicId": 2}


def test_sqlite_dashboard_dates_are_translated_to_mysql():
    sql = translate_sqlite_compatibility(
        "SELECT strftime('%Y-%m', created_at) AS period "
        "FROM invoice WHERE date('now') >= created_at COLLATE NOCASE"
    )
    assert "DATE_FORMAT(created_at, '%Y-%m')" in sql
    assert "CURDATE()" in sql
    assert "NOCASE" not in sql


def test_sqlite_date_modifiers_and_localtime_are_translated():
    sql = translate_sqlite_compatibility(
        "SELECT date('now', '-12 months'), datetime('now', 'localtime')"
    )
    assert "DATE_SUB(CURDATE(), INTERVAL 12 MONTH)" in sql
    assert "NOW()" in sql


def test_sqlite_numeric_casts_are_translated():
    sql = translate_sqlite_compatibility(
        "SELECT CAST(value AS INTEGER), CAST(total AS REAL)"
    )
    assert "CAST(value AS SIGNED)" in sql
    assert "CAST(total AS DECIMAL(65,10))" in sql


def test_json_values_keep_precision_and_dates():
    assert encode_desktop_value(Decimal("12.340")) == {
        "$type": "decimal",
        "value": "12.340",
    }
    assert encode_desktop_value(date(2026, 8, 15))["$type"] == "date"
    assert encode_desktop_value(datetime(2026, 8, 15, 8, 30))["$type"] == "datetime"


def test_mysql_time_durations_are_encoded_as_dotnet_timespans():
    assert encode_desktop_value(timedelta(hours=7, minutes=15)) == {
        "$type": "timespan",
        "value": "07:15:00",
    }
    assert encode_desktop_value(
        timedelta(days=1, hours=2, minutes=3, seconds=4, microseconds=500_000)
    ) == {
        "$type": "timespan",
        "value": "1.02:03:04.500000",
    }


def test_blob_values_are_never_serialized():
    with pytest.raises(DesktopSqlRejected):
        encode_desktop_value(b"legacy blob")


def test_tagged_student_image_is_the_only_binary_write_compatibility():
    image = b"\xff\xd8\xfflegacy-jpeg"
    decoded, resources = decode_desktop_parameters(
        "UPDATE students SET image = @image WHERE id = @id",
        {
            "@image": {
                "$type": "legacy_student_image",
                "resource_url": "/uploads/desktop/image.jpg",
                "base64": base64.b64encode(image).decode("ascii"),
            },
            "@id": 42,
        },
    )
    assert decoded["@image"] == image
    assert decoded["@id"] == 42
    assert resources == {"image": "/uploads/desktop/image.jpg"}


def test_tagged_student_image_can_clear_the_legacy_and_resource_values():
    decoded, resources = decode_desktop_parameters(
        "UPDATE students SET image = @image WHERE id = @id",
        {
            "@image": {"$type": "legacy_student_image", "remove": True},
            "@id": 42,
        },
    )
    assert decoded["@image"] is None
    assert resources == {"image": None}


def test_current_student_reads_use_the_url_resource_instead_of_the_blob():
    rewritten = rewrite_student_image_reads(
        "SELECT s.id AS student_id, s.image, s.kName "
        "FROM learning l JOIN students s ON s.id = l.studentid"
    )
    assert "s.image" not in rewritten
    assert "users_resource" in rewritten
    assert "desktop_student_resource_s.user_id = s.id" in rewritten
    assert "AS image" in rewritten


def test_primary_students_alias_does_not_rewrite_the_generated_image_alias():
    rewritten = rewrite_student_image_reads(
        "SELECT s.id, s.image, s.kName FROM students s WHERE s.id = @id"
    )
    assert rewritten.count("users_resource") == 1
    assert rewritten.count("AS image") == 1
    assert "AS (SELECT" not in rewritten


def test_unqualified_student_image_reads_keep_the_image_column_name():
    rewritten = rewrite_student_image_reads(
        "SELECT id, image, kName FROM students WHERE id = @id"
    )
    assert "SELECT id, image" not in rewritten
    assert "desktop_student_resource_students.user_id = students.id" in rewritten
    assert "AS image" in rewritten


def test_student_image_mutations_are_not_rewritten():
    sql = "UPDATE students SET image = @image WHERE id = @id"
    assert rewrite_student_image_reads(sql) == sql


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET image = @image WHERE id = @id",
        "UPDATE students SET student_noted = @image WHERE id = @id",
        "SELECT @image FROM students",
    ],
)
def test_tagged_student_image_is_rejected_outside_students_image_mutations(sql):
    with pytest.raises(DesktopSqlRejected):
        decode_desktop_parameters(
            sql,
            {
                "@image": {
                    "$type": "legacy_student_image",
                    "resource_url": "/uploads/desktop/image.jpg",
                    "base64": base64.b64encode(b"\xff\xd8\xffimage").decode("ascii"),
                },
                "@id": 1,
            },
        )


def test_requires_admin_privilege_detects_protected_mutations():
    assert requires_admin_privilege("UPDATE users SET role = 1 WHERE id = 5") is True
    assert requires_admin_privilege("INSERT INTO roles (role_name) VALUES ('SuperAdmin')") is True
    assert requires_admin_privilege("DELETE FROM role_permissions WHERE role_id = 2") is True
    assert requires_admin_privilege("REPLACE INTO system_settings (key, value) VALUES ('a', 'b')") is True
    # Reads are not mutations requiring admin privilege
    assert requires_admin_privilege("SELECT * FROM users WHERE id = 1") is False
    # Regular business mutations (students, attendance, marks) do not require admin privilege
    assert requires_admin_privilege("UPDATE students SET kName = 'Test' WHERE id = 1") is False
    assert requires_admin_privilege("INSERT INTO student_attendance (student_id) VALUES (1)") is False


def test_sensitive_credential_columns_are_redacted():
    assert is_sensitive_credential_column("password") is True
    assert is_sensitive_credential_column("Password") is True
    assert is_sensitive_credential_column("password_hash") is True
    assert is_sensitive_credential_column("token_hash") is True
    assert is_sensitive_credential_column("secret_key") is True
    assert is_sensitive_credential_column("remember_token") is True
    # Normal columns are not redacted
    assert is_sensitive_credential_column("username") is False
    assert is_sensitive_credential_column("id") is False
    assert is_sensitive_credential_column("email") is False


@pytest.mark.parametrize(
    "column",
    ["system_logo", "image_header", "receipt_header", "qr_code", "account_qr_code",
     "stamp", "director_signature", "headTeacher_signature", "image", "front_image"],
)
def test_empty_legacy_media_values_reach_the_desktop_as_null(column):
    # The desktop casts any non-path string in these columns to byte[].
    assert blank_desktop_media_value(column, "") is True
    assert blank_desktop_media_value(column, "   ") is True
    assert blank_desktop_media_value(column, "/uploads/branding/logo.png") is False
    assert blank_desktop_media_value(column, None) is False


def test_blank_media_rule_leaves_text_and_url_columns_alone():
    assert blank_desktop_media_value("signature_url", "") is False
    assert blank_desktop_media_value("image_header_path", "") is False
    assert blank_desktop_media_value("background_url", "") is False
    assert blank_desktop_media_value("branch_name", "") is False
    assert blank_desktop_media_value("contact", "") is False


def test_validate_safe_mutation_blocks_unbounded_update_or_delete():
    # Rejects unbounded DELETE without WHERE
    with pytest.raises(DesktopSqlRejected):
        validate_safe_mutation("DELETE FROM students")

    with pytest.raises(DesktopSqlRejected):
        validate_safe_mutation("DELETE FROM `attendances`;")

    # Rejects unbounded UPDATE without WHERE
    with pytest.raises(DesktopSqlRejected):
        validate_safe_mutation("UPDATE students SET status = 0")

    with pytest.raises(DesktopSqlRejected):
        validate_safe_mutation("UPDATE `users` SET role = 2;")

    # Accepts valid DELETE and UPDATE with WHERE
    validate_safe_mutation("DELETE FROM students WHERE id = 5")
    validate_safe_mutation("DELETE FROM `attendances` WHERE date < '2026-01-01'")
    validate_safe_mutation("UPDATE students SET status = 1 WHERE id = @id")
    validate_safe_mutation("UPDATE users SET DisplayName = 'Admin' WHERE user_id = 10")

    # Accepts non-update/delete statements (INSERT, SELECT, etc.)
    validate_safe_mutation("INSERT INTO students (kName) VALUES ('Test')")
    validate_safe_mutation("SELECT * FROM students")


def test_extract_mutation_tables():
    assert extract_mutation_tables("UPDATE students SET name = 'x' WHERE id = 1") == ["students"]
    assert extract_mutation_tables("INSERT INTO `users` (username) VALUES ('test')") == ["users"]
    assert extract_mutation_tables("DELETE FROM attendances WHERE id = 5") == ["attendances"]
    assert extract_mutation_tables("SELECT * FROM students WHERE id = 1") == []


def test_expanded_forbidden_patterns_block_dynamic_sql_and_admin_ops():
    # Dynamic SQL is forbidden
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("PREPARE stmt FROM 'SELECT 1'")

    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("EXECUTE stmt")

    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("DEALLOCATE PREPARE stmt")

    # Low-level table handler is forbidden
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("HANDLER students OPEN")

    # Server control is forbidden
    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("SHUTDOWN")

    with pytest.raises(DesktopSqlRejected):
        validate_desktop_sql("KILL 1234")


def test_hash_comment_is_masked():
    sql = "SELECT id FROM students # this is a comment\n WHERE id = 1"
    assert validate_desktop_sql(sql) == sql

