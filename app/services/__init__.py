"""
Services package for business logic.
"""

from .crud import *
from .utils import *

__all__ = [
    # CRUD operations
    "create_user",
    "get_user_by_username",
    "get_user_by_email",
    "create_student",
    "get_student",
    "get_student_by_student_id",
    "get_students",
    "update_student",
    "delete_student",
    "create_teacher",
    "get_teacher",
    "get_teacher_by_teacher_id",
    "get_teachers",
    "update_teacher",
    "delete_teacher",
    "create_class",
    "get_class",
    "get_class_by_code",
    "get_classes",
    "update_class",
    "delete_class",
    "create_enrollment",
    "get_enrollment",
    "get_enrollments",
    "get_student_enrollments",
    "get_class_enrollments",
    "update_enrollment",
    "delete_enrollment",

    # Utility functions
    "get_password_hash",
    "create_short_lived_access_token",
    "create_long_lived_access_token",
    "verify_token",
    "verify_token_payload",
    "verify_long_lived_token",
    "authenticate_user",
    "async_authenticate_user",
    "authenticate_student",
    "async_authenticate_student",
    "authenticate_parent",
    "async_authenticate_parent",
]
