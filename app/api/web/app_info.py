"""App-level endpoints for the Web Dashboard"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from ...core import get_db

router = APIRouter()

@router.get("/social-links")
async def get_social_links(db: Session = Depends(get_db)):
    """
    Returns global social media links for the web application.
    Independent from the mobile v1 API.
    """
    try:
        # Check if the columns exist first to prevent errors before migration
        check_query = text("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'settings'
            AND COLUMN_NAME = 'facebook_url'
        """)
        
        has_columns = db.execute(check_query).fetchone() is not None
        
        if not has_columns:
            return {
                "facebook": None,
                "telegram": None,
                "youtube": None,
                "instagram": None,
                "tiktok": None
            }
            
        # Get settings row
        query = text("""
            SELECT facebook_url, telegram_url, youtube_url, instagram_url, tiktok_url
            FROM settings 
            LIMIT 1
        """)
        result = db.execute(query).fetchone()

        if result:
            return {
                "facebook": result[0],
                "telegram": result[1],
                "youtube": result[2],
                "instagram": result[3],
                "tiktok": result[4]
            }
            
        return {
            "facebook": None,
            "telegram": None,
            "youtube": None,
            "instagram": None,
            "tiktok": None
        }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching web social links: {e}")
        return {
            "facebook": None,
            "telegram": None,
            "youtube": None,
            "instagram": None,
            "tiktok": None
        }
