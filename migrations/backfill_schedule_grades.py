"""
Backfill grade_id for existing learning_class_schedules records.
This script updates schedules that don't have grade_id populated.
"""
import os
from sqlalchemy import create_engine, text

def backfill_grades():
    """Backfill grade_id for existing schedules."""
    # Get database URL from environment or use default
    db_url = os.getenv("PAMA_DB_URL", "mysql+pymysql://root:@localhost:3306/pamais")
    
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        
        try:
            # Update schedules with missing grade_id
            update_query = text("""
                UPDATE learning_class_schedules lcs
                JOIN grade g ON g.group_id = lcs.grade_group_id 
                    AND g.academic_id = lcs.academic_id
                SET lcs.grade_id = g.id
                WHERE lcs.grade_id IS NULL
                LIMIT 1
            """)
            
            result = conn.execute(update_query)
            affected_rows = result.rowcount
            
            # Commit transaction
            trans.commit()
            
            print(f"✅ Updated {affected_rows} schedule records with grade_id")
            
        except Exception as e:
            # Rollback on error
            trans.rollback()
            print(f"❌ Error backfilling grades: {e}")
            raise

if __name__ == "__main__":
    backfill_grades()
