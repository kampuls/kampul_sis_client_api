from sqlalchemy import Boolean, Column, Integer, String, Time, Enum, Text
from .base import Base

class SystemSettings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identity
    system_name = Column(String(100), nullable=True)
    enterpriseName = Column(String(200), nullable=True)
    eProvince = Column(String(100), nullable=True)
    prefixid = Column(String(200), nullable=False)
    suffix = Column(String(100), nullable=True)
    digit_number = Column(Integer, nullable=True, default=6)
    academicid = Column(Integer, nullable=False)
    startid = Column(Integer, nullable=True)
    
    # Behavior
    follow_type = Column(Enum('settings', 'branch'), nullable=False, default='settings')
    # Remote kill switch for Shorebird. A missing/NULL value is always treated
    # as disabled by the public update-config endpoint.
    ota_updates_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    
    # Exchange
    status_fixedexchange = Column(String(3), nullable=False, default='no')
    default_exchange = Column(Integer, nullable=False, default=4100)
    
    # Social Links
    facebook_url = Column(String(255), nullable=True)
    telegram_url = Column(String(255), nullable=True)
    youtube_url = Column(String(255), nullable=True)
    instagram_url = Column(String(255), nullable=True)
    tiktok_url = Column(String(255), nullable=True)
    
    # Reporting
    time_report = Column(Time, nullable=True)
    report_chat_id = Column(String(25), nullable=True)
    report_status = Column(String(11), nullable=True)
    notify_parents = Column(String(11), nullable=True, default='no')
    
    # Timings / Schedule
    time_allow_start = Column(Time, nullable=False)
    time_allow_end = Column(Time, nullable=False)
    skip_sat = Column(String(11), nullable=True)
    skip_sun = Column(String(11), nullable=True)
    marks_extraday = Column(String(15), nullable=True, default='5')
    enable_schedule_reminders = Column(String(11), nullable=True, default='yes')
    
    # Cloud Storage Configuration
    active_storage_provider = Column(String(50), nullable=False, default='local') # 'local', 'cloudinary', 'firebase', 's3'
    
    cloudinary_cloud_name = Column(String(255), nullable=True)
    cloudinary_api_key = Column(String(255), nullable=True)
    cloudinary_api_secret = Column(String(255), nullable=True)
    
    aws_access_key_id = Column(String(255), nullable=True)
    aws_secret_access_key = Column(String(255), nullable=True)
    aws_region_name = Column(String(100), nullable=True)
    aws_bucket_name = Column(String(255), nullable=True)
    
    firebase_storage_bucket = Column(String(255), nullable=True)
    firebase_service_account_json = Column(Text, nullable=True)

    # Security toggles an administrator can flip from the app, without a
    # redeploy. NULL means "not set" and the environment default applies.
    phone_conflict_lock_enabled = Column(Boolean, nullable=True)
