import logging
from urllib.parse import urlparse
from pathlib import Path

# This file sits at pama_api/app/utils/file_utils.py
# Resolving 3 parents goes to pama_api root directory 
BASE_DIR = Path(__file__).resolve().parent.parent.parent

def delete_local_file(file_url: str):
    """
    Safely delete a local or cloud file by routing to StorageService.
    Handles None and non-string inputs safely.
    """
    if not file_url or not isinstance(file_url, str):
        return
        
    try:
        from ..core import SessionLocal
        from ..models.settings import SystemSettings
        from ..services.storage_service import StorageService
        
        with SessionLocal() as db:
            settings = db.query(SystemSettings).first()
            if settings:
                StorageService.delete_file(file_url, settings)
            else:
                # Fallback to true local deletion if settings absent
                StorageService.delete_local_file(file_url)
                
    except Exception as e:
        logging.error(f"Failed to route file deletion for url {file_url}: {e}")
