# Database Migrations & New Feature Guide
**Kampul SIS Client API (`kampul_sis_client_api`)**

This guide explains how database updates, new tables, new columns, and default seed data work across all schools, and outlines the exact procedure developers must follow when creating new features.

---

## 1. How the Multi-Tenant Architecture Handles Updates

In Kampul SIS, **1 single codebase** serves all schools, but each school has its **own isolated database** (e.g. `sis_school_a`, `sis_school_b`, etc.).

### A. When a Brand-New School Registers
1. The platform provisioning engine (`app/core/tenant_provisioner.py`) creates the school database (`sis_<subdomain>`).
2. It executes `template_school_db.sql` to immediately create all 212 core tables and populate essential reference seeds (roles, grades, currencies, etc.).
3. It creates the Administrator user (`ADM-001`) with a unique, cryptographically random password.
4. When the API container boots up for that school, the **Startup Schema Sync** automatically runs, detecting and applying any newer tables or columns defined in the codebase that were added after the template was generated.
5. **Result**: Brand-new schools *always* have 100% of the latest database structure and seed data.

### B. When Developers Add New Features to Existing Schools
When you add new columns, new tables, or new default data to `kampul_sis_client_api`:
* You **do not** have to connect to each school's database manually.
* The API has an **Automated Schema Synchronizer** (`app/core/auto_migrate.py` and `app/main.py`) that runs automatically on server/container startup:
  * **Missing Tables**: If a table exists in SQLAlchemy models (`app/models/`) but not in the database, it runs `CREATE TABLE`.
  * **Missing Columns**: If a column exists in the model but not in the table, it automatically runs:
    ```sql
    ALTER TABLE <table_name> ADD COLUMN <column_name> <type> <nullability>;
    ```
  * **Idempotent Data Seeds**: Startup routines in `app/main.py` and `app/core/schema_check.py` insert missing system settings, permission rows, and default values safely.
* When you pull the latest code on the **OVHcloud VPS** and restart the service, **every school database is updated automatically**.

---

## 2. Developer Action Guide: 3 Common Scenarios

### Scenario 1: Adding a New Column to an Existing Table

#### Step 1: Update the SQLAlchemy Model
Open the corresponding model in `app/models/` and add your new column:
```python
# app/models/student.py
class Student(Base):
    __tablename__ = "students"
    
    # ... existing columns ...
    national_id_number = Column(String(50), nullable=True, index=True) # <-- New Column
```
> [!IMPORTANT]
> When adding columns to existing tables, **always set `nullable=True`** or provide a `server_default` so existing school records do not fail constraint checks.

#### Step 2: (Optional but Recommended for explicit defaults) Register in `schema_check.py`
If your new column requires specific MySQL-level default values or immediate data backfilling, add it to `app/core/schema_check.py`:
```python
# app/core/schema_check.py
students_columns = [
    # ("existing_col", "VARCHAR(50) NULL"),
    ("national_id_number", "VARCHAR(50) NULL"),
]
```

---

### Scenario 2: Adding a Brand-New Table

#### Step 1: Create the SQLAlchemy Model
Create a new file in `app/models/` (e.g. `app/models/certificate.py`):
```python
# app/models/certificate.py
from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from .base import Base

class StudentCertificate(Base):
    __tablename__ = "student_certificates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    certificate_name = Column(String(255), nullable=False)
    issue_date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
```

#### Step 2: Export the Model in `app/models/__init__.py`
Ensure the model is imported into `app/models/__init__.py` and `app/main.py` so that `Base.metadata` registers it:
```python
# app/models/__init__.py
from .certificate import StudentCertificate
```
When the API boots, `sync_database_schema(engine, Base.metadata)` will detect that `student_certificates` is missing in the database and execute `CREATE TABLE` automatically!

---

### Scenario 3: Adding New Default / Seed Reference Data

When a new feature requires default rows (e.g., default branding, new role, or notification template):

#### Step 1: Write an Idempotent Startup Migration in `app/main.py`
Never write plain `INSERT INTO` without conflict handling. Always use `IF NOT EXISTS` or `ON DUPLICATE KEY UPDATE`:
```python
# In app/main.py inside run_database_migrations():
conn.execute(
    text("""
    INSERT INTO system_settings (key, value, description)
    VALUES ('enable_qr_certificates', '1', 'Enable digital student certificate QR verification')
    ON DUPLICATE KEY UPDATE key = key;
""")
)
conn.commit()
```

#### Step 2: Update `template_school_db.sql` for Future Schools
If the table or seed data should also be present in the initial blank database for future signups:
1. Append the table DDL or `INSERT INTO` statement into `e:\kampul\kampul_sis_client_api\template_school_db.sql`.
2. This guarantees new schools get it instantly during provisioning without waiting for startup hooks.

---

## 3. Developer Best Practices Checklist

- [ ] **Always Idempotent**: Ensure every migration, table creation, and insert can be run 100 times without throwing an error (`IF NOT EXISTS`, `ON DUPLICATE KEY UPDATE`).
- [ ] **Never Drop Columns**: Never issue `DROP COLUMN` or `DROP TABLE` in automatic migrations. If a field is deprecated, mark it deprecated in Python schemas and keep the column in MySQL to prevent breaking legacy client versions.
- [ ] **Zero Downtime**: When deploying to the OVHcloud VPS, run:
  ```bash
  git pull origin main
  # Restart service (Docker or Systemd)
  docker compose restart  # or systemctl restart kampul-client-api
  ```
  The startup hook will immediately execute `sync_database_schema`, upgrading the database seamlessly.
- [ ] **Test with Local MySQL**: Always test migrations locally against a copy of a school database before pushing to `main`.
