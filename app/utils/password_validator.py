"""
Password validation utilities.
Enforces strong password policies.
"""
import re
from ..core.config import settings


class PasswordValidationError(Exception):
    """Raised when password doesn't meet requirements"""
    pass


def validate_password_strength(password: str) -> bool:
    """
    Validate password meets minimum security requirements.
    
    Requirements:
    - Minimum length (default: 8 characters)
    - At least one uppercase letter (if enabled)
    - At least one lowercase letter (if enabled)
    - At least one digit (if enabled)
    - At least one special character (if enabled)
    
    Args:
        password: Password string to validate
        
    Returns:
        True if password meets all requirements
        
    Raises:
        PasswordValidationError: If password doesn't meet requirements
    """
    errors = []
    
    # Check minimum length
    if len(password) < settings.password_min_length:
        errors.append(f"Password must be at least {settings.password_min_length} characters long")
    
    # Check uppercase requirement
    if settings.password_require_uppercase:
        if not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
    
    # Check lowercase requirement
    if settings.password_require_lowercase:
        if not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
    
    # Check digit requirement
    if getattr(settings, 'password_require_digit', True):
        if not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one number")
    
    # Check special character requirement
    if getattr(settings, 'password_require_special', False):
        special_chars = set("!@#$%^&*()_+-=[]{}|;:,.<>?")
        if not any(c in special_chars for c in password):
            errors.append("Password must contain at least one special character (!@#$%^&*...)")
    
    # Check for common weak passwords
    weak_passwords = ['password', '123456', '12345678', 'qwerty', 'abc123', 'password123']
    if password.lower() in weak_passwords:
        errors.append("Password is too common. Please choose a stronger password")
    
    # If any errors, raise exception
    if errors:
        raise PasswordValidationError("; ".join(errors))
    
    return True


def calculate_password_strength(password: str) -> int:
    """
    Calculate password strength score (0-100).
    
    Args:
        password: Password string to score
        
    Returns:
        Integer score from 0-100
    """
    score = 0
    
    # Length score (max 30 points)
    if len(password) >= 8:
        score += 10
    if len(password) >= 12:
        score += 10
    if len(password) >= 16:
        score += 10
    
    # Character variety score (max 40 points)
    if any(c.islower() for c in password):
        score += 10
    if any(c.isupper() for c in password):
        score += 10
    if any(c.isdigit() for c in password):
        score += 10
    special_chars = set("!@#$%^&*()_+-=[]{}|;:,.<>?")
    if any(c in special_chars for c in password):
        score += 10
    
    # No repeated characters score (max 15 points)
    if len(password) == len(set(password)):
        score += 15
    elif len(set(password)) >= len(password) * 0.8:
        score += 10
    
    # No common patterns score (max 15 points)
    weak_passwords = ['password', '123456', '12345678', 'qwerty', 'abc123']
    if not any(weak in password.lower() for weak in weak_passwords):
        score += 15
    
    return min(score, 100)


def get_password_requirements() -> dict:
    """
    Get human-readable password requirements.
    
    Returns:
        Dictionary of requirements
    """
    requirements = {
        "min_length": settings.password_min_length,
        "require_uppercase": settings.password_require_uppercase,
        "require_lowercase": settings.password_require_lowercase,
        "require_digit": getattr(settings, 'password_require_digit', True),
        "require_special": getattr(settings, 'password_require_special', False),
    }
    
    # Human readable messages
    messages = []
    messages.append(f"At least {settings.password_min_length} characters")
    
    if settings.password_require_uppercase:
        messages.append("At least one uppercase letter (A-Z)")
    
    if settings.password_require_lowercase:
        messages.append("At least one lowercase letter (a-z)")
    
    if requirements["require_digit"]:
        messages.append("At least one number (0-9)")
    
    if requirements["require_special"]:
        messages.append("At least one special character (!@#$%^&*...)")
    
    return {
        "requirements": requirements,
        "messages": messages,
    }
