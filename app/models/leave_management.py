"""
Leave Management Models
SQLAlchemy models for leave management system.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, Float, ForeignKey, Table, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from .base import Base

# Association table for leave policy and leave types (many-to-many)
leave_policy_leave_type_association = Table(
    'leave_policy_leave_type_association',
    Base.metadata,
    Column('leave_policy_id', Integer, ForeignKey('leave_policies.id'), primary_key=True),
    Column('leave_type_id', Integer, ForeignKey('leave_types.id'), primary_key=True)
)

class LeaveType(Base):
    """Leave type model (Annual, Sick, Personal, etc.)"""
    __tablename__ = "leave_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    max_days_per_year = Column(Float, nullable=False, default=0)
    # Monthly policy cap. Days beyond this amount inside one calendar month are
    # still granted, but they cost no annual allowance and are recorded as
    # unpaid (see LeaveRequestDay.unpaid_cost). NULL or 0 disables the policy.
    max_days_per_month = Column(Float, nullable=True)
    is_paid = Column(Boolean, default=True)
    requires_approval = Column(Boolean, default=True)
    # When true, asking this leave requires uploading a proof image.
    requires_proof = Column(Boolean, nullable=True, default=False)
    # Nullable so auto-migrate can add it to existing rows; treat NULL as active.
    is_active = Column(Boolean, nullable=True, default=True)
    # Employee balance cards use this stable admin-configured presentation.
    # NULL preserves creation-date ordering until the migration backfills it.
    display_order = Column(Integer, nullable=True)
    color_hex = Column(String(7), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leave_requests = relationship("LeaveRequest", back_populates="leave_type")
    leave_balances = relationship("LeaveBalance", back_populates="leave_type")
    policies = relationship("LeavePolicy", secondary=leave_policy_leave_type_association, back_populates="leave_types")
    allocations = relationship("LeaveTypeAllocation", back_populates="leave_type")


class LeaveTypeAllocation(Base):
    """Allowed days for a leave type in a specific academic year.

    The active academic year id lives in settings.academicid. Balances are
    computed dynamically: allocated_days - SUM(approved leave_request_days.day_cost)
    for requests in that academic year (leave_balances table is not used).
    """
    __tablename__ = "leave_type_allocations"
    __table_args__ = (
        UniqueConstraint('leave_type_id', 'academic_id', name='uq_leave_alloc_type_academic'),
    )

    id = Column(Integer, primary_key=True, index=True)
    leave_type_id = Column(Integer, ForeignKey('leave_types.id'), nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)  # references legacy academic.id
    allocated_days = Column(Float, nullable=False, default=0)
    is_active = Column(Boolean, nullable=True, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leave_type = relationship("LeaveType", back_populates="allocations")

class LeavePolicy(Base):
    """Leave policy model for departments/branches"""
    __tablename__ = "leave_policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    department_id = Column(Integer, nullable=True)  # ForeignKey('departments.id')
    branch_id = Column(Integer, nullable=True)  # ForeignKey('branch.id')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leave_types = relationship("LeaveType", secondary=leave_policy_leave_type_association, back_populates="policies")
    leave_balances = relationship("LeaveBalance", back_populates="policy")

class LeaveBalance(Base):
    """Employee leave balance tracking"""
    __tablename__ = "leave_balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    leave_type_id = Column(Integer, ForeignKey('leave_types.id'), nullable=False)
    policy_id = Column(Integer, ForeignKey('leave_policies.id'), nullable=True)
    accrued_days = Column(Float, default=0)
    taken_days = Column(Float, default=0)
    remaining_days = Column(Float, default=0)
    carry_forward_days = Column(Float, default=0)
    last_accrual_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="leave_balances")
    leave_type = relationship("LeaveType", back_populates="leave_balances")
    policy = relationship("LeavePolicy", back_populates="leave_balances")

class LeaveRequest(Base):
    """Leave request model"""
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    leave_type_id = Column(Integer, ForeignKey('leave_types.id'), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(50), default='pending')  # pending, approved, rejected, cancelled
    approver_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    approval_date = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    # Academic year the request counts against (settings.academicid at submit time).
    academic_id = Column(Integer, nullable=True, index=True)
    # Total balance cost in days = SUM(days.day_cost); fractional for session leave.
    total_days = Column(Float, nullable=True)
    # Colleague who covers the requester's work during the leave. Proposed by
    # the employee, changeable by the approver; notified after approval.
    replacement_user_id = Column(Integer, nullable=True)
    # Storage path/URL of the uploaded proof image (leave types with
    # requires_proof). Deleted from storage when the request is cancelled.
    proof_image_path = Column(String(500), nullable=True)
    replacement_note = Column(Text, nullable=True)
    # Read-only reviewers may remind eligible decision-makers. The first
    # manual reminder starts a 15-minute cooldown; later reminders use 1 hour.
    review_reminder_count = Column(Integer, nullable=False, default=0)
    last_review_reminder_at = Column(DateTime, nullable=True)
    # Who originally created the row. Employee requests point to the employee;
    # manual records point to the authorized approver who entered the leave.
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    creation_source = Column(String(30), nullable=True, default='employee')
    cancelled_by = Column(Integer, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="leave_requests")
    leave_type = relationship("LeaveType", back_populates="leave_requests")
    approver = relationship("User", foreign_keys=[approver_id])
    creator = relationship("User", foreign_keys=[created_by])
    history = relationship("LeaveHistory", back_populates="leave_request")
    days = relationship("LeaveRequestDay", back_populates="leave_request", cascade="all, delete-orphan")


class LeaveRequestDay(Base):
    """Per-day breakdown of a leave request (full day or specific sessions)."""
    __tablename__ = "leave_request_days"

    id = Column(Integer, primary_key=True, index=True)
    leave_request_id = Column(Integer, ForeignKey('leave_requests.id'), nullable=False, index=True)
    leave_date = Column(Date, nullable=False, index=True)
    scope = Column(String(20), nullable=False, default='full_day')  # 'full_day' | 'sessions'
    # 1-based session indexes matching AttendanceRecord.session_index; NULL for full_day.
    session_indexes = Column(JSON, nullable=True)
    # Number of working sessions the user had that day when the request was made.
    sessions_total = Column(Integer, nullable=True)
    # Balance cost for this day: 1.0 full day, len(session_indexes)/sessions_total otherwise.
    day_cost = Column(Float, nullable=False, default=1.0)
    # Monthly-cap split of day_cost, always paid_cost + unpaid_cost == day_cost.
    # paid_cost is the part charged to the annual allowance; unpaid_cost is the
    # part that exceeded LeaveType.max_days_per_month for its calendar month.
    # Both are derived values recomputed by services.leave_monthly_policy, so
    # day_cost stays the untouched record of how much leave was actually taken.
    # NULL means "not split yet" and is read as fully paid.
    paid_cost = Column(Float, nullable=True)
    unpaid_cost = Column(Float, nullable=True)
    # Display snapshots of the leave window ("HH:MM"), from the covered sessions.
    time_from = Column(String(8), nullable=True)
    time_to = Column(String(8), nullable=True)

    # Relationships
    leave_request = relationship("LeaveRequest", back_populates="days")

class LeaveApprover(Base):
    """Leave approvers configuration"""
    __tablename__ = "leave_approvers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    department_id = Column(Integer, nullable=True)  # ForeignKey('departments.id')
    branch_id = Column(Integer, nullable=True)  # ForeignKey('branch.id')
    can_approve_all = Column(Boolean, default=False)
    # Visibility only. This never expands decision authority beyond the
    # approver's branch/department scope or maximum-day limit.
    can_view_all_requests = Column(Boolean, nullable=True, default=False)
    max_days_can_approve = Column(Float, nullable=True)
    # Separate privilege: approving submitted leave does not automatically
    # allow creating approved leave on another employee's behalf.
    can_create_for_staff = Column(Boolean, nullable=True, default=False)
    # Separate privilege for non-attendance balance adjustments made under a
    # school policy. This never implies approval or manual-leave permission.
    can_adjust_leave_balance = Column(Boolean, nullable=True, default=False)
    # Privilege to cancel or close approved staff leave requests inside scope.
    can_cancel_approved_leave = Column(Boolean, nullable=True, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="leave_approver_config")


class LeaveBalanceAdjustment(Base):
    """Audited policy deduction from an employee's leave allowance.

    Adjustments are intentionally separate from leave requests: they reduce
    the balance for one academic year without creating a fake leave date or
    changing attendance. Voiding an adjustment restores the balance while
    preserving the original audit record.
    """
    __tablename__ = "leave_balance_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    leave_type_id = Column(Integer, ForeignKey('leave_types.id'), nullable=False, index=True)
    academic_id = Column(Integer, nullable=False, index=True)
    amount_days = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False, index=True)
    reason = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String(20), nullable=False, default='active', index=True)
    voided_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    void_reason = Column(Text, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    leave_type = relationship("LeaveType")
    creator = relationship("User", foreign_keys=[created_by])
    voider = relationship("User", foreign_keys=[voided_by])

class LeaveHistory(Base):
    """Audit trail for leave request changes"""
    __tablename__ = "leave_histories"

    id = Column(Integer, primary_key=True, index=True)
    leave_request_id = Column(Integer, ForeignKey('leave_requests.id'), nullable=False)
    action = Column(String(100), nullable=False)  # created, updated, approved, rejected, cancelled
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    changed_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    leave_request = relationship("LeaveRequest", back_populates="history")
    user = relationship("User", foreign_keys=[changed_by])
