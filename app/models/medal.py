from sqlalchemy import Column, Integer, String, DateTime, DECIMAL, ForeignKey, text
from sqlalchemy.orm import relationship
from .base import Base

class MedalName(Base):
    __tablename__ = "medalname"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    medal_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

class MedalPrice(Base):
    __tablename__ = "medal_price"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name_us = Column(String(100), nullable=False)
    name_kh = Column(String(100), nullable=False)
    amount = Column(DECIMAL(65, 2), nullable=False)
    academic_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

class Medal(Base):
    __tablename__ = "medals"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cer_no = Column(String(100), nullable=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    medal_type = Column(String(100), nullable=False)
    medal_name = Column(String(100), nullable=True)
    medal_price_id = Column(Integer, ForeignKey("medal_price.id"), nullable=False)
    academic_id = Column(Integer, nullable=False)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))

    # Relationships
    student = relationship("Student", foreign_keys=[student_id], backref="medals")
    medal_price = relationship("MedalPrice", foreign_keys=[medal_price_id])
