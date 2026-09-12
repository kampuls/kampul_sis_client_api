"""
User model for authentication and user management.
Matches the actual database schema.
"""

from sqlalchemy import Column, Integer, String, DateTime, Numeric, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class User(Base):
    """User model for teachers and administrators."""
    
    __tablename__ = "users"
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Authentication fields
    username = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(100), nullable=False)  # Database has varchar(100), not 255
    email = Column(String(100), nullable=True)  # Database has varchar(100), nullable
    
    # Identification
    uniqueId = Column(String(20), nullable=False)
    
    # URL/path resources managed by StorageService.
    image = Column(String(1000), nullable=True)
    signature = Column(String(1000), nullable=True)
    signatureImagePath = Column(String(500), nullable=True)  # File path for signature image
    
    # Name fields - exact database column names
    kName = Column(String(100), nullable=False)  # Khmer name
    eName = Column(String(100), nullable=False)  # English name
    
    # Physical attributes
    height = Column(Numeric(10, 2), nullable=False)  # decimal(10,2) in database
    gender = Column(String(50), nullable=False)  # varchar(50) in database
    dob = Column(Date, nullable=False)  # date in database, not datetime
    
    # Personal information
    nationality = Column(String(100), nullable=False)
    religion = Column(String(100), nullable=False)
    
    # Current address
    province = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    commune = Column(String(100), nullable=False)
    village = Column(String(100), nullable=True)
    
    # Contact information
    phone = Column(String(100), nullable=True)
    telegramId = Column(String(100), nullable=True)  # varchar(100) in database, not BIGINT
    
    # Permanent address
    pProvince = Column(String(50), nullable=True)
    pDistrict = Column(String(50), nullable=True)
    pCommune = Column(String(50), nullable=True)
    pVillage = Column(String(50), nullable=True)
    
    # Identity card information
    identityNumber = Column(String(100), nullable=True)
    identityRegDate = Column(Date, nullable=True)
    identityEndDate = Column(Date, nullable=True)
    identityRegPlace = Column(String(100), nullable=True)
    
    # Family information
    fatherName = Column(String(100), nullable=True)
    motherName = Column(String(100), nullable=True)
    
    # Work information
    departmentId = Column(Integer, nullable=True)
    positionId = Column(Integer, nullable=True)
    startWork = Column(String(50), nullable=True)  # varchar(50) in database, not DateTime
    endWork = Column(String(50), nullable=True)  # varchar(50) in database, not DateTime
    education = Column(String(100), nullable=False)
    
    # Workplace and role - exact database column names (not workplace_id/role_id)
    workplace = Column(Integer, nullable=False)  # int(11) NOT NULL in database
    status = Column(Integer, nullable=False)  # int(11) NOT NULL in database (not is_active Boolean)
    role = Column(Integer, nullable=False)  # int(11) NOT NULL in database (not role_id)

    # Session / token version for JWT revocation
    token_version = Column(Integer, nullable=True, default=1)
    
    # Additional fields
    isForeigner = Column(Integer, nullable=False)  # int(11) NOT NULL in database

    # Banking Information
    bankAccountNumber = Column(String(50), nullable=True)
    bankAccountName = Column(String(100), nullable=True)
    bankName = Column(String(100), nullable=True)

    # Payroll Information
    baseSalary = Column(Numeric(10, 2), nullable=True)  # Current active salary

    # Identification & Social Security
    nssfNumber = Column(String(50), nullable=True)
    isNssf = Column(Integer, nullable=True, default=0)  # Employee NSSF? (1=Yes, 0=No)
    isResident = Column(Integer, nullable=True, default=1)  # Resident status (1=Yes, 0=No)

    # Family Status
    hasSpouse = Column(Integer, nullable=True, default=0)  # 1=Yes, 0=No
    numberOfDependents = Column(Integer, nullable=True, default=0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at = Column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    attendance_audit_logs = relationship("AttendanceAuditLog", back_populates="user", cascade="all, delete-orphan")

    # Relationships are not defined here because the database doesn't have foreign key constraints.
    # The workplace and role columns are just integers, not foreign keys.
    # If relationships are needed, they should be defined using primaryjoin in the Branch/Role models.
    
    # Properties for backward compatibility (database uses status/role as integers)
    @property
    def is_active(self) -> bool:
        """Check if user is active (status == 1)."""
        status_val = getattr(self, 'status', 0)
        return status_val == 1
    
    @is_active.setter
    def is_active(self, value: bool):
        """Set user active status."""
        self.status = 1 if value else 0
    
    @property
    def is_admin(self) -> bool:
        """Check if user is admin (role == 1)."""
        role_val = getattr(self, 'role', 0)
        return role_val == 1
    
    @is_admin.setter
    def is_admin(self, value: bool):
        """Set user admin status."""
        self.role = 1 if value else self.role
    
    # Alias properties for compatibility with code expecting workplace_id/role_id
    @property
    def workplace_id(self) -> int:
        """Get workplace ID (alias for workplace)."""
        workplace_val = getattr(self, 'workplace', 0)
        return workplace_val
    
    @workplace_id.setter
    def workplace_id(self, value: int):
        """Set workplace ID (alias for workplace)."""
        self.workplace = value
    
    @property
    def role_id(self) -> int:
        """Get role ID (alias for role)."""
        role_val = getattr(self, 'role', 0)
        return role_val
    
    @role_id.setter
    def role_id(self, value: int):
        """Set role ID (alias for role)."""
        self.role = value

    # Leave Management Relationships
    leave_requests = relationship("LeaveRequest", foreign_keys="[LeaveRequest.user_id]", back_populates="user")
    approved_requests = relationship("LeaveRequest", foreign_keys="[LeaveRequest.approver_id]", back_populates="approver")
    leave_balances = relationship("LeaveBalance", back_populates="user")
    leave_approver_config = relationship("LeaveApprover", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', eName='{self.eName}', kName='{self.kName}')>"
