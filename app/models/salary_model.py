from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from .base import Base

class AmountType(str, enum.Enum):
    FIXED_AMOUNT = "fixed_amount"
    HOURLY_RATE = "hourly_rate"
    PERCENTAGE = "percentage"

class SalaryHistory(Base):
    __tablename__ = "salary_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    base_salary = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True) # Null means currently active
    reason = Column(String(255), nullable=True) # e.g., Promotion, Annual Raise
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="salary_history")

class SalaryDeduction(Base):
    __tablename__ = "salary_deductions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # If null, applies to global/department scope (future proofing)
    attendance_setting_id = Column(Integer, ForeignKey("attendance_schedules.id"), nullable=True) # Link to schedule? Or keep purely user based for now. User asked for "users must have..."
    
    name = Column(String(100), nullable=False) # e.g., "Tax", "Loan"
    description = Column(String(255), nullable=True)
    type = Column(Enum(AmountType), default=AmountType.FIXED_AMOUNT, nullable=False)
    amount = Column(Float, nullable=False) # The value (money or %)
    
    is_enabled = Column(Boolean, default=True)
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="deductions")

class SalaryBonus(Base):
    __tablename__ = "salary_bonuses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    name = Column(String(100), nullable=False) # e.g., "Performance", "OT"
    description = Column(String(255), nullable=True)
    type = Column(Enum(AmountType), default=AmountType.FIXED_AMOUNT, nullable=False)
    amount = Column(Float, nullable=False)
    
    is_enabled = Column(Boolean, default=True)
    effective_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="bonuses")
