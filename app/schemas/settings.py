from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import time

class SettingsBase(BaseModel):
    # Identity
    system_name: Optional[str] = None
    enterpriseName: Optional[str] = None
    eProvince: Optional[str] = None
    prefixid: str
    suffix: Optional[str] = None
    digit_number: Optional[int] = 6
    academicid: int
    startid: Optional[int] = None
    
    # Behavior
    follow_type: str = 'settings'
    
    # Exchange
    status_fixedexchange: str = 'no'
    default_exchange: int = 4100
    
    # Timings and Rules
    time_allow_start: time
    time_allow_end: time
    skip_sat: Optional[str] = None
    skip_sun: Optional[str] = None
    marks_extraday: Optional[str] = '5'
    enable_schedule_reminders: Optional[str] = 'yes'
    
    # Reporting
    time_report: Optional[time] = None
    report_chat_id: Optional[str] = None
    report_status: Optional[str] = None
    notify_parents: Optional[str] = 'no'
    
    # Social
    facebook_url: Optional[str] = None
    telegram_url: Optional[str] = None
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None
    tiktok_url: Optional[str] = None
    
    # Cloud Storage Configuration
    active_storage_provider: str = 'local'
    
    cloudinary_cloud_name: Optional[str] = None
    cloudinary_api_key: Optional[str] = None
    cloudinary_api_secret: Optional[str] = None
    
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region_name: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    
    firebase_storage_bucket: Optional[str] = None
    firebase_service_account_json: Optional[str] = None

class SettingsUpdate(SettingsBase):
    pass

class SettingsResponse(SettingsBase):
    id: int
    
    class Config:
        from_attributes = True
