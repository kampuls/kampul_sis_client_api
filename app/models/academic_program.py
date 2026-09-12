from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class AcademicProgram(Base):
    """Academic Program model for the PAMA home screen"""
    __tablename__ = "academic_programs"
    
    id = Column(Integer, primary_key=True, index=True)
    program_name = Column(String(100), nullable=False)
    icon_name = Column(String(100), nullable=True)
    custom_logo_url = Column(String(255), nullable=True)
    color_start = Column(String(20), nullable=True)
    color_end = Column(String(20), nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)
    facebook_url = Column(String(255), nullable=True)
    telegram_url = Column(String(255), nullable=True)
    youtube_url = Column(String(255), nullable=True)
    tiktok_url = Column(String(255), nullable=True)
    registration_start_date = Column(Date, nullable=True)
    registration_end_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    images = relationship("AcademicProgramImage", back_populates="program", cascade="all, delete-orphan", order_by="AcademicProgramImage.position")

class AcademicProgramImage(Base):
    """Gallery images for an Academic Program"""
    __tablename__ = "academic_program_images"
    
    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, ForeignKey("academic_programs.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(String(255), nullable=False)
    position = Column(Integer, default=0)
    
    program = relationship("AcademicProgram", back_populates="images")
