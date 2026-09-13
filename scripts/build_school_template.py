#!/usr/bin/env python
"""
Build `template_school_db.sql`, the blank database every new school receives.

The template is generated from a known-good school database. It keeps the full
schema plus the curriculum/reference presets of ONE academic year and ONE
branch, remapped to academic id 1 and branch id 1. Operational data and
anything identifying the source school (people, contacts, bot tokens, GPS,
uploaded files, fees, forms) is never copied. The school administrator is
added later by app/core/tenant_provisioner.py.

    python scripts/build_school_template.py --source "working test"

Connects with DB_HOST / DB_PORT / DB_USER / DB_PASSWORD (default: local root).
"""
import argparse
import os
import re
import sys
from pathlib import Path

import pymysql

TEMPLATE_ACADEMIC_ID = 1
TEMPLATE_BRANCH_ID = 1
ADMIN_USER_ID = 1  # created by app/core/tenant_provisioner.py

# Global reference presets, copied as-is.
COPY_ALL = [
    "_schema_patches", "alembic_version",
    "roles", "permissions", "role_permissions",
    "department", "position", "status", "shift", "units", "category", "items_group",
    "nittes", "leave_types", "holidays", "learning_time_slots", "program",
    "decimal_marks_allow", "medalname", "medal_points_setup",
    "market_categories", "market_settings",
    "attendance_system_settings", "results_top_students_display_settings",
    "price_visibility_settings", "feature_locks",
]

# Presets scoped to the source academic year / branch.
SCOPED = {
    "academic": "id = {acad}",
    "branch": "id = {branch}",
    "grade_group": "academic_id = {acad}",
    "grade_scale": "academic_id = {acad}",
    "grade_type": "academic_id = {acad} AND branch_id = {branch}",
    "grade": "academic_id = {acad} AND branch_id = {branch}",
    "subjects_group": "academic_id = {acad}",
    "marks_system": "academic_id = {acad}",
    "marks_system_subjects":
        "marks_system_id IN (SELECT id FROM marks_system WHERE academic_id = {acad})",
    "exam_calculate_sign": "academic_id = {acad}",
    "exam_calculate_sign_subjects":
        "exam_calculate_sign_id IN (SELECT id FROM exam_calculate_sign WHERE academic_id = {acad})",
    "subjects": (
        "academic_id = {acad}"
        " OR id IN (SELECT subject_id FROM subjects_group WHERE academic_id = {acad})"
        " OR id IN (SELECT s.subject_id FROM marks_system_subjects s"
        "           JOIN marks_system m ON m.id = s.marks_system_id WHERE m.academic_id = {acad})"
        " OR id IN (SELECT s.subject_id FROM exam_calculate_sign_subjects s"
        "           JOIN exam_calculate_sign e ON e.id = s.exam_calculate_sign_id WHERE e.academic_id = {acad})"
    ),
    "medal_price": "academic_id = {acad}",
    "leave_type_allocations": "academic_id = {acad}",
    "pickup_settings": "academic_id = {acad}",
    "pickup_branch_calling": "academic_id = {acad} AND branch_id = {branch}",
}

# One neutral row, taken from the source's first row with identifying fields replaced.
SINGLETONS = {
    "settings": {
        "enterpriseName": "School Name", "eProvince": "", "eDistrict": "", "eCommune": "",
        "eVillage": "", "enterpriseAddress": "", "ownerKname": "", "ownerEname": "",
        "ownerGender": "", "prefixid": "SIS-", "suffix": "", "startid": 1,
        "telegrambot": "", "parent_bot_token": "", "chat_id": "", "report_chat_id": "",
        "system_logo": "", "system_name": "SIS", "secret_pass": "", "image_header": "",
        "facebook_url": None, "telegram_url": None, "youtube_url": None,
        "instagram_url": None, "tiktok_url": None, "active_storage_provider": "local",
        "cloudinary_cloud_name": "", "cloudinary_api_key": "", "cloudinary_api_secret": "",
        "aws_access_key_id": "", "aws_secret_access_key": "", "aws_region_name": "",
        "aws_bucket_name": "", "firebase_storage_bucket": "", "firebase_service_account_json": None,
    },
    "app_branding_settings": {
        "top_text": "SCHOOL", "bottom_text": "MANAGEMENT SYSTEM",
        "use_logo_image": 0, "logo_image_url": None, "logo_image_url_dark": None,
    },
}

BRANCH_OVERRIDES = {
    "branch_name": "Main Campus", "app_display_name": "Main Campus",
    "contact": None, "address_khmer": None, "address_english": None, "email": None,
    "website": None, "id_prefix": "", "invoice_prefix": "", "receipt_prefix": "",
    "receipt_start_number": 1, "vatin_number": None, "users_id": None,
    "receipt_header": "", "image_header": "", "director_kName": None, "director_eName": None,
    "director_signature": None, "stamp": None, "headTeacher_kName": None,
    "headTeacher_eName": None, "headTeacher_signature": None, "app_branch_cover": None,
    "app_branch_facebook_url": None, "app_branch_telegram_url": None,
    "app_branch_youtube_url": None, "app_branch_tiktok_url": None,
    "app_branch_google_map_url": None, "map_latitude": None, "map_longitude": None,
    "image_header_path": None, "director_signature_path": None,
    "headTeacher_signature_path": None, "stamp_path": None, "signature_url": None,
    "stamp_url": None, "report_status": "no",
}

# Rows written from scratch instead of copied.
GENERATED = {
    "accounts": [
        {"id": 1, "account_name": "Main Cash USD", "account_number": "000000001", "qr_code": "",
         "branch_id": TEMPLATE_BRANCH_ID, "academic_id": TEMPLATE_ACADEMIC_ID, "balance": 0,
         "currency": "USD", "bank_name": "Cash", "created_by": ADMIN_USER_ID, "updated_by": ADMIN_USER_ID},
        {"id": 2, "account_name": "Main Cash KHR", "account_number": "000000002", "qr_code": "",
         "branch_id": TEMPLATE_BRANCH_ID, "academic_id": TEMPLATE_ACADEMIC_ID, "balance": 0,
         "currency": "KHR", "bank_name": "Cash", "created_by": ADMIN_USER_ID, "updated_by": ADMIN_USER_ID},
    ],
    "app_quick_action_settings": [{"id": 1, "items_json": "[]"}],
}

# Everything else stays empty, notably these school-specific tables:
# users, app_admins, branch_contacts, work_locations, telegram_*, forms/form_*,
# zing_*, profile_frames, fee_services, nittes_discount, price_list, academic_programs,
# background_cards, background_cert, certificate_settings, attendance_processing_rules,
# learning_time_slot_scopes and all operational tables (students, invoices, marks, ...).

USER_COLUMNS = {"created_by", "updated_by", "head_user_id"}


def remap(table, row):
    if table == "academic":
        row["id"] = TEMPLATE_ACADEMIC_ID
        row["status"] = 1
    if table == "branch":
        row.update(BRANCH_OVERRIDES)
    if table == "feature_locks":
        row.update(is_locked=0, locked_by=None, locked_at=None)
    for col in list(row):
        if col in ("academic_id", "academicid"):
            row[col] = TEMPLATE_ACADEMIC_ID
        elif col == "branch_id" and row[col] is not None:
            row[col] = TEMPLATE_BRANCH_ID
        elif col in USER_COLUMNS and row[col] is not None:
            row[col] = ADMIN_USER_ID
    return row


def fetch(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, [dict(zip(cols, r)) for r in cur.fetchall()]


def insert_sql(conn, table, cols, rows, batch=100):
    # conn.escape() writes newlines inside strings as \n, so every line that
    # ends with ";" is a statement boundary (tenant_provisioner relies on this).
    out = []
    names = ", ".join(f"`{c}`" for c in cols)
    for i in range(0, len(rows), batch):
        values = ",\n".join(
            "(" + ", ".join(conn.escape(r.get(c)) for c in cols) + ")" for r in rows[i:i + batch]
        )
        out.append(f"INSERT INTO `{table}` ({names}) VALUES\n{values};\n")
    return "".join(out)


def build(conn, source, academic_id, branch_id):
    cur = conn.cursor()
    cur.execute(f"USE `{source}`")

    cur.execute("SELECT COUNT(*) FROM information_schema.views WHERE table_schema = %s", (source,))
    views = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = %s", (source,))
    triggers = cur.fetchone()[0]
    if views or triggers:
        sys.exit(f"Source has {views} views / {triggers} triggers; extend this script before using it.")

    if academic_id is None:
        cur.execute("SELECT id FROM academic WHERE status = 1 ORDER BY id DESC LIMIT 1")
        found = cur.fetchone()
        if not found:
            sys.exit("Source has no active academic year (academic.status = 1); pass --academic-id.")
        academic_id = found[0]
    cur.execute("SELECT academic_us_name FROM academic WHERE id = %s", (academic_id,))
    academic_label = (cur.fetchone() or ["?"])[0]

    cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
    tables = sorted(r[0] for r in cur.fetchall())

    missing = (set(COPY_ALL) | set(SCOPED) | set(SINGLETONS) | set(GENERATED)) - set(tables)
    if missing:
        sys.exit(f"Tables listed in this script are missing from the source: {sorted(missing)}")

    parts = [
        "-- ========================================================\n"
        "-- Kampul SIS blank school database template\n"
        "-- Generated by scripts/build_school_template.py; do not edit by hand.\n"
        f"-- {len(tables)} tables, 1 branch, 1 academic year ({academic_label}), no users or operational data.\n"
        "-- ========================================================\n\n"
        "SET NAMES utf8mb4;\n"
        "SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';\n"
        "SET FOREIGN_KEY_CHECKS = 0;\n\n"
    ]
    for t in tables:
        cur.execute(f"SHOW CREATE TABLE `{t}`")
        ddl = re.sub(r" AUTO_INCREMENT=\d+", "", cur.fetchone()[1])
        parts.append(f"DROP TABLE IF EXISTS `{t}`;\n{ddl};\n\n")

    parts.append("-- ========================================================\n-- Preset data\n"
                 "-- ========================================================\n\n")
    summary = {}
    fmt = {"acad": int(academic_id), "branch": int(branch_id)}
    for t in tables:
        if t in GENERATED:
            cols, _ = fetch(cur, f"SELECT * FROM `{t}` LIMIT 0")
            rows = [dict(r) for r in GENERATED[t]]
            unknown = set().union(*rows) - set(cols)
            if unknown:
                sys.exit(f"{t}: generated columns missing from schema: {sorted(unknown)}")
        elif t in SINGLETONS:
            cols, rows = fetch(cur, f"SELECT * FROM `{t}` ORDER BY id LIMIT 1")
            for r in rows:
                r.update(SINGLETONS[t], id=1)
        elif t in SCOPED:
            cols, rows = fetch(cur, f"SELECT * FROM `{t}` WHERE {SCOPED[t].format(**fmt)}")
        elif t in COPY_ALL:
            cols, rows = fetch(cur, f"SELECT * FROM `{t}`")
        else:
            continue
        rows = [remap(t, r) for r in rows]
        if t == "branch" and len(rows) != 1:
            sys.exit(f"Source branch id {branch_id} not found.")
        if rows:
            parts.append(f"-- {t}: {len(rows)} rows\n" + insert_sql(conn, t, cols, rows) + "\n")
        summary[t] = len(rows)

    parts.append("SET FOREIGN_KEY_CHECKS = 1;\n")
    return "".join(parts), summary, academic_id, academic_label


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="known-good school database to read from")
    ap.add_argument("--academic-id", type=int, help="source academic year (default: the active one)")
    ap.add_argument("--branch-id", type=int, default=1, help="source branch whose presets are kept")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "template_school_db.sql"))
    args = ap.parse_args()

    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""), charset="utf8mb4",
    )
    try:
        sql, summary, academic_id, label = build(conn, args.source, args.academic_id, args.branch_id)
    finally:
        conn.close()

    Path(args.out).write_text(sql, encoding="utf-8", newline="\n")
    print(f"Wrote {args.out} from `{args.source}` (academic {academic_id} {label}, branch {args.branch_id})")
    for t, n in summary.items():
        print(f"  {t:40} {n}")


if __name__ == "__main__":
    main()
