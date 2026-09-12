from sqlalchemy import inspect, text, MetaData
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)

def sync_database_schema(engine, metadata: MetaData):
    """
    Synchronizes the database schema with the SQLAlchemy models.
    Creates missing tables and adds missing columns.
    """
    logger.info("Starting automatic database schema synchronization...")
    
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        with engine.connect() as conn:
            for table_name, table in metadata.tables.items():
                if table_name not in existing_tables:
                    logger.info(f"Table '{table_name}' is missing. Creating...")
                    # Set default collation for MySQL to avoid 0900_ai_ci errors on older DBs
                    if engine.dialect.name == 'mysql':
                        if 'mysql_collate' not in table.kwargs:
                            table.kwargs['mysql_collate'] = 'utf8mb4_unicode_ci'
                        if 'mysql_charset' not in table.kwargs:
                            table.kwargs['mysql_charset'] = 'utf8mb4'
                    
                    try:
                        table.create(engine)
                        logger.info(f"✅ Table '{table_name}' created successfully.")
                    except Exception as e:
                        logger.error(f"❌ Failed to create table '{table_name}': {e}")
                else:
                    # Table exists, check columns
                    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
                    for column in table.columns:
                        if column.name not in existing_columns:
                            logger.info(f"Column '{column.name}' is missing in table '{table_name}'. Adding...")
                            
                            try:
                                # Compile the column type to SQL string
                                col_type = column.type.compile(engine.dialect)
                                
                                # Handle Nullability
                                nullable = "NULL" if column.nullable else "NOT NULL"
                                
                                # Handle Defaults (Limited support)
                                default_clause = ""
                                # Note: converting SQLAlchemy default objects to SQL string is complex and risky automatically.
                                # For now, we omit default unless it's a simple value, but that's hard to determine safely.
                                # We stick to adding the column.
                                
                                stmt = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type} {nullable}"
                                
                                conn.execute(text(stmt))
                                logger.info(f"✅ Column '{column.name}' added to '{table_name}'.")
                            except Exception as e:
                                logger.error(f"❌ Failed to add column {column.name} to {table_name}: {e}")
            
            conn.commit()
            
        logger.info("Database schema synchronization completed.")
        
    except Exception as e:
        logger.error(f"Critical error during schema synchronization: {e}")
