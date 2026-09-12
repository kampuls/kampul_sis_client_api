"""
Database models package.
"""

from .base import Base
from .user import User
from .student import Student
from .parent import Parent
from .teacher import Teacher
from .class_model import Class
from .enrollment import Enrollment
from .organization import Branch, Role, Department, BranchContact
from .notification import Notification
from .leave_management import (
    LeaveType, LeavePolicy, LeaveBalance, LeaveRequest,
    LeaveApprover, LeaveHistory, LeaveTypeAllocation, LeaveRequestDay,
    LeaveBalanceAdjustment
)
from .attendance_model import (
    AttendanceSchedule, AttendanceSystemSettings,
    AttendanceUserAssignment, AttendanceRecord, AttendanceScheduleException,
    AttendanceScheduleExceptionEnrollment,
)
from .telegram_attendance_settings import (
    TelegramAttendanceSettings,
    TelegramBranchNotificationRoute,
)
from .attendance__allowed_branches import AttendanceAllowedBranch
from .salary_model import SalaryHistory, SalaryDeduction, SalaryBonus
from .financial import UserFinancials, BonusDeductionRules
from .rbac import Permission, RolePermission
from .holiday import Holiday
from .workplace import WorkLocation
from .user_resource import UserResource
from .user_social_link import UserSocialLink
from .marketing import Ad, AdClick, SmartDownloadLink
from .device import DeviceToken
from .device import DeviceToken
from .daily_attendance import DailyAttendance
from .learning import (
    LearningTimeSlot, LearningClassSchedule,
    LearningSessionLog, LearningScheduleException, Subject
)
from .homework import LearningHomework, LearningHomeworkAttachment
from .subject_grading import (
    SubjectAttendance,
    SubjectGradeComponent,
    SubjectGradePlan,
    SubjectGradeScore,
)
from .hot_event import HotEvent, HotEventImpression
from .news import News, NewsImage
from .message import (
    MessageGroup, MessageGroupMember, GroupMessage,
    MessageGroupBan, MessageGroupSettings
)
from .academic_program import AcademicProgram, AcademicProgramImage
from .partner import Partner, PartnerImage
from .school_overview import SchoolOverview
from .school_event import SchoolEvent
from .form import Form, FormField, FormFieldOption, FormSubmission, FormSubmissionValue
from .results_top_student import ResultTopStudent
from .attendance_audit_log import AttendanceAuditLog
from .attendance_statistic import AttendanceStatistic
from .attendance_processing_rule import AttendanceProcessingRule
from .attendance_audience_preset import AttendanceAudiencePreset
from .attendance_primary_device import (
    AttendancePrimaryDevice,
    AttendancePrimaryDeviceEvent,
)
from .check_in_security_event import CheckInSecurityEvent
from .user_home_app_permission import UserHomeAppPermission
from .app_admin import AppAdmin
from .feature_lock import FeatureLock
from .student_profile_edit_request import StudentProfileEditRequest
from .profile_frame import ProfileFrame, ProfileFrameHistory
from .market import (
    MarketCategory,
    MarketSettings,
    MarketStore,
    MarketListing,
    MarketListingBroadcast,
    MarketListingImage,
    MarketOrder,
    MarketSellerBan,
    MarketWishlist,
    MarketReview,
)

__all__ = [
    "Base",
    "User",
    "Subject",
    "Branch",
    "BranchContact",
    "Role",
    "Department",
    "Student",
    "Parent",
    "Teacher",
    "Class",
    "Enrollment",
    "Notification",
    "LeaveType",
    "LeavePolicy",
    "LeaveBalance",
    "LeaveRequest",
    "LeaveApprover",
    "LeaveHistory",
    "LeaveTypeAllocation",
    "LeaveRequestDay",
    "LeaveBalanceAdjustment",
    "AttendanceSchedule",
    "AttendanceSystemSettings",
    "AttendanceUserAssignment",
    "AttendanceRecord",
    "AttendanceScheduleException",
    "AttendanceScheduleExceptionEnrollment",
    "TelegramAttendanceSettings",
    "TelegramBranchNotificationRoute",
    "AttendanceAllowedBranch",
    "SalaryHistory",
    "SalaryDeduction",
    "SalaryBonus",
    "UserFinancials",
    "BonusDeductionRules",
    "Permission",
    "RolePermission",
    "Holiday",
    "WorkLocation",
    "UserResource",
    "UserSocialLink",
    "Ad",
    "AdClick",
    "SmartDownloadLink",
    "DeviceToken",
    "DailyAttendance",
    "LearningTimeSlot",
    "LearningClassSchedule",
    "LearningSessionLog",
    "LearningScheduleException",
    "LearningHomework",
    "LearningHomeworkAttachment",
    "SubjectAttendance",
    "SubjectGradeComponent",
    "SubjectGradePlan",
    "SubjectGradeScore",
    "HotEvent",
    "HotEventImpression",
    "News",
    "NewsImage",
    "MessageGroup",
    "MessageGroupMember",
    "GroupMessage",
    "MessageGroupBan",
    "MessageGroupSettings",
    "AcademicProgram",
    "AcademicProgramImage",
    "Partner",
    "PartnerImage",
    "SchoolOverview",
    "Form",
    "FormField",
    "FormFieldOption",
    "FormSubmission",
    "FormSubmissionValue",
    "ResultTopStudent",
    "AttendanceAuditLog",
    "AttendanceStatistic",
    "AttendanceProcessingRule",
    "AttendanceAudiencePreset",
    "AttendancePrimaryDevice",
    "AttendancePrimaryDeviceEvent",
    "CheckInSecurityEvent",
    "UserHomeAppPermission",
    "AppAdmin",
    "FeatureLock",
    "StudentProfileEditRequest",
    "ProfileFrame",
    "ProfileFrameHistory",
    "MarketCategory",
    "MarketSettings",
    "MarketStore",
    "MarketListing",
    "MarketListingBroadcast",
    "MarketListingImage",
    "MarketOrder",
    "MarketSellerBan",
    "MarketWishlist",
    "MarketReview",
]
from .splash_ad import SplashAd

from .settings import SystemSettings

from .pickup import PickupRequest, PickupSettings
from .medal import Medal, MedalName, MedalPrice

from .certificate import BackgroundCert, CertificateSettings, DemoCert
