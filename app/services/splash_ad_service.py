from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional

from ..models.splash_ad import SplashAd
from ..schemas.splash_ad import SplashAdCreate, SplashAdUpdate

class SplashAdService:
    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[SplashAd]:
        return db.query(SplashAd).order_by(SplashAd.id.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, db: Session, ad_id: int) -> Optional[SplashAd]:
        return db.query(SplashAd).filter(SplashAd.id == ad_id).first()

    def get_active_ad(self, db: Session) -> Optional[SplashAd]:
        """
        Get the currently active splash ad.
        It must be marked is_active=True, and the current time must fall 
        between start_date (if set) and end_date (if set).
        If multiple match, returns the most recently updated one.
        """
        now = datetime.utcnow()
        query = db.query(SplashAd).filter(SplashAd.is_active == True)
        
        # Filter by start_date (if start_date is null, it's considered started)
        query = query.filter(
            (SplashAd.start_date == None) | (SplashAd.start_date <= now)
        )
        
        # Filter by end_date (if end_date is null, it's considered never-ending)
        query = query.filter(
            (SplashAd.end_date == None) | (SplashAd.end_date >= now)
        )
        
        return query.order_by(SplashAd.updated_at.desc()).first()

    def create(self, db: Session, ad_in: SplashAdCreate) -> SplashAd:
        db_ad = SplashAd(**ad_in.model_dump())
        db.add(db_ad)
        db.commit()
        db.refresh(db_ad)
        return db_ad

    def update(self, db: Session, db_ad: SplashAd, ad_in: SplashAdUpdate) -> SplashAd:
        update_data = ad_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_ad, field, value)
            
        db.add(db_ad)
        db.commit()
        db.refresh(db_ad)
        return db_ad

    def delete(self, db: Session, db_ad: SplashAd) -> SplashAd:
        db.delete(db_ad)
        db.commit()
        return db_ad

splash_ad_service = SplashAdService()
