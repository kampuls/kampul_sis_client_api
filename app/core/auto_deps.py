"""Auto-dependency management and dynamic installer helper."""

from __future__ import annotations

import importlib
import logging
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

REQUIRED_PACKAGES = [
    ("yt_dlp", "yt-dlp>=2026.6.9"),
    ("telethon", "telethon>=1.36.0"),
    ("phonenumbers", "phonenumbers==9.0.30"),
    ("firebase_admin", "firebase-admin==6.5.0"),
    ("cloudinary", "cloudinary==1.41.0"),
    ("boto3", "boto3==1.35.0"),
    ("apscheduler", "apscheduler==3.10.4"),
    ("openai", "openai==1.55.0"),
    ("pypdf", "pypdf==4.0.1"),
    ("docx", "python-docx==1.1.2"),
    ("openpyxl", "openpyxl==3.1.2"),
    ("pptx", "python-pptx==1.0.2"),
    ("PIL", "Pillow>=11.0.0"),
    ("redis", "redis==5.0.3"),
]


def ensure_package(module_name: str, install_spec: Optional[str] = None) -> bool:
    """Ensure a Python package is installed; auto-install via pip if missing."""
    install_name = install_spec or module_name
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        logger.info(f"Package '{module_name}' missing. Auto-installing '{install_name}'...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", install_name],
                check=True,
                capture_output=True,
                text=True,
            )
            importlib.import_module(module_name)
            logger.info(f"✅ Successfully auto-installed '{install_name}'")
            return True
        except Exception as e:
            logger.warning(f"❌ Failed to auto-install '{install_name}': {e}")
            return False


def auto_check_and_install_dependencies():
    """Verify and auto-install essential runtime packages on server startup."""
    for mod_name, spec in REQUIRED_PACKAGES:
        ensure_package(mod_name, spec)
