"""
API v1 package.
"""

from fastapi import APIRouter, Depends

from ...core.feature_lock_guard import require_feature_unlocked
from .auth import router as auth_router
from .users import router as users_router
from .students import router as students_router
from .teachers import router as teachers_router
from .classes import router as classes_router
from .attendance import router as attendance_router
from .branches import router as branches_router
from .roles import router as roles_router
from .departments import router as departments_router
from .positions import router as positions_router
from .marks import router as marks_router
from .results import router as results_router
from .ads import router as ads_router
from .notifications import router as notifications_router
from .parents import router as parents_router
from .employee_attendance import router as employee_attendance_router
from .leave_management import router as leave_management_router
from .websocket import websocket_endpoint
from .grades import router as grades_router
from .holidays import router as holidays_router
from .learning import router as learning_router
from .subjects import router as subjects_router
from .grade_groups import router as grade_groups_router
from .hot_events import router as hot_events_router
from .news import router as news_router
from .messages import router as messages_router
from .group_admin import router as group_admin_router
from .group_features import router as group_features_router
from .user_resource import router as profile_router
from .app import router as app_router
from .price_list import router as price_list_router
from .endpoints.academic_programs import router as academic_programs_router
from .endpoints.partners import router as partners_router
from .endpoints.school_overviews import router as school_overview_router
from .endpoints.school_events import router as school_events_router
from .endpoints.forms import router as forms_router
from .admin_users import router as admin_users_router
from .splash_ads import router as splash_ads_router
from .settings import router as settings_router
from .pickup import router as pickup_router
from .school_documents import router as school_documents_router
from .telegram_webhook import router as telegram_webhook_router
from .app_admin import router as app_admin_router
from .profile_frames import router as profile_frames_router
from .certificates import router as certificates_router
from .market import router as market_router
from .homework import router as homework_router
from .subject_grading import router as subject_grading_router

api_router = APIRouter()

# Include all routers.
# `require_feature_unlocked(...)` enforces Super Admin feature locks on WRITE
# requests only (reads stay open for parents/teachers). Routers whose writes
# are also performed by regular users carry `exempt_suffixes` for those paths.
api_router.include_router(
    splash_ads_router,
    dependencies=[Depends(require_feature_unlocked("splash_ads"))],
)
api_router.include_router(
    settings_router, prefix="/settings", tags=["settings"],
    dependencies=[Depends(require_feature_unlocked("company_settings"))],
)
api_router.include_router(auth_router, prefix="/auth", tags=["authentication"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(parents_router, prefix="/parents", tags=["parents"])
# Register before students_router: students also defines GET /branches (auth-only).
# First match wins; public list must be the canonical /api/v1/branches for registration, etc.
api_router.include_router(
    branches_router, prefix="/branches", tags=["branches"],
    dependencies=[Depends(require_feature_unlocked("manage_branches"))],
)
api_router.include_router(students_router, tags=["students"])  # No prefix - endpoints define their own paths
api_router.include_router(teachers_router, prefix="/teachers", tags=["teachers"])
api_router.include_router(classes_router, prefix="/classes", tags=["classes"])
api_router.include_router(attendance_router, prefix="/attendance", tags=["attendance"])
api_router.include_router(roles_router, prefix="/roles", tags=["roles"])
api_router.include_router(departments_router, prefix="/departments", tags=["departments"])
api_router.include_router(positions_router, prefix="/positions", tags=["positions"])
api_router.include_router(marks_router, tags=["marks"])
api_router.include_router(results_router, prefix="/results", tags=["results"])
api_router.include_router(
    ads_router, prefix="/ads", tags=["ads"],
    # /click and /view are app-user tracking events, not admin writes
    dependencies=[Depends(require_feature_unlocked("manage_ads", exempt_suffixes=("/click", "/view")))],
)
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(employee_attendance_router, prefix="/employee-attendance", tags=["employee-attendance"])
api_router.include_router(leave_management_router, prefix="/leave-management", tags=["leave-management"])
api_router.include_router(grades_router, prefix="/grades", tags=["grades"])
api_router.include_router(grade_groups_router, prefix="/grade-groups", tags=["grade-groups"])
api_router.include_router(holidays_router, prefix="/holidays", tags=["holidays"])
api_router.include_router(
    hot_events_router, prefix="/hot-events", tags=["hot-events"],
    # /view is an app-user tracking event, not an admin write
    dependencies=[Depends(require_feature_unlocked("hot_events", exempt_suffixes=("/view",)))],
)
api_router.include_router(
    news_router, prefix="/news", tags=["news"],
    dependencies=[Depends(require_feature_unlocked("news_updates"))],
)
api_router.include_router(learning_router, tags=["learning"])
api_router.include_router(homework_router)
api_router.include_router(subject_grading_router, tags=["subject-grading"])
api_router.include_router(subjects_router, tags=["subjects"])
api_router.include_router(messages_router, prefix="/messages", tags=["messages"])
api_router.include_router(group_admin_router, prefix="/messages", tags=["group-admin"])
api_router.include_router(group_features_router, prefix="/messages", tags=["group-features"])
api_router.include_router(profile_router, prefix="/profile", tags=["profile"])
api_router.include_router(app_router, prefix="/app", tags=["app"])
api_router.include_router(price_list_router, prefix="/price-list", tags=["price-list"])
api_router.include_router(
    academic_programs_router, prefix="/academic-programs", tags=["academic-programs"],
    dependencies=[Depends(require_feature_unlocked("academic_programs"))],
)
api_router.include_router(
    partners_router, prefix="/partners", tags=["partners"],
    dependencies=[Depends(require_feature_unlocked("partners"))],
)
api_router.include_router(
    school_overview_router, prefix="/school-overviews", tags=["school_overview"],
    dependencies=[Depends(require_feature_unlocked("school_overview"))],
)
api_router.include_router(
    school_events_router, prefix="/school-events", tags=["school_events"],
    dependencies=[Depends(require_feature_unlocked("school_events"))],
)
api_router.include_router(
    forms_router, prefix="/forms", tags=["dynamic_forms"],
    # /submit is how app users answer forms, not an admin write
    dependencies=[Depends(require_feature_unlocked("manage_forms", exempt_suffixes=("/submit",)))],
)
api_router.include_router(admin_users_router, tags=["admin-users"])
api_router.include_router(pickup_router, prefix="/pickup", tags=["pickup"])
api_router.include_router(
    school_documents_router, tags=["school-documents"],
    dependencies=[Depends(require_feature_unlocked("school_documents"))],
)

# Telegram webhook (no auth required - Telegram sends updates)
api_router.include_router(telegram_webhook_router, prefix="/telegram", tags=["telegram-webhook"])
from .medals import router as medals_router
api_router.include_router(medals_router, tags=["medals"])

# Monitoring endpoints (for performance tracking)
from .monitoring import router as monitoring_router
api_router.include_router(monitoring_router)

# Version compatibility endpoint (for Flutter app)
from .version_compat import router as version_compat_router
api_router.include_router(version_compat_router, prefix="/app", tags=["app"])

# Attendance audit & statistics endpoints
from .attendance_audit import router as attendance_audit_router
api_router.include_router(attendance_audit_router, prefix="/attendance", tags=["attendance-audit"])

# App Admin Control endpoints
api_router.include_router(app_admin_router, prefix="/app-admin", tags=["app-admin-control"])

# Profile Frames
api_router.include_router(profile_frames_router, prefix="/profile-frames", tags=["profile-frames"])

# Certificate Management
api_router.include_router(certificates_router, tags=["certificates"])

# School Marketplace
api_router.include_router(market_router, prefix="/market", tags=["market"])

__all__ = ["api_router"]
