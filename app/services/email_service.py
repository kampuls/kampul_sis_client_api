import smtplib
import random
import time
import hashlib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, ClassVar
from datetime import datetime, timedelta
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Settings - will be loaded from environment variables
class EmailSettings:
    SMTP_SERVER: ClassVar[str] = "smtp.gmail.com"
    SMTP_PORT: ClassVar[int] = 587
    SMTP_USER: ClassVar[str] = ""  # Set via environment
    SMTP_PASSWORD: ClassVar[str] = ""  # Set via environment
    SMTP_FROM_NAME: ClassVar[str] = "PAMA International School"
    OTP_EXPIRY_SECONDS: ClassVar[int] = 300  # 5 minutes
    MAX_FAILED_ATTEMPTS: ClassVar[int] = 5
    LOCKOUT_DURATION_SECONDS: ClassVar[int] = 900  # 15 minutes


def _hash_otp(otp: str) -> str:
    """Hash the OTP before storing in DB for minimal security."""
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_otp() -> str:
    """Generate a random 6-digit OTP"""
    return str(random.randint(100000, 999999))


def _get_db():
    """Import lazily to avoid circular import."""
    from ..core import SessionLocal
    return SessionLocal()


def store_otp(username: str, otp: str) -> None:
    """
    Store OTP in the database with expiry time.
    Uses INSERT ... ON DUPLICATE KEY UPDATE so re-requesting always refreshes.
    Works correctly across all Gunicorn workers (shared DB).
    """
    otp_hash = _hash_otp(otp)
    expiry = datetime.utcnow() + timedelta(seconds=EmailSettings.OTP_EXPIRY_SECONDS)
    db = _get_db()
    try:
        db.execute(
            text("""
                INSERT INTO otp_codes (username, otp_hash, expiry, attempts, locked_until)
                VALUES (:username, :otp_hash, :expiry, 0, NULL)
                ON DUPLICATE KEY UPDATE
                    otp_hash     = VALUES(otp_hash),
                    expiry       = VALUES(expiry),
                    attempts     = 0,
                    locked_until = NULL
            """),
            {"username": username, "otp_hash": otp_hash, "expiry": expiry},
        )
        db.commit()
        logger.info(f"OTP stored for user: {username}, expires in {EmailSettings.OTP_EXPIRY_SECONDS}s")
    except Exception as e:
        logger.error(f"Error storing OTP for {username}: {e}")
        db.rollback()
    finally:
        db.close()


def verify_otp(username: str, otp_code: str) -> tuple[bool, Optional[str]]:
    """
    Verify OTP code for a username.
    Returns (success: bool, error_message: Optional[str])
    All state is in the database — works across all workers.
    """
    db = _get_db()
    try:
        now = datetime.utcnow()

        # Fetch OTP record
        row = db.execute(
            text("""
                SELECT otp_hash, expiry, attempts, locked_until
                FROM otp_codes
                WHERE username = :username
            """),
            {"username": username},
        ).fetchone()

        if not row:
            return False, "OTP not found. Please request a new one."

        otp_hash, expiry, attempts, locked_until = row

        # Check lockout
        if locked_until and now < locked_until:
            remaining = int((locked_until - now).total_seconds())
            return False, f"Too many failed attempts. Try again in {remaining} seconds."

        # Check expiry
        if now > expiry:
            db.execute(text("DELETE FROM otp_codes WHERE username = :u"), {"u": username})
            db.commit()
            return False, "OTP has expired. Please request a new one."

        # Verify OTP
        if otp_hash != _hash_otp(otp_code):
            new_attempts = attempts + 1

            if new_attempts >= EmailSettings.MAX_FAILED_ATTEMPTS:
                # Lock out the user
                lockout_until = now + timedelta(seconds=EmailSettings.LOCKOUT_DURATION_SECONDS)
                db.execute(
                    text("""
                        UPDATE otp_codes
                        SET attempts = :attempts, locked_until = :locked_until
                        WHERE username = :username
                    """),
                    {"attempts": new_attempts, "locked_until": lockout_until, "username": username},
                )
                db.commit()
                logger.warning(f"User {username} locked out due to too many failed OTP attempts")
                return False, "Too many failed attempts. Account temporarily locked."

            db.execute(
                text("UPDATE otp_codes SET attempts = :a WHERE username = :u"),
                {"a": new_attempts, "u": username},
            )
            db.commit()
            remaining_attempts = EmailSettings.MAX_FAILED_ATTEMPTS - new_attempts
            logger.warning(f"Invalid OTP for {username}, {remaining_attempts} attempts remaining")
            return False, f"Invalid OTP code. {remaining_attempts} attempts remaining."

        # OTP verified — delete from DB
        db.execute(text("DELETE FROM otp_codes WHERE username = :u"), {"u": username})
        db.commit()
        logger.info(f"OTP verified successfully for user: {username}")
        return True, None

    except Exception as e:
        logger.error(f"Error verifying OTP for {username}: {e}")
        db.rollback()
        return False, "An error occurred. Please try again."
    finally:
        db.close()


def cleanup_expired_otps() -> None:
    """Remove expired OTPs from the database."""
    db = _get_db()
    try:
        result = db.execute(
            text("DELETE FROM otp_codes WHERE expiry < :now"),
            {"now": datetime.utcnow()},
        )
        db.commit()
        if result.rowcount:
            logger.debug(f"Removed {result.rowcount} expired OTP(s) from DB")
    except Exception as e:
        logger.error(f"Error cleaning up expired OTPs: {e}")
        db.rollback()
    finally:
        db.close()


def mask_email(email: str) -> str:
    """
    Mask email address for privacy.
    Example: 'teacher@gmail.com' -> 't****r@gmail.com'
    """
    if not email or "@" not in email:
        return "****@****.com"

    local, domain = email.split("@", 1)

    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]

    return f"{masked_local}@{domain}"


def send_otp_email(
    recipient_email: str, recipient_name: str, otp_code: str
) -> tuple[bool, Optional[str]]:
    """
    Send OTP email to recipient.
    Returns (success: bool, error_message: Optional[str])
    """
    try:
        # Validate SMTP configuration
        if not EmailSettings.SMTP_USER or not EmailSettings.SMTP_PASSWORD:
            logger.error("SMTP credentials not configured")
            return False, "Email service not configured"

        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = "Password Reset OTP - PAMA International School"
        message["From"] = f"{EmailSettings.SMTP_FROM_NAME} <{EmailSettings.SMTP_USER}>"
        message["To"] = recipient_email

        # HTML email body
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Arial', sans-serif; background-color: #f5f7fa;">
    <div style="max-width: 600px; margin: 40px auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: bold;">Password Reset</h1>
        </div>
        
        <!-- Body -->
        <div style="padding: 40px 30px;">
            <p style="color: #333; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                Hello <strong>{recipient_name}</strong>,
            </p>
            
            <p style="color: #666; font-size: 14px; line-height: 1.6; margin: 0 0 30px 0;">
                You have requested to reset your password. Use the verification code below to continue:
            </p>
            
            <!-- OTP Box -->
            <div style="background: #f8f9fa; border: 2px dashed #2196F3; border-radius: 8px; padding: 30px; text-align: center; margin: 0 0 30px 0;">
                <div style="color: #999; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">
                    Your OTP Code
                </div>
                <div style="font-size: 42px; font-weight: bold; color: #2196F3; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                    {otp_code}
                </div>
            </div>
            
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 0 0 30px 0; border-radius: 4px;">
                <p style="color: #856404; font-size: 13px; margin: 0; line-height: 1.5;">
                    ⏱️ This code will expire in <strong>5 minutes</strong>.
                </p>
            </div>
            
            <p style="color: #666; font-size: 14px; line-height: 1.6; margin: 0;">
                If you didn't request this password reset, please ignore this email and your password will remain unchanged.
            </p>
        </div>
        
        <!-- Footer -->
        <div style="background: #f8f9fa; padding: 20px 30px; border-top: 1px solid #e9ecef;">
            <p style="color: #999; font-size: 12px; margin: 0; text-align: center;">
                © 2026 PAMA International School<br>
                This is an automated message, please do not reply.
            </p>
        </div>
    </div>
</body>
</html>
        """

        # Plain text fallback
        text_body = f"""
Password Reset - PAMA International School

Hello {recipient_name},

You have requested to reset your password.

Your OTP Code: {otp_code}

This code will expire in 5 minutes.

If you didn't request this, please ignore this email.

---
PAMA International School
        """

        # Attach parts
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        message.attach(part1)
        message.attach(part2)

        # Send email
        with smtplib.SMTP(EmailSettings.SMTP_SERVER, EmailSettings.SMTP_PORT) as server:
            server.starttls()
            server.login(EmailSettings.SMTP_USER, EmailSettings.SMTP_PASSWORD)
            server.send_message(message)

        logger.info(f"OTP email sent successfully to: {recipient_email}")
        return True, None

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        return False, "Email authentication failed. Please contact administrator."
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        return False, "Failed to send email. Please try again."
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False, "An error occurred while sending email."


# Initialize settings from environment on module load
def init_email_settings(smtp_user: str = "", smtp_password: str = ""):
    """Initialize email settings from environment variables"""
    if smtp_user:
        EmailSettings.SMTP_USER = smtp_user
    if smtp_password:
        EmailSettings.SMTP_PASSWORD = smtp_password
