from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, func
from .base import Base

class WorkLocation(Base):
    __tablename__ = "work_locations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    latitude = Column(Float(10, 8), nullable=False)
    longitude = Column(Float(11, 8), nullable=False)
    radius_meters = Column(Integer, nullable=False, default=100)
    branch_id = Column(Integer, nullable=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<WorkLocation(name='{self.name}', lat={self.latitude}, lng={self.longitude})>"
