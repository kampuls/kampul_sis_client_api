import os
import sys
import asyncio
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add app directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal

UPLOAD_DIR = "uploads/branches"

async def migrate_branch_images():
    logger.info("Starting Branch Images Migration...")
    
    # Create uploads directory if it doesn't exist
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    db = SessionLocal()
    try:
        # Check if new columns exist first
        try:
            db.execute(text("SELECT image_header_path FROM branch LIMIT 1"))
        except Exception:
            logger.error("Branch path columns don't exist yet! Run the API server first to auto-migrate the table schema.")
            return

        # Get branches
        result = db.execute(text("SELECT id, branch_name, image_header, director_signature, headTeacher_signature, stamp FROM branch"))
        branches = result.mappings().all()
        
        migrated_count = 0
        
        for branch in branches:
            branch_id = branch['id']
            updates = {}
            
            # Helper to process image column
            def process_image(col_name, path_col_name):
                blob_data = branch[col_name]
                if blob_data:
                    file_path = f"{UPLOAD_DIR}/branch_{branch_id}_{col_name}.png"
                    try:
                        with open(file_path, "wb") as f:
                            f.write(blob_data)
                        updates[path_col_name] = file_path
                        logger.info(f"    Saved {col_name} to {file_path}")
                    except Exception as e:
                        logger.error(f"    Failed to save {col_name} for branch {branch_id}: {str(e)}")

            process_image('image_header', 'image_header_path')
            process_image('director_signature', 'director_signature_path')
            process_image('headTeacher_signature', 'headTeacher_signature_path')
            process_image('stamp', 'stamp_path')
            
            # Update the branch record
            if updates:
                set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                params = {"id": branch_id, **updates}
                db.execute(
                    text(f"UPDATE branch SET {set_clause} WHERE id = :id"),
                    params
                )
                migrated_count += 1
                logger.info(f"✅ Migrated images for branch ID {branch_id}")
            else:
                logger.info(f"⏭️ No images to migrate for branch ID {branch_id}")
                
        db.commit()
        logger.info(f"Migration completed successfully. Updated {migrated_count} branches.")

    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(migrate_branch_images())
