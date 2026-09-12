import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

# Setup database connection
DATABASE_URL = settings.database_url
if not DATABASE_URL:
    print("Error: DATABASE_URL not found in config")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
UPLOAD_DIR = Path("uploads/signatures")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def migrate_signatures():
    print("Starting signature migration...")
    
    with engine.connect() as conn:
        # Get users with blobs but no file path yet
        result = conn.execute(text("""
            SELECT id, signature 
            FROM users 
            WHERE signature IS NOT NULL 
              AND LENGTH(signature) > 0 
              AND (signatureImagePath IS NULL OR signatureImagePath = '')
        """))
        
        users_with_blobs = result.fetchall()
        print(f"Found {len(users_with_blobs)} users with blob signatures to migrate.")
        
        migrated_count = 0
        for row in users_with_blobs:
            user_id = row[0]
            blob_data = row[1]
            
            try:
                # Save blob to file
                filename = f"sig_{user_id}.png"
                file_path = UPLOAD_DIR / filename
                
                with open(file_path, "wb") as f:
                    f.write(blob_data)
                
                # Update database
                db_path = f"uploads/signatures/{filename}"
                conn.execute(
                    text("UPDATE users SET signatureImagePath = :path WHERE id = :id"),
                    {"path": db_path, "id": user_id}
                )
                
                migrated_count += 1
                if migrated_count % 10 == 0:
                    print(f"Migrated {migrated_count} signatures...")
                    
            except Exception as e:
                print(f"Failed to migrate signature for user {user_id}: {e}")
                
        conn.commit()
    
    print(f"Migration complete! Successfully migrated {migrated_count} signatures out of {len(users_with_blobs)}.")

if __name__ == "__main__":
    migrate_signatures()
