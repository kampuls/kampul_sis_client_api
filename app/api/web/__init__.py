from fastapi import APIRouter
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .app_info import router as app_router
from .students import router as students_router

api_router = APIRouter()

# Include routers
api_router.include_router(auth_router, prefix="/auth", tags=["web-auth"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["web-dashboard"])
api_router.include_router(app_router, prefix="/app", tags=["web-app"])
api_router.include_router(students_router, prefix="/students", tags=["web-students"])
