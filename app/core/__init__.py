"""
Core package for configuration and database setup.
"""

from .config import settings
from .database import engine, SessionLocal, get_db

__all__ = [
    "settings",
    "engine", 
    "SessionLocal",
    "get_db",
]
