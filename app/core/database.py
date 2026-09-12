from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from .config import settings


# Create database engine with SSL support and connection pooling
connect_args = {}

# Add SSL configuration if provided
ssl_config = settings.ssl_config
if ssl_config:
    # Map SSL configuration to PyMySQL parameters
    if "ssl_ca" in ssl_config:
        connect_args["ssl_ca"] = ssl_config["ssl_ca"]
    if "ssl_cert" in ssl_config:
        connect_args["ssl_cert"] = ssl_config["ssl_cert"]
    if "ssl_key" in ssl_config:
        connect_args["ssl_key"] = ssl_config["ssl_key"]
    if "ssl_disabled" in ssl_config and ssl_config["ssl_disabled"]:
        connect_args["ssl_disabled"] = True

# Production-ready engine configuration
engine_kwargs = {
    "echo": False,  # Disable SQL query logging for cleaner output
    "connect_args": connect_args,
    "poolclass": QueuePool,
    "pool_size": settings.db_pool_size,
    "max_overflow": settings.db_max_overflow,
    "pool_timeout": settings.db_pool_timeout,
    "pool_recycle": settings.db_pool_recycle,
    "pool_pre_ping": True,  # Verify connections before use
}

# Add additional production settings
if settings.is_production:
    engine_kwargs.update({
        "echo": False,  # Never echo SQL in production
        "pool_pre_ping": True,
        "connect_args": {
            **connect_args,
            "charset": "utf8mb4",
            "autocommit": False,
        }
    })

engine = create_engine(settings.database_url, **engine_kwargs)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class is now imported from models.base

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            # Suppress errors during close (e.g. connection already closed)
            pass
