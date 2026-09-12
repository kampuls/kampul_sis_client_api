from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey, func
from sqlalchemy.orm import relationship
from .base import Base

class Ad(Base):
    __tablename__ = "ads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=False)
    image_path = Column(String(500), nullable=True)
    
    ad_type = Column(String(50), nullable=False, default='general')
    action_type = Column(String(50), nullable=True)
    action_data = Column(JSON, nullable=True)
    
    button_text = Column(String(100), nullable=True)
    button_color = Column(String(20), default='#1976D2')
    
    target_audience = Column(String(50), default='all')
    
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    
    click_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)
    
    created_by = Column(Integer, nullable=True)
    academic_id = Column(Integer, nullable=True)
    branch_id = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Ad(title='{self.title}')>"

class AdClick(Base):
    __tablename__ = "ad_clicks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ad_id = Column(Integer, ForeignKey('ads.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    user_type = Column(String(50), nullable=True)
    clicked_at = Column(DateTime, server_default=func.now())
    device_info = Column(String(255), nullable=True)
    
    ad = relationship("Ad")

    def __repr__(self):
        return f"<AdClick(ad_id={self.ad_id}, user_id={self.user_id})>"


class SmartDownloadLink(Base):
    __tablename__ = "smart_download_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(32), nullable=False, unique=True, index=True)

    android_url = Column(Text, nullable=False)
    ios_url = Column(Text, nullable=False)

    created_at = Column(DateTime, server_default=func.now())
