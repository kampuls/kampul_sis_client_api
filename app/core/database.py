import logging
import re
import threading
import time
import urllib.parse
from typing import Dict, Optional, Set

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from .config import settings

logger = logging.getLogger(__name__)

# Create database engine with SSL support and connection pooling
connect_args = {}

# Add SSL configuration if provided
ssl_config = settings.ssl_config
if ssl_config:
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

# Default root/fallback engine
engine: Engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal: sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Multi-tenant engine cache & discovery
_engines_lock = threading.Lock()
_tenant_engines: Dict[str, Engine] = {settings.db_name: engine}
_tenant_sessions: Dict[str, sessionmaker] = {settings.db_name: SessionLocal}
_known_databases: Set[str] = {settings.db_name}
_last_db_scan_time: float = 0.0


def make_database_url(db_name: str) -> str:
    """Builds a MySQL connection URL targeting a specific tenant database."""
    encoded_pwd = urllib.parse.quote_plus(settings.db_password)
    return f"mysql+pymysql://{settings.db_user}:{encoded_pwd}@{settings.db_host}:{settings.db_port}/{db_name}"


def refresh_known_databases() -> None:
    """Queries MySQL schemata to find all provisioned school databases (sis_*)."""
    global _last_db_scan_time
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'sis_%' OR schema_name = :default_db"),
                {"default_db": settings.db_name}
            ).fetchall()
            found = {r[0] for r in rows if r and r[0]}
            with _engines_lock:
                _known_databases.update(found)
                _last_db_scan_time = time.time()
    except Exception as ex:
        logger.warning(f"Failed to refresh known tenant databases: {ex}")


def is_valid_database(candidate_db: str) -> bool:
    """Checks if a candidate database exists in MySQL."""
    global _last_db_scan_time
    if not candidate_db:
        return False
    if candidate_db == settings.db_name:
        return True
    if candidate_db in _known_databases:
        return True

    now = time.time()
    # Cache miss: query MySQL at most once every 10 seconds
    if now - _last_db_scan_time > 10.0 or len(_known_databases) <= 1:
        refresh_known_databases()

    return candidate_db in _known_databases


def resolve_tenant_db_name(request: Optional[Request] = None) -> str:
    """
    Extracts and validates the target tenant database name from HTTP request headers.
    Supports Host subdomain routing, x-tenant-db, and x-tenant-subdomain headers.
    Falls back safely to the primary default database (kampul_sis_client_db).
    """
    if request is None:
        return settings.db_name

    # 1. Direct explicit database header override
    explicit_db = request.headers.get("x-tenant-db") or request.headers.get("x-tenant-database")
    if explicit_db:
        clean_db = re.sub(r"[^a-zA-Z0-9_]", "", explicit_db.strip().lower())
        if clean_db and is_valid_database(clean_db):
            return clean_db

    # 2. Subdomain header override
    explicit_sub = request.headers.get("x-tenant-subdomain") or request.headers.get("x-school-slug")
    if explicit_sub:
        clean_sub = re.sub(r"[^a-z0-9]", "_", explicit_sub.strip().lower()).strip("_")
        candidate = f"sis_{clean_sub}"
        if is_valid_database(candidate):
            return candidate

    # 3. Dynamic Host header parsing (e.g. kmao.sis.kampul.com, angkor.sis.kampul.com)
    host_header = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    host = host_header.split(":")[0].strip().lower()

    if host and "." in host:
        subdomain = host.split(".")[0]
        # Skip generic and central management hostnames
        if subdomain not in ("sis", "api", "www", "admin", "central", "mail", "localhost", "royal"):
            clean_sub = re.sub(r"[^a-z0-9]", "_", subdomain).strip("_")
            candidate = f"sis_{clean_sub}"
            if is_valid_database(candidate):
                return candidate

    return settings.db_name


def get_tenant_session_factory(db_name: str) -> sessionmaker:
    """Retrieves or creates a thread-safe connection pool & sessionmaker for a tenant database."""
    if db_name in _tenant_sessions:
        return _tenant_sessions[db_name]

    with _engines_lock:
        if db_name in _tenant_sessions:
            return _tenant_sessions[db_name]

        url = make_database_url(db_name)
        tenant_engine = create_engine(url, **engine_kwargs)
        factory = sessionmaker(autocommit=False, autoflush=False, bind=tenant_engine)
        _tenant_engines[db_name] = tenant_engine
        _tenant_sessions[db_name] = factory
        logger.info(f"Initialized dynamic connection pool for tenant database: `{db_name}`")
        return factory


def get_db(request: Request = None):
    """
    FastAPI dependency that yields a database session bound to the active school tenant database.
    Seamlessly multi-tenant: routes dynamically per school hostname with zero configuration.
    """
    db_name = resolve_tenant_db_name(request)
    session_factory = get_tenant_session_factory(db_name)
    db: Session = session_factory()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
