"""
Financial Models
SQLAlchemy models for financial information.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, func, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base


class UserFinancials(Base):
    """User financial information model (separated from main user table)"""

    __tablename__ = "user_financials"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, unique=True)

    # Banking Information
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_name = Column(String(100), nullable=True)

    # Social Security
    nssf_number = Column(String(50), nullable=True)
    nssf_employee_id = Column(String(50), nullable=True)

    # Family Status
    spouse_status = Column(Boolean, nullable=True, default=False)
    dependent_count = Column(Integer, nullable=True, default=0)

    # Resident Status
    is_resident = Column(Boolean, nullable=True, default=True)

    # Salary Information
    base_salary = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Note: Financial columns are now directly in User table
    # No relationship needed

    def __repr__(self):
        return f"<UserFinancials(user_id={self.user_id}, bank_name='{self.bank_name}')>"


class BonusDeductionRules(Base):
    """Rules for bonuses and deductions"""

    __tablename__ = "bonus_deduction_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)  # 'bonus' or 'deduction'
    calculation_type = Column(String(50), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    is_active = Column(Boolean, nullable=True, default=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<BonusDeductionRules(name='{self.name}', type='{self.type}', amount={self.amount})>"
