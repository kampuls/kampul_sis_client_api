from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text("ALTER TABLE forms ADD COLUMN start_date DATETIME NULL"))
    db.commit()
    print("Added start_date column to forms table.")
except Exception as e:
    print(f"start_date exists or error: {e}")
    db.rollback()

try:
    db.execute(text("ALTER TABLE forms ADD COLUMN end_date DATETIME NULL"))
    db.commit()
    print("Added end_date column to forms table.")
except Exception as e:
    print(f"end_date exists or error: {e}")
    db.rollback()

db.close()
