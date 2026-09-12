"""
Cleanup script: Remove phantom marks_semester records.

A 'phantom' record is one where:
  - average = 0.0
  - AND there are no linked marks_semester_monthlies entries that point to a 
    marks_monthly record with a non-zero average

These records were created by an earlier bug where months with zero averages
were incorrectly treated as real data. This caused RSEM1 to appear in the
database even for students who had never entered any marks.

Run from the pama_api root directory:
    python -m scripts.cleanup_phantom_semester_records
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_phantom_semester_records(dry_run: bool = True):
    """
    Find and delete marks_semester records where average = 0 and
    no valid (non-zero) monthly marks are linked.

    Args:
        dry_run: If True, only print what would be deleted without deleting.
    """
    db = SessionLocal()
    try:
        logger.info(f"Starting cleanup {'(DRY RUN)' if dry_run else '(LIVE)'}")

        # Find all marks_semester records where average = 0 or average IS NULL
        phantom_query = text("""
            SELECT 
                ms.id, 
                ms.exam_name, 
                ms.student_id, 
                ms.academic_id, 
                ms.average,
                ecs.sign_code
            FROM marks_semester ms
            LEFT JOIN exam_calculate_sign ecs 
                ON ecs.result_name = ms.exam_name 
                AND ecs.academic_id = ms.academic_id
                AND ecs.program_id = ms.program_id
                AND ecs.grade_group_id = ms.grade_group_id
                AND ecs.sign_code IN ('RSEM1', 'RSEM2')
            WHERE (ms.average = 0 OR ms.average IS NULL)
              AND ecs.sign_code IS NOT NULL
            ORDER BY ms.student_id, ms.academic_id
        """)

        candidates = db.execute(phantom_query).fetchall()
        logger.info(f"Found {len(candidates)} zero-average semester records to evaluate.")

        phantom_ids_to_delete = []

        for row in candidates:
            ms_id = row[0]
            exam_name = row[1]
            student_id = row[2]
            academic_id = row[3]
            average = row[4]
            sign_code = row[5]

            # Check if any linked marks_monthly has a non-zero average
            valid_monthly_check = text("""
                SELECT COUNT(*) 
                FROM marks_semester_monthlies msm
                JOIN marks_monthly mm ON mm.id = msm.marks_monthly_id
                WHERE msm.marks_semester_id = :ms_id
                  AND mm.average IS NOT NULL
                  AND mm.average > 0
            """)
            valid_count = db.execute(valid_monthly_check, {"ms_id": ms_id}).scalar()

            if valid_count == 0:
                phantom_ids_to_delete.append(ms_id)
                logger.info(
                    f"  [PHANTOM] marks_semester id={ms_id}, student={student_id}, "
                    f"academic={academic_id}, exam='{exam_name}', sign={sign_code}, avg={average}"
                )

        logger.info(f"\nTotal phantom records to delete: {len(phantom_ids_to_delete)}")

        if not phantom_ids_to_delete:
            logger.info("Nothing to clean up!")
            return

        if dry_run:
            logger.info("DRY RUN complete. No records deleted. Re-run with dry_run=False to delete.")
            return

        # Perform deletion
        for ms_id in phantom_ids_to_delete:
            # Delete junction entries first
            db.execute(
                text("DELETE FROM marks_semester_monthlies WHERE marks_semester_id = :id"),
                {"id": ms_id}
            )
            # Delete the phantom semester record
            db.execute(
                text("DELETE FROM marks_semester WHERE id = :id"),
                {"id": ms_id}
            )
            logger.info(f"  Deleted marks_semester id={ms_id}")

        db.commit()
        logger.info(f"\nCleanup complete! Deleted {len(phantom_ids_to_delete)} phantom records.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # Default to dry_run=True for safety. Pass '--live' argument to actually delete.
    live = "--live" in sys.argv
    cleanup_phantom_semester_records(dry_run=not live)
    print("\nUsage:")
    print("  python -m scripts.cleanup_phantom_semester_records          # dry run")
    print("  python -m scripts.cleanup_phantom_semester_records --live   # actually delete")
