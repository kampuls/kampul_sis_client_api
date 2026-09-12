"""
Authentication package.
"""

from .dependencies import (
    PARENT_MEMBER_TYPES,
    STAFF_MEMBER_TYPES,
    STUDENT_MEMBER_TYPES,
    Principal,
    get_current_active_employee,
    get_current_active_user,
    get_current_principal,
    principal_from_user,
)
from .services import (
    authenticate_user, 
    async_authenticate_user,
    authenticate_student, 
    authenticate_parent
)
from .student_auth import async_authenticate_student
from .parent_auth import async_authenticate_parent

__all__ = [
    "Principal",
    "STAFF_MEMBER_TYPES",
    "PARENT_MEMBER_TYPES",
    "STUDENT_MEMBER_TYPES",
    "get_current_active_user",
    "get_current_active_employee",
    "get_current_principal",
    "principal_from_user",
    "authenticate_user",
    "async_authenticate_user",
    "authenticate_student", 
    "async_authenticate_student",
    "authenticate_parent",
    "async_authenticate_parent",
]
