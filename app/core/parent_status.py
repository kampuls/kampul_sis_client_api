"""Ensure parents.status exists (startup migration may not have run yet)."""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_parent_status_column(db: Session) -> None:
    """Add parents.status if missing so pending registration works."""
    try:
        inspector = inspect(db.connection())
        if "parents" not in inspector.get_table_names():
            return
        column_names = {col["name"] for col in inspector.get_columns("parents")}
        if "status" in column_names:
            return
        logger.info("Adding status column to parents table (runtime ensure)...")
        db.execute(
            text("ALTER TABLE parents ADD COLUMN status INT NOT NULL DEFAULT 1")
        )
        try:
            db.execute(text("CREATE INDEX ix_parents_status ON parents(status)"))
        except Exception:
            pass
        db.commit()
        logger.info("Added parents.status column")
    except Exception as e:
        db.rollback()
        logger.error(f"ensure_parent_status_column failed: {e}")
        raise
