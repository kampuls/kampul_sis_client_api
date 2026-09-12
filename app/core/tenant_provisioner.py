"""
Tenant Database Provisioner for Kampul SIS Client API.
Creates the isolated tenant database, all 212 tables, default seed data,
and generates a cryptographically random admin password.
"""
import os
import re
import secrets
import string
import logging
import pymysql
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def generate_random_admin_password(length: int = 12) -> str:
    """
    Generates a cryptographically strong, human-readable random password.
    Contains uppercase, lowercase, numbers, and allowed punctuation.
    """
    prefix = "Kmp@"
    charset = string.ascii_letters + string.digits + "!#$%"
    random_part = "".join(secrets.choice(charset) for _ in range(length - len(prefix)))
    return f"{prefix}{random_part}"


def provision_tenant_database(
    subdomain: str,
    school_name: str,
    school_name_km: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    mysql_host: Optional[str] = None,
    mysql_port: Optional[int] = None,
    mysql_user: Optional[str] = None,
    mysql_password: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Provisions a complete 212-table school database in MySQL with default reference data
    and an auto-generated administrator account with a unique random password.
    """
    host = mysql_host or os.getenv("DB_HOST", "127.0.0.1")
    port = int(mysql_port or os.getenv("DB_PORT", 3306))
    user = mysql_user or os.getenv("DB_USER", "root")
    password = mysql_password or os.getenv("DB_PASSWORD", "")

    # Sanitize database name
    safe_subdomain = "".join(c if c.isalnum() else "_" for c in subdomain.lower())
    db_name = f"sis_{safe_subdomain}"

    # Generate random admin password and username
    email_prefix = (contact_email or "admin").split("@")[0]
    clean_prefix = "".join(c for c in email_prefix if c.isalnum() or c == "_")
    admin_username = clean_prefix or "admin"
    admin_plain_password = generate_random_admin_password()

    # Hash password with bcrypt
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        admin_password_hash = pwd_context.hash(admin_plain_password)
    except Exception:
        import hashlib
        admin_password_hash = hashlib.sha256(admin_plain_password.encode('utf-8')).hexdigest()

    logger.info(f"Provisioning tenant database `{db_name}` on {host}:{port}...")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True
    )

    try:
        with conn.cursor() as cur:
            # 1. Create database
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            cur.execute(f"USE `{db_name}`;")
            cur.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cur.execute("SET NAMES utf8mb4;")

            # 2. Read and execute template SQL containing all 212 tables and seed data
            template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "template_school_db.sql")
            if not os.path.exists(template_path):
                template_path = r"e:\kampul\kampul_sis_client_api\template_school_db.sql"

            with open(template_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            statements = re.split(r';\s*\n', sql_content)
            for stmt in statements:
                lines = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
                stmt = "\n".join(lines).strip()
                if not stmt:
                    continue
                try:
                    cur.execute(stmt)
                except Exception as e:
                    logger.warning(f"Notice during SQL execution: {e}")

            # 3. Update settings with school details
            km_name = school_name_km or school_name
            cur.execute(
                "UPDATE `settings` SET `enterpriseName` = %s, `default_exchange` = 4100 WHERE id = 1;",
                (school_name,)
            )

            # 4. Update default branch
            cur.execute(
                "UPDATE `branch` SET `branch_name` = 'Main Campus', `app_display_name` = 'Main Campus' WHERE id = 1;"
            )

            # 5. Update default academic year
            cur.execute(
                "UPDATE `academic` SET `academic_name` = '2026-2027', `academic_us_name` = '2026-2027', `status` = 1 WHERE id = 1;"
            )

            # 6. Insert initial Administrator user with unique random password
            full_contact_name = contact_name or school_name
            cur.execute(
                "INSERT INTO `users` ("
                "  id, username, password, email, uniqueId, kName, eName, phone, "
                "  height, gender, dob, nationality, religion, province, district, commune, "
                "  education, workplace, status, role, isForeigner"
                ") VALUES ("
                "  1, %s, %s, %s, 'ADM-001', %s, %s, %s, "
                "  170.00, 'Male', '1990-01-01', 'Cambodian', 'Buddhism', 'Phnom Penh', 'Daun Penh', 'Phsar Thmei', "
                "  'Bachelor', 1, 1, 1, 0"
                ") ON DUPLICATE KEY UPDATE "
                "  password = VALUES(password), "
                "  status = 1, role = 1, email = VALUES(email);",
                (
                    admin_username,
                    admin_password_hash,
                    contact_email or "",
                    km_name,
                    full_contact_name,
                    contact_phone or ""
                )
            )

            # Verify table count
            cur.execute("SHOW TABLES;")
            tables = cur.fetchall()
            table_count = len(tables)

            cur.execute("SET FOREIGN_KEY_CHECKS = 1;")

        logger.info(f"Tenant database `{db_name}` provisioned successfully with {table_count} tables.")

        return {
            "success": True,
            "database": db_name,
            "table_count": table_count,
            "admin_username": admin_username,
            "admin_password": admin_plain_password,
            "school_code": f"SIS-{subdomain[:4].upper()}"
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    subdomain = sys.argv[1] if len(sys.argv) > 1 else "demo"
    name = sys.argv[2] if len(sys.argv) > 2 else "Demo School"
    res = provision_tenant_database(subdomain, name)
    print("Provision result:", res)
