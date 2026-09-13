"""
Tenant database provisioner for Kampul SIS Client API.

Creates `sis_<subdomain>` from template_school_db.sql (the full schema plus the
single-branch, single-academic-year presets built by
scripts/build_school_template.py) and adds the school's administrator.
"""
import argparse
import json
import logging
import os
import re
import secrets
import string
from pathlib import Path
from typing import Any, Dict, Optional

import bcrypt
import pymysql

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "template_school_db.sql"
ADMIN_USER_ID = 1
SUPER_ADMIN_ROLE_ID = 1
DEFAULT_BRANCH_ID = 1


def validate_school_defaults(cur):
    """Fail provisioning before exposing a school with unusable defaults."""
    for table in ("branch", "academic", "settings"):
        cur.execute(f"SELECT id FROM `{table}`")
        if cur.fetchall() != ((1,),):
            raise ValueError(f"School template must contain exactly one {table} with id 1")
    cur.execute("SELECT academicid FROM settings WHERE id = 1")
    if cur.fetchone()[0] != 1:
        raise ValueError("School settings must select academic 1")
    cur.execute("SELECT status FROM academic WHERE id = 1")
    if cur.fetchone()[0] != 1:
        raise ValueError("Default academic year must be active")
    for table in ("users", "app_admins", "students", "parents"):
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        if cur.fetchone()[0]:
            raise ValueError(f"School template must not contain source {table}")
    cur.execute("SELECT role_name FROM roles WHERE id = 1")
    role = cur.fetchone()
    if not role or role[0] not in ("Super Admin", "Admin"):
        raise ValueError("School template is missing administrator role 1")


def generate_random_admin_password(length: int = 12) -> str:
    """
    Generates a cryptographically strong, human-readable random password.
    Contains uppercase, lowercase, numbers, and allowed punctuation.
    """
    prefix = "Kmp@"
    charset = string.ascii_letters + string.digits + "!#$%"
    random_part = "".join(secrets.choice(charset) for _ in range(length - len(prefix)))
    return f"{prefix}{random_part}"


def template_statements(path: Path):
    """Yield the template's statements. The generator escapes newlines inside
    string literals, so a semicolon at end of line always ends a statement."""
    sql = path.read_text(encoding="utf-8")
    for chunk in re.split(r";\s*\n", sql):
        stmt = "\n".join(l for l in chunk.splitlines() if not l.strip().startswith("--")).strip()
        if stmt:
            yield stmt


def provision_tenant_database(
    subdomain: str,
    school_name: str,
    school_name_km: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    mysql_host: Optional[str] = None,
    mysql_port: Optional[int] = None,
    mysql_user: Optional[str] = None,
    mysql_password: Optional[str] = None,
    template_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Provisions a new school database with the template presets and an administrator
    account. Refuses to touch a database that already contains tables.
    """
    host = mysql_host or os.getenv("DB_HOST", "127.0.0.1")
    port = int(mysql_port or os.getenv("DB_PORT", 3306))
    user = mysql_user or os.getenv("DB_USER", "root")
    password = mysql_password if mysql_password is not None else os.getenv("DB_PASSWORD", "")
    template = Path(template_path or os.getenv("KAMPUL_TEMPLATE_SQL") or TEMPLATE_PATH)
    if not template.is_file():
        raise FileNotFoundError(f"School template not found: {template}")

    safe_subdomain = re.sub(r"[^a-z0-9]", "_", subdomain.lower()).strip("_")
    if not safe_subdomain:
        raise ValueError(f"Invalid subdomain: {subdomain!r}")
    db_name = f"sis_{safe_subdomain}"

    if not admin_username:
        email_prefix = (contact_email or "admin").split("@")[0]
        admin_username = "".join(c for c in email_prefix if c.isalnum() or c == "_") or "admin"
    admin_password = admin_password or generate_random_admin_password()
    admin_password_hash = bcrypt.hashpw(admin_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    admin_name = (contact_name or school_name)[:100]

    logger.info("Provisioning tenant database `%s` on %s:%s", db_name, host, port)
    conn = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4", autocommit=True)
    created = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (db_name,))
            existing_tables = cur.fetchone()[0]
            if existing_tables:
                raise RuntimeError(
                    f"Database `{db_name}` already has {existing_tables} tables; refusing to overwrite an existing school"
                )
            cur.execute("SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = %s", (db_name,))
            created = cur.fetchone()[0] == 0
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute(f"USE `{db_name}`")

            for stmt in template_statements(template):
                cur.execute(stmt)

            validate_school_defaults(cur)

            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute(
                "UPDATE `settings` SET `enterpriseName` = %s, `ownerKname` = %s, `ownerEname` = %s ORDER BY id LIMIT 1",
                (school_name[:100], admin_name, admin_name),
            )
            cur.execute(
                "UPDATE `branch` SET `email` = %s, `contact` = %s WHERE id = %s",
                (contact_email or None, contact_phone or None, DEFAULT_BRANCH_ID),
            )
            cur.execute(
                "INSERT INTO `users` ("
                "  id, username, password, uniqueId, kName, eName, height, gender, dob, nationality,"
                "  religion, province, district, commune, email, phone, education, workplace, status,"
                "  role, isForeigner, token_version"
                ") VALUES (%s, %s, %s, 'ADM-001', %s, %s, 0, '', '1990-01-01', 'ខ្មែរ',"
                "  '', '', '', '', %s, %s, '', %s, 1, %s, 0, 1)",
                (
                    ADMIN_USER_ID, admin_username, admin_password_hash,
                    (school_name_km or admin_name)[:100], admin_name,
                    contact_email or None, contact_phone or None,
                    DEFAULT_BRANCH_ID, SUPER_ADMIN_ROLE_ID,
                ),
            )
            cur.execute(
                "INSERT INTO `app_admins` (user_id, is_super_admin, is_locked, created_at, updated_at,"
                " can_reset_attendance_devices) VALUES (%s, 1, 0, NOW(), NOW(), 1)",
                (ADMIN_USER_ID,),
            )
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")

            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s", (db_name,))
            table_count = cur.fetchone()[0]
    except Exception:
        if created:
            logger.error("Provisioning `%s` failed; dropping the partially created database", db_name)
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        raise
    finally:
        conn.close()

    logger.info("Tenant database `%s` provisioned with %s tables", db_name, table_count)
    return {
        "success": True,
        "database": db_name,
        "table_count": table_count,
        "admin_username": admin_username,
        "admin_password": admin_password,
        "school_code": f"SIS-{safe_subdomain[:4].upper()}",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Create a new school database from the template.")
    parser.add_argument("subdomain")
    parser.add_argument("school_name")
    parser.add_argument("--school-name-km")
    parser.add_argument("--contact-name")
    parser.add_argument("--contact-email")
    parser.add_argument("--contact-phone")
    parser.add_argument("--admin-username")
    args = parser.parse_args()

    # The password comes from the environment so it never appears in the process list.
    supplied_password = os.getenv("KAMPUL_ADMIN_PASSWORD") or None
    result = provision_tenant_database(
        args.subdomain,
        args.school_name,
        school_name_km=args.school_name_km,
        contact_name=args.contact_name,
        contact_email=args.contact_email,
        contact_phone=args.contact_phone,
        admin_username=args.admin_username,
        admin_password=supplied_password,
    )
    if supplied_password:
        result.pop("admin_password")
    print(json.dumps(result, ensure_ascii=False))
