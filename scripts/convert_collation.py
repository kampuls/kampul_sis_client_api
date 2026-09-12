from sqlalchemy import text, inspect
import sys
import os

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine

def convert_database_collation():
    print("Connecting to the database...")
    
    with engine.connect() as conn:
        inspector = inspect(engine)
        
        # We only do this for MySQL
        if engine.dialect.name != 'mysql':
            print(f"Skipping: This is a {engine.dialect.name} database, not MySQL.")
            return

        # Get current database name
        db_name_result = conn.execute(text("SELECT DATABASE()"))
        db_name = db_name_result.scalar()
        
        if not db_name:
            print("Could not determine database name.")
            return
            
        print(f"Converting tables in database: {db_name} to utf8mb4_unicode_ci...")
        
        # Update the database default collation
        try:
            conn.execute(text(f"""
                ALTER DATABASE `{db_name}` 
                CHARACTER SET utf8mb4 
                COLLATE utf8mb4_unicode_ci;
            """))
            print(f"✓ Updated database `{db_name}` default collation.")
        except Exception as e:
            print(f"Warning: Could not update database default collation: {e}")

        # Get all tables
        tables = inspector.get_table_names()
        
        # Convert each table
        for table in tables:
            try:
                # This converts the table's default collation AND all of its character string columns
                conn.execute(text(f"""
                    ALTER TABLE `{table}` 
                    CONVERT TO CHARACTER SET utf8mb4 
                    COLLATE utf8mb4_unicode_ci;
                """))
                print(f"  ✓ Converted table: {table}")
            except Exception as e:
                print(f"  ✗ Failed to convert table {table}: {e}")
                
        conn.commit()
        print("\nAll done! You should now be able to transfer your database without the 1273 error.")

if __name__ == "__main__":
    convert_database_collation()
