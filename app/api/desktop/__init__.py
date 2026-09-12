from fastapi import APIRouter, Depends
from .auth import router as auth_router
from .data import get_current_desktop_user, router as data_router
from .dashboard import router as dashboard_router
from .employee_attendance import router as employee_attendance_router
from .integrations import router as integrations_router
from .leave import router as leave_management_router
from .marks_setup import router as marks_setup_router
from .marks_system_setup import router as marks_system_setup_router
from .notifications import router as notifications_router
from .parent_registrations import router as parent_registrations_router
from .staff_registrations import router as staff_registrations_router
from .student_profile_edits import router as student_profile_edits_router

api_router = APIRouter()

# Include routers
api_router.include_router(auth_router, prefix="/auth", tags=["desktop-auth"])
api_router.include_router(data_router, prefix="/data", tags=["desktop-data"])
api_router.include_router(
    dashboard_router,
    prefix="/dashboard",
    tags=["desktop-dashboard"],
)
api_router.include_router(
    integrations_router,
    prefix="/integrations",
    tags=["desktop-integrations"],
)
api_router.include_router(
    notifications_router,
    prefix="/notifications",
    tags=["desktop-notifications"],
)
api_router.include_router(
    staff_registrations_router,
    prefix="/staff-registrations",
    tags=["desktop-staff-registrations"],
)
api_router.include_router(
    parent_registrations_router,
    prefix="/parent-registrations",
    tags=["desktop-parent-registrations"],
)
api_router.include_router(
    student_profile_edits_router,
    prefix="/student-profile-edits",
    tags=["desktop-student-profile-edits"],
)
api_router.include_router(
    leave_management_router,
    prefix="/leave-management",
    tags=["desktop-leave-management"],
    dependencies=[Depends(get_current_desktop_user)],
)
api_router.include_router(
    employee_attendance_router,
    prefix="/employee-attendance",
    tags=["desktop-employee-attendance"],
    dependencies=[Depends(get_current_desktop_user)],
)
api_router.include_router(
    marks_setup_router,
    prefix="/marks-setup",
    tags=["desktop-marks-setup"],
)
api_router.include_router(
    marks_system_setup_router,
    prefix="/marks-system-setup",
    tags=["desktop-marks-system-setup"],
)
