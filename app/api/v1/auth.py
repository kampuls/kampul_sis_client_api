from fastapi import APIRouter, Depends, HTTPException, status, Header, BackgroundTasks, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import (
    OAuth2PasswordRequestForm,
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from sqlalchemy.orm import Session, defer
from datetime import timedelta
import jwt
# PyJWT replaces python-jose, which is unmaintained and whose stale
# pyasn1 pin made requirements.txt uninstallable. Tokens are byte-identical,
# so sessions issued by the old library keep working.
from jwt import PyJWTError as JWTError
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
import base64
import os
from datetime import datetime
from sqlalchemy import text

from ...core import get_db, settings

logger = logging.getLogger(__name__)

# Google Authentication imports
try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    logger.warning(
        "Google authentication libraries not installed. Google login will not work."
    )
from ...schemas import (
    Token,
    UserCreate,
    UserResponse,
    StaffRegisterResponse,
    UserMeResponse,
    RoleBasedLogin,
    StudentLoginResponse,
    ParentLoginResponse,
    TeacherLoginResponse,
)
from ...schemas.parents import ParentCreate, ParentRegisterResponse
from ...services import (
    create_user,
    get_user_by_username,
    get_user_by_email,
    get_password_hash,
    create_short_lived_access_token,
    create_long_lived_access_token,
    verify_token_payload,
    verify_long_lived_token,
)
from ...auth import (
    authenticate_user,
    async_authenticate_user,
    authenticate_student,
    async_authenticate_student,
    authenticate_parent,
    async_authenticate_parent,
    get_current_active_user,
)
from ...auth.dependencies import get_current_active_user, require_admin
from ...models import (
    User,
    Student,
    Parent,
    Permission,
    RolePermission,
    UserHomeAppPermission,
)
from ...services.cache import permissions_cache
from ...utils.phone import get_phone_variations
from ...utils.client_ip import client_ip, peer_is_trusted_proxy, throttle_ip
from ...services import login_throttle
from ...services.phone_conflict import (
    PHONE_CONFLICT_CODE,
    accounts_on_app,
    find_conflict_for_account,
    list_all_conflicts,
    lock_is_enabled,
    set_lock_enabled,
)
from ...services.telegram_otp_security import (
    allow_send as allow_telegram_otp_send,
    bearer_value,
    claim_registration_proof,
    issue_registration_proof,
    retry_after_seconds as telegram_otp_retry_after_seconds,
)


def _assert_login_not_throttled(request: Optional[Request], username: str) -> None:
    """Refuse further guesses once an account has failed too many times.

    Keyed on the account first, so rotating IPs (or spoofing X-Forwarded-For)
    does not reset the count. Successful logins clear it, so a real person who
    mistypes once is unaffected.
    """
    ip = throttle_ip(request) if request is not None else None
    if login_throttle.is_locked(username, ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(login_throttle.retry_after_seconds())},
        )


def _note_login_failure(request: Optional[Request], username: str) -> None:
    login_throttle.record_failure(
        username, throttle_ip(request) if request is not None else None
    )


def _note_login_success(request: Optional[Request], username: str) -> None:
    login_throttle.clear(
        username, throttle_ip(request) if request is not None else None
    )


def _assert_phone_not_shared(db: Session, account_id: int, account_type: str) -> None:
    """Refuse the login when this account's phone is on another account too.

    Sharing a number with a second account of the same kind makes every
    phone-based sign-in a coin flip, so the account stays locked until an
    administrator corrects the data. 423 Locked is distinct from a wrong
    password (401) and from "pick which role" (409) so the app can show the
    right dialog.
    """
    if not lock_is_enabled(db):
        # Cleanup mode: these accounts keep working with username + password.
        # Their PHONE login is still refused below, so the wrong-account coin
        # flip cannot happen either way — only the hard lockout is deferred.
        return
    conflict = find_conflict_for_account(db, account_id, account_type)
    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=conflict.as_payload(),
        )


def _claim_telegram_registration(
    db: Session,
    phone: Optional[str],
    authorization: Optional[str],
) -> bool:
    """Consume a one-use proof returned by Telegram OTP verification."""
    token = bearer_value(authorization)
    if not phone or not token:
        return False
    try:
        normalized_phone = _normalize_to_e164(phone)
    except ValueError:
        return False
    return claim_registration_proof(
        db,
        phone=normalized_phone,
        token=token,
    )


async def _verify_firebase_registration_phone(
    token: str,
    expected_phone: Optional[str],
) -> None:
    """Verify a Firebase ID token and bind it to the exact form phone."""
    if not GOOGLE_AUTH_AVAILABLE or not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase phone verification is not configured on the server.",
        )
    if not token.strip() or not expected_phone:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phone verification is required.",
        )

    request_obj = google_requests.Request()
    try:
        decoded_token = await run_in_threadpool(
            lambda: google_id_token.verify_firebase_token(
                token.strip(),
                request_obj,
                settings.firebase_project_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase phone authentication token.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Firebase registration token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase phone verification is temporarily unavailable.",
        ) from exc

    token_phone = decoded_token.get("phone_number")
    if not token_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase token does not contain a verified phone number.",
        )
    try:
        normalized_token_phone = _normalize_to_e164(str(token_phone))
        normalized_expected_phone = _normalize_to_e164(expected_phone)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verified or provided phone number is invalid.",
        ) from exc
    if normalized_token_phone != normalized_expected_phone:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The verified phone number does not match the registration phone number.",
        )

router = APIRouter()
security = HTTPBearer()


@router.get("/check-parent-username/{username}")
async def check_parent_username_available(username: str, db: Session = Depends(get_db)):
    """Check if a parent username is available.

    Checks the employee table too: several endpoints resolve a caller by the
    ``sub`` claim alone, so a parent holding a teacher's username would be
    served that teacher's account.
    """
    return {"available": _username_is_free(db, username)}


def _username_is_free(db: Session, username: str) -> bool:
    """True when no employee and no parent already owns this username."""
    if not username or not username.strip():
        return False
    username = username.strip()
    if get_user_by_username(db, username):
        return False
    if db.query(Parent).filter(Parent.username == username).first():
        return False
    return True


@router.post("/register", response_model=StaffRegisterResponse)
async def register(
    user: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Register a new user with password validation."""
    # This is a public staff-registration surface. Never trust a client-supplied
    # role or status: every account must enter the staff approval queue.
    user = user.model_copy(update={"role": 2, "status": 2})

    # Validate password strength
    from ...utils.password_validator import validate_password_strength
    try:
        validate_password_strength(user.password)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    # Check if username already exists — in either table, since usernames are
    # used to resolve accounts across both.
    if not _username_is_free(db, user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Check if email already exists (only if email is provided)
    if user.email and get_user_by_email(db, user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Check if identityNumber already exists (only if identityNumber is provided)
    if user.identityNumber:
        existing_user_id = (
            db.query(User).filter(User.identityNumber == user.identityNumber).first()
        )
        if existing_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This Identity Number / Passport Number is already linked to another account. Please check and try again.",
            )

    # Security Check: Enforce Phone Verification for Teachers/Employees (Role 2).
    # Telegram verification produces an opaque proof tied to this phone.  Claiming
    # it here is atomic with create_user's commit, so it cannot be replayed for a
    # second registration. Firebase SMS continues to use its signed ID token.
    if (
        user.role == 2 or user.role == "teacher"
    ):
        telegram_verified = _claim_telegram_registration(
            db,
            user.phone,
            authorization,
        )
        if telegram_verified:
            logger.info("Registration: one-use Telegram proof accepted")
        else:
            if not authorization:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Phone verification is required. Please verify your phone via Telegram OTP or Firebase SMS.",
                )
            await _verify_firebase_registration_phone(
                bearer_value(authorization) or "",
                user.phone,
            )
        # Telegram-verified registrations skip Firebase token validation.

    new_user = create_user(db=db, user=user)

    # Use a real FastAPI background task with its own database session.  The
    # previous fire-and-forget task reused the request DB session, which can be closed
    # by the time the notification worker starts.
    try:
        from ...services.registration_notification_service import (
            notify_approvers_new_staff_registration,
        )

        background_tasks.add_task(
            notify_approvers_new_staff_registration,
            int(new_user.id),
        )
    except Exception as e:
        logger.error(f"Failed to notify admins of new employee registration: {e}")

    access_token = create_short_lived_access_token(
        data={
            "sub": new_user.username,
            "role": "teacher",
            "user_id": new_user.id,
            "token_version": getattr(new_user, "token_version", 1) or 1,
        }
    )
    return StaffRegisterResponse(
        **UserResponse.model_validate(new_user).model_dump(),
        access_token=access_token,
        token_type="bearer",
        pending_approval=True,
    )


@router.post("/register-parent", response_model=ParentRegisterResponse)
async def register_parent(
    parent_data: ParentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Register a new parent with password validation."""
    from secrets import token_hex, token_urlsafe
    from ...core.parent_registration import (
        format_parent_save_error,
        insert_pending_parent,
        notify_app_admins_new_parent_registration,
        notify_telegram_new_parent_registration,
    )
    from ...core.parent_status import ensure_parent_status_column

    try:
        ensure_parent_status_column(db)
    except Exception as e:
        logger.error(f"Parent status column check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database is not ready for parent registration. Please contact support.",
        )

    # Validate password strength — only if the user chose a password.
    # Parents may register without one; the backend auto-generates credentials.
    from ...utils.password_validator import validate_password_strength
    if parent_data.password:
        try:
            validate_password_strength(parent_data.password)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # Check if ANY of the provided phone numbers already exist in ANY phone column
    # This prevents duplicate registrations regardless of parent role
    phones_to_check = []
    if parent_data.fatherPhone and parent_data.fatherPhone.strip():
        phones_to_check.append(parent_data.fatherPhone.strip())
    if parent_data.motherPhone and parent_data.motherPhone.strip():
        phones_to_check.append(parent_data.motherPhone.strip())
    if parent_data.gPhone and parent_data.gPhone.strip():
        phones_to_check.append(parent_data.gPhone.strip())

    for phone in phones_to_check:
        phone_variations = get_phone_variations(phone)
        existing_parent_phone = (
            db.query(Parent)
            .filter(
                (Parent.fatherPhone.in_(phone_variations))
                | (Parent.motherPhone.in_(phone_variations))
                | (Parent.gPhone.in_(phone_variations))
            )
            .first()
        )
        if existing_parent_phone:
            raise HTTPException(
                status_code=400, detail=f"Phone number '{phone}' is already registered"
            )

    # Verify Phone Auth. Telegram uses the one-use proof returned after code
    # verification; Firebase SMS uses its signed ID token.
    primary_phone = None
    if parent_data.parentRole == "mother":
        primary_phone = parent_data.motherPhone
    elif parent_data.parentRole == "guardian":
        primary_phone = parent_data.gPhone
    else:  # father (default)
        primary_phone = parent_data.fatherPhone

    telegram_verified = _claim_telegram_registration(
        db,
        primary_phone,
        authorization,
    )
    if telegram_verified:
        logger.info("Parent registration: one-use Telegram proof accepted")
    else:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phone verification is required. Please verify your phone via Telegram OTP or Firebase SMS.",
            )
        await _verify_firebase_registration_phone(
            bearer_value(authorization) or "",
            primary_phone,
        )
    # Telegram-verified registrations skip Firebase token validation.


    def _next_parent_username() -> str:
        for _ in range(50):
            candidate = f"p{token_hex(4)}"
            if len(candidate) > 25:
                candidate = candidate[:25]
            if _username_is_free(db, candidate):
                return candidate
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to allocate a username. Please try again.",
        )

    final_username = parent_data.username
    if not final_username:
        final_username = _next_parent_username()
    else:
        # Must be free in BOTH tables — a parent registering as an existing
        # employee's username would be resolved as that employee.
        if not _username_is_free(db, final_username):
            raise HTTPException(status_code=400, detail="Username already registered")

    user_chose_password = bool(parent_data.password)
    if user_chose_password:
        plain_password_for_response: Optional[str] = None
        password_to_hash = parent_data.password
    else:
        plain_password_for_response = token_urlsafe(12)
        password_to_hash = plain_password_for_response

    # Create Parent Record
    # Generate uniqueid if needed or leave empty (model says nullable=False but no default?)
    # Model says: uniqueid = Column(String(100), nullable=False)
    # let's generate one or set default.
    new_unique_id = str(uuid.uuid4())

    hashed_password = get_password_hash(password_to_hash)

    try:
        new_parent_id = insert_pending_parent(
            db,
            parent_data,
            username=final_username,
            password_hash=hashed_password,
            unique_id=new_unique_id,
        )
    except Exception as e:
        logger.exception("register_parent failed saving parent: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=format_parent_save_error(e),
        )

    new_parent = db.query(Parent).filter(Parent.id == new_parent_id).first()
    if new_parent is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration saved but could not be loaded. Please contact support.",
        )

    # Handle Image Upload (UserResource)
    if parent_data.image:
        try:
            import base64

            # Decode base64
            image_data = base64.b64decode(parent_data.image)

            # Save to file
            # Assuming we have a media/ directory or similar.
            # Or store path in UserResource.
            # user_resource.py says: avatar = Column(String(255)) # Path/URL

            # For now, let's create a directory if not exists
            import os

            upload_dir = "uploads/avatars"
            os.makedirs(upload_dir, exist_ok=True)

            filename = f"parent_{new_parent.id}_{uuid.uuid4().hex[:8]}.jpg"
            file_path = os.path.join(upload_dir, filename)

            with open(file_path, "wb") as f:
                f.write(image_data)

            # Create UserResource
            from ...models.user_resource import UserResource

            user_res = UserResource(
                user_id=new_parent.id, user_type="parent", avatar=file_path, status=1
            )
            db.add(user_res)
            db.commit()

        except Exception as e:
            logger.error(f"Failed to save profile image: {e}")
            # Don't fail registration, just log error

    background_tasks.add_task(
        notify_app_admins_new_parent_registration,
        new_parent.id,
        final_username,
    )
    background_tasks.add_task(
        notify_telegram_new_parent_registration,
        new_parent.id,
    )

    parent_username = new_parent.username if new_parent.username else str(new_parent.id)
    access_token = create_short_lived_access_token(
        data={
            "sub": parent_username,
            "role": "parent",
            "user_id": new_parent.id,
        }
    )

    return ParentRegisterResponse(
        access_token=access_token,
        token_type="bearer",
        username=final_username,
        parent_id=new_parent.id,
        pending_approval=True,
        password=plain_password_for_response,
    )


@router.get("/check-username/{username}")
async def check_username_available(username: str, db: Session = Depends(get_db)):
    """Check if a username is available (across employees and parents)."""
    if not _username_is_free(db, username):
        return {"available": False, "detail": "Username is already taken"}
    return {"available": True, "detail": "Username is available"}


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login and get access token (defaults to teacher role)."""
    _assert_login_not_throttled(request, form_data.username)
    user = await async_authenticate_user(db, form_data.username, form_data.password)
    if not user:
        _note_login_failure(request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _note_login_success(request, form_data.username)

    _assert_phone_not_shared(db, user.id, "teacher")

    # Create short-lived access token (2 hours, cannot be auto-refreshed)
    # User must exchange this for long-lived token
    access_token = create_short_lived_access_token(
        data={
            "sub": user.username,
            "role": "teacher",
            "user_id": user.id,
            "token_version": getattr(user, "token_version", 1) or 1,
        }
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login-role", response_model=Token)
async def login_with_role(
    login_data: RoleBasedLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with specific role (teacher, student, parent)."""
    logger.info(f"Login request received: {login_data.model_dump_json()}")
    _assert_login_not_throttled(request, login_data.username)
    user = None
    role_data = None

    if login_data.role == "teacher":
        # Check in users table
        user = await async_authenticate_user(
            db, login_data.username, login_data.password
        )
        if user:
            _assert_phone_not_shared(db, user.id, "teacher")
            role_data = {
                "role": "teacher",
                "user_id": user.id,
                "token_version": getattr(user, "token_version", 1) or 1,
            }
    elif login_data.role == "student":
        # Check in students table
        student = await async_authenticate_student(
            db, login_data.username, login_data.password
        )
        if student:
            user = type(
                "User", (), {"username": student.username}
            )()  # Mock user object
            role_data = {"role": "student", "user_id": student.id}
    elif login_data.role == "parent":
        # Check in parents table
        parent = await async_authenticate_parent(
            db, login_data.username, login_data.password
        )
        if parent:
            if getattr(parent, "status", 0) != 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your parent account is pending administrative approval. Please try again after approval.",
                )
            _assert_phone_not_shared(db, parent.id, "parent")
            # Use username if available, otherwise use id
            username = parent.username if parent.username else str(parent.id)
            user = type("User", (), {"username": username})()  # Mock user object
            role_data = {
                "role": "parent",
                "user_id": parent.id,
                "token_version": getattr(parent, "token_version", 1) or 1,
            }
    else:
        logger.error(
            f"Invalid role received during login: '{login_data.role}' (Type: {type(login_data.role)})"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: '{login_data.role}'. Must be 'teacher', 'student', or 'parent'",
        )

    if not user:
        _note_login_failure(request, login_data.username)
        # Provide more specific error messages
        if login_data.role == "parent":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Parent not found. Please check your username/phone number or id. If you don't have a password set, please contact administrator.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found in {login_data.role} table",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Create short-lived access token (2 hours, cannot be auto-refreshed)
    # User must exchange this for long-lived token
    token_payload = {
        "sub": user.username,
        "role": role_data["role"],
        "user_id": role_data["user_id"],
    }
    # Only teachers/employees currently have token_version; parents/students are unchanged
    if role_data["role"] in ("teacher", "parent"):
        token_payload["token_version"] = role_data.get("token_version", 1) or 1

    _note_login_success(request, login_data.username)
    access_token = create_short_lived_access_token(data=token_payload)

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Get current user information for any role (teacher, student, parent)."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        import time
        t_start = time.time()
        
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        username: str = payload.get("sub")
        user_role: str = payload.get("role")
        user_id = payload.get("user_id")  # May be None for some tokens
        token_version = payload.get("token_version")

        if user_role is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Get user data based on role
    if user_role == "teacher":
        import time
        t1 = time.time()
        print(f"DEBUG /me: JWT decode took {t1 - t_start}s")
        # Use user_id if available, fallback to username
        if user_id is not None:
            user = db.query(User).options(defer(User.image), defer(User.signature)).filter(User.id == user_id).first()
        else:
            user = db.query(User).options(defer(User.image), defer(User.signature)).filter(User.username == username).first()
        t2 = time.time()
        print(f"DEBUG /me: User query took {t2 - t1}s")
        if user is None:
            raise credentials_exception

        # Enforce token_version for teachers
        db_version = getattr(user, "token_version", 1) or 1
        if token_version is not None:
            if int(token_version) != int(db_version):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            # Legacy teacher tokens without version are invalid once token_version > 1
            if int(db_version) > 1:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # The app calls /me on every launch, so this is where an already
        # signed-in user whose phone became ambiguous gets stopped.
        _assert_phone_not_shared(db, user.id, "teacher")

        # workplace column in users table stores the branch_id (integer: 1, 2, 3, 4, etc.)
        # Get workplace value directly from database
        workplace_value = user.workplace_id

        # Convert to int if needed and ensure it's not None
        if workplace_value is None:
            workplace_value = 0
        else:
            # Ensure it's an integer
            try:
                workplace_value = int(workplace_value)
            except (ValueError, TypeError):
                workplace_value = 0

        # Fetch permissions for the user's role (cached)
        cache_key = f"permissions_role_{user.role}"
        cached_perms = permissions_cache.get(cache_key)
        if cached_perms is not None:
            permission_list = cached_perms
        else:
            permissions = (
                db.query(Permission.permission_name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role_id == user.role)
                .all()
            )
            permission_list = [p[0] for p in permissions]
        t3 = time.time()
        print(f"DEBUG /me: Permissions logic took {t3 - t2}s")

        # Build user data dictionary with ALL fields from User model
        locked_features = [
            row[0]
            for row in db.query(UserHomeAppPermission.feature_id)
            .filter(
                UserHomeAppPermission.user_id == user.id,
                UserHomeAppPermission.is_allowed == False,
            )
            .all()
        ]
        user_data = {
            "debug_jwt": t1 - t_start,
            "debug_query": t2 - t1,
            "debug_perms": t3 - t2,
            "permissions": permission_list,
            "locked_features": locked_features,
            "id": user.id,
            "username": user.username,
            # Never return the password hash — the client has no use for it and
            # it lands in logs, caches and crash reports.
            "uniqueId": user.uniqueId,
            "image": None, # Removed hex generation to prevent 30s+ server freeze
            "kName": user.kName,
            "eName": user.eName,
            "height": float(user.height) if user.height else None,
            "gender": user.gender,
            "dob": user.dob.isoformat() if user.dob else None,
            "signature": None, # Removed hex generation to prevent 30s+ server freeze
            "nationality": user.nationality,
            "religion": user.religion,
            "province": user.province,
            "district": user.district,
            "commune": user.commune,
            "village": user.village,
            "email": user.email,
            "phone": user.phone,
            "telegramId": user.telegramId,
            "pProvince": user.pProvince,
            "pDistrict": user.pDistrict,
            "pCommune": user.pCommune,
            "pVillage": user.pVillage,
            "identityNumber": user.identityNumber,
            "identityRegDate": user.identityRegDate.isoformat()
            if user.identityRegDate
            else None,
            "identityEndDate": user.identityEndDate.isoformat()
            if user.identityEndDate
            else None,
            "identityRegPlace": user.identityRegPlace,
            "fatherName": user.fatherName,
            "motherName": user.motherName,
            "departmentId": user.departmentId,
            "positionId": user.positionId,
            "startWork": user.startWork,
            "endWork": user.endWork,
            "education": user.education,
            "workplace": workplace_value,
            "workplace_id": workplace_value,
            "branch_id": workplace_value,
            "status": user.status,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "isForeigner": user.isForeigner,
            "user_type": "teacher",
        }

        return user_data
    elif user_role == "student":
        # Use user_id if available, fallback to username
        if user_id is not None:
            student = db.query(Student).filter(Student.id == user_id).first()
        else:
            student = db.query(Student).filter(Student.username == username).first()
        if student is None:
            raise credentials_exception
        
        student_data = {
            "id": student.id,
            "username": student.username,
            "studentid": student.studentid,
            "kName": student.kName,
            "eName": student.eName,
            "gender": student.gender,
            "dob": student.dob,
            "academic": student.academic,
            "branch": student.branch,
            "status": student.status,
            "created_at": student.created_at,
            "user_type": "student",
        }
        return student_data
    elif user_role == "parent":
        # Use user_id if available, fallback to username
        parent = None
        if user_id is not None:
            parent = db.query(Parent).filter(Parent.id == user_id).first()
        if parent is None:
            parent = db.query(Parent).filter(Parent.username == username).first()
        if parent is None:
            raise credentials_exception

        # Stops an already signed-in parent as soon as the app relaunches.
        _assert_phone_not_shared(db, parent.id, "parent")

        db_version = getattr(parent, "token_version", 1) or 1
        if token_version is not None:
            if int(token_version) != int(db_version):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        elif int(db_version) > 1:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Return all parent fields for profile edit (match parents table columns)
        parent_data = {
            "id": parent.id,
            "username": parent.username,
            "uniqueid": parent.uniqueid,
            "fatherName": parent.fatherName,
            "motherName": parent.motherName,
            "fatherPhone": parent.fatherPhone,
            "motherPhone": parent.motherPhone,
            "fatherJob": parent.fatherJob,
            "motherJob": parent.motherJob,
            "pProvince": parent.pProvince,
            "pDistrict": parent.pDistrict,
            "pCommune": parent.pCommune,
            "pVillage": parent.pVillage,
            "pEmail": parent.pEmail,
            "pTelegramId": parent.pTelegramId,
            "gName": parent.gName,
            "gPhone": parent.gPhone,
            "gIsThe": parent.gIsThe,
            "gHome": parent.gHome,
            "gStreet": parent.gStreet,
            "gGroup": parent.gGroup,
            "gProvince": parent.gProvince,
            "gDistrict": parent.gDistrict,
            "gCommune": parent.gCommune,
            "gVillage": parent.gVillage,
            "myChilds": parent.myChilds,
            "status": parent.status,
            "created_at": parent.created_at.isoformat() if parent.created_at else None,
            "updated_at": parent.updated_at.isoformat() if parent.updated_at else None,
            "user_type": "parent",
        }
        return parent_data
    else:
        raise credentials_exception


class ExchangeTokenRequest(BaseModel):
    access_token: str


@router.post("/exchange-long-lived", response_model=Token)
async def exchange_long_lived_token(
    token_request: ExchangeTokenRequest, db: Session = Depends(get_db)
):
    """Exchange short-lived access token for long-lived access token (Facebook-like: 60 days, can be refreshed)."""
    short_token = token_request.access_token

    # Verify short-lived token
    payload = verify_token_payload(short_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_type = payload.get("type")
    # Only allow exchange of short-lived tokens
    if token_type != "short_access":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only short-lived tokens can be exchanged",
        )

    username: str = payload.get("sub")
    user_role: str = payload.get("role")
    user_id = payload.get("user_id")  # May be None for some tokens
    short_token_version = payload.get("token_version")

    # Generate long-lived access token (60 days, can be refreshed/extended)
    token_data = {"sub": username, "role": user_role}
    if user_id is not None:
        token_data["user_id"] = user_id

    # Carry an up-to-date token_version so a revoked session cannot be laundered
    # into a fresh 60-day token by exchanging or refreshing it.
    if user_id is not None and user_role in ("teacher", "parent"):
        row = (
            db.query(Parent).filter(Parent.id == user_id).first()
            if user_role == "parent"
            else db.query(User).filter(User.id == user_id).first()
        )
        if row is not None:
            token_data["token_version"] = getattr(row, "token_version", 1) or 1
        elif short_token_version is not None:
            token_data["token_version"] = short_token_version
    long_lived_token = create_long_lived_access_token(data=token_data)

    return {"access_token": long_lived_token, "token_type": "bearer"}


@router.post("/refresh-long-lived", response_model=Token)
async def refresh_long_lived_token(
    token_request: ExchangeTokenRequest, db: Session = Depends(get_db)
):
    """Refresh/extend long-lived access token (Facebook-like: extends 60 days from now)."""
    long_token = token_request.access_token

    # Verify long-lived token
    payload = verify_long_lived_token(long_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired long-lived token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub")
    user_role: str = payload.get("role")
    user_id = payload.get("user_id")  # May be None for some tokens
    long_token_version = payload.get("token_version")

    # Generate new long-lived access token (extends by configured days from now)
    # Example: If long_lived_token_days = 60, extends by 60 days from now
    # Example: If long_lived_token_days = 1, extends by 1 day from now
    # This is rolling expiration: each refresh extends the lifetime from refresh time
    token_data = {"sub": username, "role": user_role}
    if user_id is not None:
        token_data["user_id"] = user_id

    # Same as the exchange path: a refresh must not resurrect a revoked session.
    if user_id is not None and user_role in ("teacher", "parent"):
        row = (
            db.query(Parent).filter(Parent.id == user_id).first()
            if user_role == "parent"
            else db.query(User).filter(User.id == user_id).first()
        )
        if row is not None:
            token_data["token_version"] = getattr(row, "token_version", 1) or 1
        elif long_token_version is not None:
            token_data["token_version"] = long_token_version
    new_long_lived_token = create_long_lived_access_token(data=token_data)

    return {"access_token": new_long_lived_token, "token_type": "bearer"}


class GoogleLoginRequest(BaseModel):
    google_token: str
    role: Optional[str] = None  # role picked on the login screen ("teacher"/"parent")


class PhoneLoginRequest(BaseModel):
    """Request body for asking an OTP code for a phone number."""

    phone: str
    type: str = "login"  # "login" or "register"


class PhoneVerifyRequest(BaseModel):
    """Request body for verifying OTP code and logging in with phone."""

    phone: str
    code: str
    type: str = "login"
    role: Optional[str] = None  # role picked on the login screen ("teacher"/"parent")


class FirebasePhoneLoginRequest(BaseModel):
    """Request body for logging in with Firebase Phone Auth ID token."""

    firebase_id_token: str
    role: Optional[str] = None  # role picked on the login screen ("teacher"/"parent")


class TelegramLoginStartResponse(BaseModel):
    token: str
    bot_username: str
    deep_link: str
    expires_in_seconds: int


# NOTE: For now we use a static OTP code for development.
# In production, replace this with a real SMS provider integration
# and a secure, per-request random code.
PHONE_LOGIN_STATIC_CODE = "123456"


def _require_insecure_static_phone_otp_enabled() -> None:
    """Keep the legacy fixed-code phone flow unreachable by default.

    Firebase Phone Auth is the production path. A public, reusable code would
    otherwise let anyone who knows an employee phone number take over the
    account and submit attendance as that employee.
    """
    if not settings.allow_insecure_static_phone_otp:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Legacy phone-code login is disabled for security. "
                "Use Firebase phone verification instead."
            ),
        )


class ForgotPasswordRequest(BaseModel):
    """Request body for requesting password reset OTP via email."""

    username: str


class PasswordResetVerify(BaseModel):
    """Request body for verifying OTP and resetting password."""

    username: str
    otp_code: str
    new_password: str
    # OTP is verified by Firebase on client side


@router.post("/login-google", response_model=Token)
async def login_with_google(
    login_request: GoogleLoginRequest, db: Session = Depends(get_db)
):
    """
    Login with Google ID token.

    Flow:
    1. Verify Google ID token with Firebase
    2. Extract email from token
    3. Check if email exists in database (users, parents tables)
    4. If exists → Issue JWT token
    5. If not exists → Return error: "You are not part of our school. Please contact administrator."

    Note: Students table does not have email column, so Google login only works for teachers and parents.
    """
    if not GOOGLE_AUTH_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not configured. Please install google-auth packages.",
        )

    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase Project ID is not configured. Please set FIREBASE_PROJECT_ID in environment variables.",
        )

    try:
        try:
            # Instantiate directly in the async handler
            thread_request = google_requests.Request()
            
            # 1. Try standard Google OAuth2 Token (from raw GoogleSignIn SDK)
            if not settings.google_client_id:
                raise ValueError("GOOGLE_CLIENT_ID not configured")
            id_info = google_id_token.verify_oauth2_token(
                login_request.google_token,
                thread_request,
                audience=settings.google_client_id,
            )
            
        except ValueError as oauth_err:
            # Native verify failed, do NOT fallback right now since we need to read the specific error!
            # The fallback to Firebase was causing it to show 'Certificate not found' because Firebase uses different certs.
            logger.error(f"OAuth2 verification natively failed: {oauth_err}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google authentication token: {str(oauth_err)}",
            )

        # Extract email
        email = id_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not found in Google account",
            )

        # Normalize email (lowercase for case-insensitive matching)
        email = email.lower().strip()

        # Check if email exists in database. Honour the role the user picked:
        # a teacher whose own child attends the school is in BOTH tables, and
        # always preferring the employee row logged such parents into the staff app.
        requested_role = (login_request.role or "").strip().lower() or None

        user = None if requested_role == "parent" else get_user_by_email(db, email)
        parent = (
            None
            if requested_role == "teacher"
            else db.query(Parent).filter(Parent.pEmail.ilike(email)).first()
        )

        # An unapproved/disabled account must not get in this way either.
        if user is not None and int(getattr(user, "status", 0) or 0) != 1:
            user = None
        if parent is not None and int(getattr(parent, "status", 0) or 0) != 1:
            parent = None

        if user is not None and parent is not None:
            logger.warning(f"Google login ambiguous - email in both tables: {email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This email is linked to both a staff and a parent account. "
                    "Please sign in with your username and password."
                ),
            )

        if user:
            # User exists → Login as teacher
            access_token = create_short_lived_access_token(
                data={
                    "sub": user.username,
                    "role": "teacher",
                    "user_id": user.id,
                    "token_version": getattr(user, "token_version", 1) or 1,
                }
            )
            logger.info(
                f"Google login successful for teacher: {email} (user_id: {user.id})"
            )
            return {"access_token": access_token, "token_type": "bearer"}

        if parent:
            # Parent exists → Login as parent
            access_token = create_short_lived_access_token(
                data={
                "sub": parent.username,
                "role": "parent",
                "user_id": parent.id,
                "token_version": getattr(parent, "token_version", 1) or 1,
            }
            )
            logger.info(
                f"Google login successful for parent: {email} (parent_id: {parent.id})"
            )
            return {"access_token": access_token, "token_type": "bearer"}

        # Email not found → Deny
        logger.warning(f"Google login denied - email not in database: {email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not part of our school. Please contact administrator.",
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Google login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during Google authentication: {str(e)}",
        )


# Phone matching lives in app/utils/phone.py so the auth layer can share it
# without importing this router (which would be circular).


def ensure_telegram_login_sessions_table(db: Session) -> None:
    """Create Telegram login session table if startup migration has not run yet."""
    bind = db.get_bind()
    is_mysql = bind.dialect.name == "mysql"
    if is_mysql:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_login_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                token VARCHAR(96) NOT NULL UNIQUE,
                telegram_user_id BIGINT NULL,
                private_chat_id BIGINT NULL,
                phone VARCHAR(50) NULL,
                first_name VARCHAR(255) NULL,
                last_name VARCHAR(255) NULL,
                username VARCHAR(255) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                verified_at DATETIME NULL,
                consumed_at DATETIME NULL,
                INDEX idx_tls_token (token),
                INDEX idx_tls_telegram_user_id (telegram_user_id),
                INDEX idx_tls_status_expires (status, expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
    else:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_login_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token VARCHAR(96) NOT NULL UNIQUE,
                telegram_user_id BIGINT NULL,
                private_chat_id BIGINT NULL,
                phone VARCHAR(50) NULL,
                first_name VARCHAR(255) NULL,
                last_name VARCHAR(255) NULL,
                username VARCHAR(255) NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                verified_at DATETIME NULL,
                consumed_at DATETIME NULL
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_tls_token ON telegram_login_sessions(token)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_tls_telegram_user_id ON telegram_login_sessions(telegram_user_id)"))
    db.commit()


def _find_teachers_by_phone(db: Session, phone_variations: list[str]) -> list:
    if not phone_variations:
        return []
    return db.query(User).filter(User.phone.in_(phone_variations)).all()


def _find_parents_by_phone(db: Session, phone_variations: list[str]) -> list:
    if not phone_variations:
        return []
    return (
        db.query(Parent)  # type: ignore
        .filter(
            (Parent.fatherPhone.in_(phone_variations))
            | (Parent.motherPhone.in_(phone_variations))
            | (Parent.gPhone.in_(phone_variations))
        )
        .all()
    )


def _create_phone_login_token_response(
    db: Session, phone: str, requested_role: Optional[str] = None
) -> dict:
    """Map a verified phone number to exactly one account and issue a token.

    ``requested_role`` is the role the user picked on the login screen. Honour it:
    a teacher whose own child attends the school exists in BOTH tables, and
    silently preferring the employee row logged such parents into the staff app.

    When a phone maps to more than one account we refuse instead of guessing —
    taking "the first row" is how someone ends up inside a stranger's account.
    """
    phone = (phone or "").strip()
    phone_variations = get_phone_variations(phone)
    logger.info(
        f"Phone login - checking variations for {phone}: {phone_variations}"
    )

    requested_role = (requested_role or "").strip().lower() or None

    teachers = [] if requested_role == "parent" else _find_teachers_by_phone(db, phone_variations)
    parents = [] if requested_role == "teacher" else _find_parents_by_phone(db, phone_variations)

    # Inactive/unapproved accounts must not get a token here. /login-role already
    # refuses them; the phone path must not be a way around that check.
    active_teachers = [t for t in teachers if int(getattr(t, "status", 0) or 0) == 1]
    active_parents = [p for p in parents if int(getattr(p, "status", 0) or 0) == 1]

    if (teachers or parents) and not (active_teachers or active_parents):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is pending administrative approval. Please try again after approval.",
        )

    # Two accounts of the SAME kind sharing this number is a data error: the
    # account is locked until an administrator fixes it. Report it the same way
    # every other entry point does so the app shows one consistent dialog.
    if len(active_teachers) > 1 or len(active_parents) > 1:
        locked_type = "teacher" if len(active_teachers) > 1 else "parent"
        locked = active_teachers[0] if locked_type == "teacher" else active_parents[0]
        logger.warning(
            "Phone login refused for %s: %d %s account(s) share it",
            phone,
            len(active_teachers) if locked_type == "teacher" else len(active_parents),
            locked_type,
        )
        # Raises 423 when the lock is on. When it is off we still must not guess
        # which of the two accounts this is, so refuse the phone login and point
        # them at username + password, which is unambiguous.
        _assert_phone_not_shared(db, locked.id, locked_type)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This phone number is registered on more than one account, so we "
                "cannot tell which one is yours. Please sign in with your username "
                "and password, or contact the administrator."
            ),
        )

    if len(active_teachers) + len(active_parents) > 1:
        # One staff row and one parent row: a teacher whose own child attends the
        # school. Legitimate, but we cannot tell which they want without the role
        # button, which older app builds do not send.
        logger.info(
            "Phone login needs a role for %s: %d teacher(s), %d parent(s)",
            phone,
            len(active_teachers),
            len(active_parents),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This phone number is used for both a staff and a parent account. "
                "Please choose Teacher or Parent on the login screen, or sign in "
                "with your username and password."
            ),
        )

    # A single match is not proof of uniqueness. The lookup above compares the
    # typed number's variations against whatever string the column holds, which
    # misses a row stored as "+855 96 555 444" — so the OTHER account sharing
    # this number can be invisible here. Conflict detection compares canonical
    # numbers on both sides, so ask it before issuing anything.
    only = (active_teachers or active_parents)
    if len(only) == 1:
        kind = "teacher" if active_teachers else "parent"
        if find_conflict_for_account(db, only[0].id, kind) is not None:
            logger.warning(
                "Phone login refused for %s: %s %s shares the number with another account",
                phone, kind, only[0].id,
            )
            _assert_phone_not_shared(db, only[0].id, kind)  # 423 when the lock is on
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This phone number is registered on more than one account, so we "
                    "cannot tell which one is yours. Please sign in with your username "
                    "and password, or contact the administrator."
                ),
            )

    if active_teachers:
        teacher = active_teachers[0]
        access_token = create_short_lived_access_token(
            data={
                "sub": teacher.username,
                "role": "teacher",
                "user_id": teacher.id,
                "token_version": getattr(teacher, "token_version", 1) or 1,
            }
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "registered": True,
            "role": "teacher",
        }

    if active_parents:
        parent = active_parents[0]
        access_token = create_short_lived_access_token(
            data={
                "sub": parent.username,
                "role": "parent",
                "user_id": parent.id,
                "token_version": getattr(parent, "token_version", 1) or 1,
            }
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "registered": True,
            "role": "parent",
        }

    return {
        "registered": False,
        "message": "This phone number is not registered in PAMA. Please contact the administrator.",
    }


@router.post("/telegram-login/start", response_model=TelegramLoginStartResponse)
async def start_telegram_login(db: Session = Depends(get_db)):
    """
    Start Telegram login.

    Telegram does not expose phone through OAuth/login widget. The bot must ask the
    user to share their own Telegram contact, then the backend maps that phone to
    the same user lookup used by phone login.
    """
    ensure_telegram_login_sessions_table(db)

    from ...models.telegram_attendance_settings import TelegramAttendanceSettings
    import httpx

    logger.info("Telegram login start requested from app")
    settings_row = db.query(TelegramAttendanceSettings).first()
    bot_token = settings_row.bot_token if settings_row and settings_row.bot_token else None
    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot is not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = res.json()
            if not data.get("ok") or not data.get("result", {}).get("username"):
                raise ValueError("Telegram bot username not available")
            bot_username = data["result"]["username"]
    except Exception as e:
        logger.error(f"Unable to read Telegram bot username: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to contact Telegram bot.",
        )

    login_token = f"login_{uuid.uuid4().hex}{uuid.uuid4().hex[:12]}"
    bind = db.get_bind()
    if bind.dialect.name == "mysql":
        db.execute(text("""
            INSERT INTO telegram_login_sessions (token, status, expires_at)
            VALUES (:token, 'pending', DATE_ADD(NOW(), INTERVAL 10 MINUTE))
        """), {"token": login_token})
    else:
        db.execute(text("""
            INSERT INTO telegram_login_sessions (token, status, expires_at)
            VALUES (:token, 'pending', datetime('now', '+10 minutes'))
        """), {"token": login_token})
    db.commit()
    logger.info(
        "Telegram login session created: token_prefix=%s bot_username=%s",
        login_token[:18],
        bot_username,
    )

    return TelegramLoginStartResponse(
        token=login_token,
        bot_username=bot_username,
        deep_link=f"https://t.me/{bot_username}?start={login_token}",
        expires_in_seconds=600,
    )


@router.get("/telegram-login/status/{login_token}")
async def get_telegram_login_status(
    login_token: str,
    consume: bool = False,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
):
    ensure_telegram_login_sessions_table(db)
    logger.info(
        "Telegram login status requested: token_prefix=%s consume=%s",
        login_token[:18] if login_token else None,
        consume,
    )

    row = db.execute(text("""
        SELECT id, status, phone, consumed_at
        FROM telegram_login_sessions
        WHERE token = :token AND expires_at > NOW()
        LIMIT 1
    """), {"token": login_token}).fetchone()

    if not row:
        logger.info("Telegram login status: expired/not found")
        return {"status": "expired", "registered": False}

    session_id, session_status, phone, consumed_at = row
    logger.info(
        "Telegram login status row: session_id=%s status=%s phone_present=%s consumed=%s",
        session_id,
        session_status,
        bool(phone),
        consumed_at is not None,
    )
    if consumed_at is not None:
        return {"status": "consumed", "registered": False}

    if session_status != "verified" or not phone:
        return {"status": session_status or "pending", "registered": False}

    result = _create_phone_login_token_response(db, phone, requested_role=role)
    if not consume:
        return {
            "status": "verified",
            "registered": result.get("registered") is True,
            "message": result.get("message"),
            "role": result.get("role"),
        }

    db.execute(text("""
        UPDATE telegram_login_sessions
        SET consumed_at = NOW(), status = 'consumed'
        WHERE id = :id
    """), {"id": session_id})
    db.commit()

    return {"status": "verified", **result}


@router.post("/phone/request-code")
async def request_phone_login_code(
    request: PhoneLoginRequest, db: Session = Depends(get_db)
):
    """
    Request a one-time code (OTP) to login or register by phone number.

    For now this uses a static code (123456) and **does not send SMS**.
    If type == "login", it validates that the phone exists in the database.
    If type == "register", it allows any phone number (for verification).
    """
    _require_insecure_static_phone_otp_enabled()
    phone = request.phone.strip()
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Phone number is required"
        )

    # For registration, we just generate the code without checking DB
    # In a real app, you might want to check if it's ALREADY registered
    # and warn the user, but for now we allow verification.
    if request.type == "register":
        # Check if phone already exists in Users (teachers) or Parents
        phone_variations = get_phone_variations(phone)

        existing_teacher = (
            db.query(User).filter(User.phone.in_(phone_variations)).first()
        )
        existing_parent = None
        if not existing_teacher:
            existing_parent = (
                db.query(Parent)  # type: ignore
                .filter(
                    (Parent.fatherPhone.in_(phone_variations))
                    | (Parent.motherPhone.in_(phone_variations))
                )
                .first()
            )

        if existing_teacher or existing_parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is already registered. Please login instead.",
            )

        return {
            "detail": "OTP code generated successfully (development mode).",
            "code": PHONE_LOGIN_STATIC_CODE,
        }

    # === LOGIN FLOW (Default) ===
    # Only allow if phone exists in DB

    # Generate all possible formats to check against DB
    phone_variations = get_phone_variations(phone)
    logger.info(f"Checking phone variations: {phone_variations}")

    # Try to find teacher by any of the phone variations
    teacher = db.query(User).filter(User.phone.in_(phone_variations)).first()

    # Try to find parent by father/mother phone if not found in users
    parent = None
    if teacher is None:
        parent = (
            db.query(Parent)  # type: ignore
            .filter(
                (Parent.fatherPhone.in_(phone_variations))
                | (Parent.motherPhone.in_(phone_variations))
            )
            .first()
        )

    if teacher is None and parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Phone number not found in system",
        )

    # In real production we would send SMS here.
    # For development, return the static code so user can enter it.
    return {
        "detail": "OTP code generated successfully (development mode).",
        "code": PHONE_LOGIN_STATIC_CODE,
    }


@router.post("/phone/login", response_model=Token)
async def login_with_phone(request: PhoneVerifyRequest, db: Session = Depends(get_db)):
    """
    Login using phone number and one-time code (OTP).

    Current behavior (development):
      - Uses static code 123456 (PHONE_LOGIN_STATIC_CODE).
      - Finds teacher by User.phone OR parent by fatherPhone/motherPhone.
      - Issues the same short-lived JWT as other login methods.

    In production you should replace this with real, per-request OTP verification.
    """
    _require_insecure_static_phone_otp_enabled()
    phone = request.phone.strip()
    code = request.code.strip()

    if not phone or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone and code are required",
        )

    if code != PHONE_LOGIN_STATIC_CODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code"
        )

    # Same resolver as the other phone paths: role-aware, refuses ambiguous
    # matches, and rejects unapproved accounts.
    result = _create_phone_login_token_response(db, phone, requested_role=request.role)
    if not result.get("registered"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found in system"
        )
    return result


@router.post("/phone/verify")
async def verify_phone_code_only(
    request: PhoneVerifyRequest,
):
    """
    Verify OTP code without logging in. Used for registration flow.
    """
    _require_insecure_static_phone_otp_enabled()
    code = request.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Code is required"
        )

    if code != PHONE_LOGIN_STATIC_CODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code"
        )

    return {"detail": "Phone verified successfully"}


@router.post("/login-phone-firebase")
async def login_with_phone_firebase(
    request: FirebasePhoneLoginRequest, db: Session = Depends(get_db)
):
    """
    Login using Firebase Phone Auth ID token.

    Flow:
      1. App signs in with Firebase using phone SMS code.
      2. App sends Firebase ID token to this endpoint.
      3. Backend verifies ID token against Firebase project (multischool-pro).
      4. Backend maps phone_number to teacher/parent and issues JWT.
    """
    if not settings.firebase_project_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase project ID is not configured. Please set FIREBASE_PROJECT_ID.",
        )

    try:
        request_obj = google_requests.Request()
        # Verify Firebase ID token — offloaded to thread to avoid blocking event loop
        id_info = await run_in_threadpool(
            lambda: google_id_token.verify_firebase_token(
                request.firebase_id_token,
                request_obj,
                settings.firebase_project_id,
            )
        )
    except ValueError as e:
        logger.error(f"Invalid Firebase phone ID token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase phone authentication token",
        )
    except Exception as e:
        logger.error(f"Error verifying Firebase phone ID token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error verifying Firebase phone token",
        )

    phone = id_info.get("phone_number")
    if not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number not found in Firebase token",
        )

    phone = phone.strip()

    # Shared resolver: honours the role picked on the login screen, refuses to
    # guess when a number matches several accounts, and rejects unapproved ones.
    result = _create_phone_login_token_response(db, phone, requested_role=request.role)
    if not result.get("registered"):
        logger.info(f"Phone {phone} not registered yet. Proceeding to registration.")
        return {
            "registered": False,
            "message": "Phone not registered yet. Proceed with registration.",
        }
    return result


# ============================================================================
# TELEGRAM OFFICIAL OTP LOGIN (MTProto via Telethon)
# ============================================================================
# Users enter their phone → Telegram sends a 5-digit code via their Telegram app
# (the same way Telegram itself sends login codes on new devices)
# ============================================================================

def _telegram_otp_error(
    status_code: int,
    code: str,
    *,
    fallback_to_sms: bool = False,
    retry_after: Optional[int] = None,
):
    """Stable machine-readable error details consumed by Flutter clients."""
    detail = {"code": code, "fallback_to_sms": fallback_to_sms}
    headers = None
    if retry_after is not None:
        detail["retry_after_seconds"] = retry_after
        headers = {"Retry-After": str(retry_after)}
    raise HTTPException(status_code=status_code, detail=detail, headers=headers)


class TelegramOtpSendRequest(BaseModel):
    phone: str  # e.g. "0961234567" or "+85596..."


class TelegramOtpVerifyRequest(BaseModel):
    phone: str
    code: str            # 5-digit code received in Telegram app
    phone_code_hash: str # returned by /send, must be passed back
    role: Optional[str] = None  # role picked on the login screen ("teacher"/"parent")


def _normalize_to_e164(phone: str) -> str:
    """Validate and normalize a Cambodian/international phone number."""
    import phonenumbers

    value = phone.strip()
    if not value:
        raise ValueError("phone_required")
    try:
        parsed = phonenumbers.parse(value, "KH")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("invalid_phone") from exc
    if not phonenumbers.is_possible_number(parsed) or not phonenumbers.is_valid_number(parsed):
        raise ValueError("invalid_phone")
    return phonenumbers.format_number(
        parsed,
        phonenumbers.PhoneNumberFormat.E164,
    )


def _masked_phone(phone: str) -> str:
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"


def _store_telegram_otp_session(
    db: Session,
    *,
    phone: str,
    phone_code_hash: str,
    session_string: str,
) -> None:
    """Keep exactly one current send session for a phone on MySQL or SQLite."""
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    params = {
        "phone": phone,
        "hash": phone_code_hash,
        "session": session_string,
        "expires_at": expires_at,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "mysql":
        statement = """
            INSERT INTO telegram_otp_sessions
                (phone, phone_code_hash, session_string, expires_at)
            VALUES (:phone, :hash, :session, :expires_at)
            ON DUPLICATE KEY UPDATE
                phone_code_hash = VALUES(phone_code_hash),
                session_string = VALUES(session_string),
                expires_at = VALUES(expires_at),
                used_at = NULL,
                registration_token_hash = NULL,
                registration_expires_at = NULL,
                registration_used_at = NULL
        """
    elif dialect == "sqlite":
        statement = """
            INSERT INTO telegram_otp_sessions
                (phone, phone_code_hash, session_string, expires_at)
            VALUES (:phone, :hash, :session, :expires_at)
            ON CONFLICT(phone) DO UPDATE SET
                phone_code_hash = excluded.phone_code_hash,
                session_string = excluded.session_string,
                expires_at = excluded.expires_at,
                used_at = NULL,
                registration_token_hash = NULL,
                registration_expires_at = NULL,
                registration_used_at = NULL
        """
    else:
        db.execute(
            text("DELETE FROM telegram_otp_sessions WHERE phone = :phone"),
            {"phone": phone},
        )
        statement = """
            INSERT INTO telegram_otp_sessions
                (phone, phone_code_hash, session_string, expires_at)
            VALUES (:phone, :hash, :session, :expires_at)
        """
    db.execute(text(statement), params)
    db.commit()


@router.post("/telegram-otp/send")
async def send_telegram_otp(
    payload: TelegramOtpSendRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """Send Telegram's official login code, with explicit SMS-fallback hints."""
    phone = payload.phone.strip()
    if not phone:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "phone_required")

    try:
        e164_phone = _normalize_to_e164(phone)
    except ValueError:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "invalid_phone")

    if not allow_telegram_otp_send(e164_phone, throttle_ip(http_request)):
        _telegram_otp_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            retry_after=telegram_otp_retry_after_seconds(),
        )

    if not settings.telegram_api_id or not settings.telegram_api_hash:
        _telegram_otp_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "credentials_not_configured",
            fallback_to_sms=True,
        )

    from app.core.auto_deps import ensure_package

    try:
        ensure_package("telethon", "telethon>=1.36.0")
        from telethon import TelegramClient
        from telethon.errors import (
            FloodWaitError,
            PhoneNumberInvalidError,
            PhoneNumberUnoccupiedError,
        )
        from telethon.sessions import StringSession
    except Exception as exc:
        logger.error("Telegram OTP dependency is unavailable: %s", exc)
        _telegram_otp_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "telethon_unavailable",
            fallback_to_sms=True,
        )

    client = None
    try:
        client = TelegramClient(
            StringSession(),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        result = await client.send_code_request(e164_phone)
        session_string = client.session.save()
        phone_code_hash = str(result.phone_code_hash or "").strip()
        if not phone_code_hash or not session_string:
            raise RuntimeError("Telegram returned an incomplete send session")
        code_length = int(
            getattr(getattr(result, "type", None), "length", 5) or 5
        )
    except PhoneNumberInvalidError:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "invalid_phone")
    except PhoneNumberUnoccupiedError:
        _telegram_otp_error(
            status.HTTP_400_BAD_REQUEST,
            "phone_not_on_telegram",
            fallback_to_sms=True,
        )
    except FloodWaitError as exc:
        _telegram_otp_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            retry_after=max(int(getattr(exc, "seconds", 60) or 60), 1),
        )
    except Exception as exc:
        error_text = f"{type(exc).__name__} {exc}".lower()
        network_failure = any(
            marker in error_text
            for marker in (
                "connection",
                "connect",
                "network",
                "timeout",
                "timedout",
                "permission",
                "operation not permitted",
                "oserror",
            )
        )
        if network_failure:
            logger.warning(
                "Telegram network unreachable for %s: %s",
                _masked_phone(e164_phone),
                exc,
            )
            _telegram_otp_error(
                status.HTTP_502_BAD_GATEWAY,
                "telegram_unreachable",
                fallback_to_sms=True,
            )
        logger.error(
            "Telegram OTP send error for %s: %s",
            _masked_phone(e164_phone),
            exc,
            exc_info=True,
        )
        _telegram_otp_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "send_failed",
            fallback_to_sms=True,
        )
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                logger.debug("Could not disconnect Telegram send client", exc_info=True)

    try:
        _store_telegram_otp_session(
            db,
            phone=e164_phone,
            phone_code_hash=phone_code_hash,
            session_string=session_string,
        )
    except Exception as exc:
        db.rollback()
        logger.error("Could not persist Telegram OTP session: %s", exc, exc_info=True)
        _telegram_otp_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "send_failed",
            fallback_to_sms=True,
        )

    logger.info("Telegram OTP sent to %s", _masked_phone(e164_phone))
    return {
        "detail": "Verification code sent to your Telegram app.",
        "phone_code_hash": phone_code_hash,
        "code_length": max(4, min(code_length, 8)),
    }


@router.post("/telegram-otp/verify")
async def verify_telegram_otp(request: TelegramOtpVerifyRequest, db: Session = Depends(get_db)):
    """
    Verify the OTP code the user received in their Telegram app.
    If valid, maps the phone to a school user and returns a JWT token.
    """
    try:
        e164_phone = _normalize_to_e164(request.phone)
    except ValueError:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "invalid_phone")
    code = request.code.strip()
    phone_code_hash = request.phone_code_hash.strip()

    if not code or not phone_code_hash:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "code_and_hash_required")

    # Load stored Telethon session
    row = db.execute(text("""
        SELECT id, phone_code_hash, session_string
        FROM telegram_otp_sessions
        WHERE phone = :phone
          AND expires_at > NOW()
          AND used_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
    """), {"phone": e164_phone}).fetchone()

    if not row:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "session_expired")

    session_id, stored_hash, session_string = row

    if stored_hash != phone_code_hash:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "invalid_session")

    try:
        from telethon import TelegramClient
        from telethon.errors import (
            FloodWaitError,
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            SessionPasswordNeededError,
        )
        from telethon.sessions import StringSession
    except ImportError:
        _telegram_otp_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "telethon_unavailable",
        )

    client = None
    try:
        client = TelegramClient(
            StringSession(session_string),
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        await client.connect()
        try:
            await client.sign_in(
                phone=e164_phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )
            try:
                await client.log_out()
            except Exception:
                logger.warning(
                    "Telegram code verified but temporary logout failed for %s",
                    _masked_phone(e164_phone),
                    exc_info=True,
                )
        except SessionPasswordNeededError:
            # The code itself was correct.  Telegram 2FA still prevents this
            # temporary client from obtaining account access.
            pass
    except PhoneCodeExpiredError:
        _telegram_otp_error(status.HTTP_400_BAD_REQUEST, "code_expired")
    except PhoneCodeInvalidError:
        _telegram_otp_error(status.HTTP_401_UNAUTHORIZED, "incorrect_code")
    except FloodWaitError as exc:
        _telegram_otp_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_attempts",
            retry_after=max(int(getattr(exc, "seconds", 60) or 60), 1),
        )
    except Exception as exc:
        logger.error(
            "Telegram OTP verify error for %s: %s",
            _masked_phone(e164_phone),
            exc,
            exc_info=True,
        )
        _telegram_otp_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "verification_failed",
        )
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                logger.debug("Could not disconnect Telegram verify client", exc_info=True)

    # Remove the MTProto session secret as soon as code possession is proven.
    # New registrations receive a separate opaque proof that has no Telegram
    # account capability and is consumed by the account-creation transaction.
    result = _create_phone_login_token_response(
        db,
        e164_phone,
        requested_role=request.role,
    )
    now = datetime.utcnow()
    update_result = db.execute(
        text(
            """
            UPDATE telegram_otp_sessions
            SET used_at = :now,
                session_string = NULL,
                registration_token_hash = NULL,
                registration_expires_at = NULL,
                registration_used_at = NULL
            WHERE id = :session_id
              AND used_at IS NULL
            """
        ),
        {"now": now, "session_id": session_id},
    )
    if update_result.rowcount != 1:
        db.rollback()
        _telegram_otp_error(status.HTTP_409_CONFLICT, "invalid_session")
    if not result.get("registered"):
        result["registration_token"] = issue_registration_proof(
            db,
            session_id=int(session_id),
        )
    db.commit()
    logger.info(
        "Telegram OTP verify successful for %s registered=%s",
        _masked_phone(e164_phone),
        result.get("registered"),
    )
    return result


# ============================================================================
# FORGOT PASSWORD ENDPOINTS - DISABLED PER USER REQUEST
# ============================================================================
# Email OTP service code is available in app/services/email_service.py
# if this feature is needed in the future.
# ============================================================================


@router.get("/users", response_model=list[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get list of users (admin only)."""
    if current_user.role != 1:  # 1 = admin
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.get("/admin/phone-conflicts")
async def get_phone_conflicts(
    db: Session = Depends(get_db),
    admin_user_id: int = Depends(require_admin),
):
    """List every phone number shared by two or more accounts of the same kind.

    These accounts are locked out of the app until an administrator gives each
    one its own number, so this is the worklist for clearing that.
    """
    conflicts = list_all_conflicts(db)

    items = []
    for conflict in conflicts:
        if conflict.account_type == "parent":
            rows = (
                db.query(Parent.id, Parent.username, Parent.fatherName, Parent.motherName)
                .filter(Parent.id.in_(conflict.account_ids))
                .all()
            )
            accounts = [
                {
                    "id": r[0],
                    "username": r[1],
                    "name": r[2] or r[3] or "",
                }
                for r in rows
            ]
        else:
            rows = (
                db.query(User.id, User.username, User.eName, User.kName)
                .filter(User.id.in_(conflict.account_ids))
                .all()
            )
            accounts = [
                {
                    "id": r[0],
                    "username": r[1],
                    "name": r[2] or r[3] or "",
                }
                for r in rows
            ]

        # Whether each account actually has the app installed. Someone who is
        # not on the app is not inconvenienced yet, so the office can leave them
        # until later.
        on_app = accounts_on_app(db, conflict.account_type, conflict.account_ids)
        for a in accounts:
            a["on_app"] = bool(on_app.get(int(a["id"]), False))

        items.append(
            {
                "phone": conflict.phone,
                "account_type": conflict.account_type,
                "account_count": len(conflict.account_ids),
                "on_app_count": sum(1 for a in accounts if a["on_app"]),
                "accounts": accounts,
            }
        )

    return {
        "total": len(items),
        "locked_accounts": sum(i["account_count"] for i in items),
        "on_app_accounts": sum(i["on_app_count"] for i in items),
        "lock_enabled": lock_is_enabled(db),
        "items": items,
    }


class PhoneConflictLockRequest(BaseModel):
    enabled: bool


@router.put("/admin/phone-conflict-lock")
async def update_phone_conflict_lock(
    body: PhoneConflictLockRequest,
    db: Session = Depends(get_db),
    admin_user_id: int = Depends(require_admin),
):
    """Turn the hard lockout on or off without a redeploy.

    On: accounts sharing a phone number are stopped at login and on app launch,
    and told to contact the administrator. Off: they keep using the app normally
    and only their phone sign-in is refused, which stays true either way — that
    is the ambiguity that could sign someone into a stranger's account.
    """
    try:
        enabled = set_lock_enabled(db, body.enabled)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    conflicts = list_all_conflicts(db)
    affected = sum(len(c.account_ids) for c in conflicts)
    logger.warning(
        "Admin %s set the phone-conflict lock to %s (%d account(s) affected)",
        admin_user_id, enabled, affected,
    )
    return {
        "lock_enabled": enabled,
        "affected_accounts": affected,
        "message": (
            f"{affected} account(s) must now contact an administrator before "
            "using the app."
            if enabled
            else f"{affected} account(s) can use the app again with their "
            "username and password."
        ),
    }


@router.get("/admin/network-diagnostics")
async def get_network_diagnostics(
    request: Request,
    admin_user_id: int = Depends(require_admin),
):
    """Show what the server sees about who is calling, to configure proxy trust.

    TRUSTED_PROXY_RANGES has to list the reverse proxy in front of this app, and
    getting it wrong in either direction is bad: leave it empty and forwarded
    headers stay untrusted, set it too wide and anyone can spoof their IP. There
    is no way to guess the value, so this reports the address the app actually
    receives connections from. Call it from any browser while signed in as an
    admin and use `peer_ip` — that is your load balancer.
    """
    peer_ip = (
        str(request.client.host) if request.client and request.client.host else None
    )
    forwarded = request.headers.get("X-Forwarded-For")
    configured = str(settings.trusted_proxy_ranges or "").strip()

    if not configured:
        if forwarded:
            advice = (
                f"A proxy is forwarding to you but TRUSTED_PROXY_RANGES is empty, so "
                f"its header is ignored. Set TRUSTED_PROXY_RANGES={peer_ip} "
                f"(or the CIDR covering it) to trust it."
            )
        else:
            advice = (
                "No proxy detected — clients appear to connect directly. Leave "
                "TRUSTED_PROXY_RANGES empty unless you add a load balancer."
            )
    elif peer_is_trusted_proxy(peer_ip or ""):
        advice = "Configured correctly: this request arrived via a trusted proxy."
    else:
        advice = (
            f"TRUSTED_PROXY_RANGES is set but does not cover {peer_ip}. Either add "
            f"it, or this request did not come through your load balancer."
        )

    return {
        "peer_ip": peer_ip,
        "x_forwarded_for": forwarded,
        "trusted_proxy_ranges": configured or None,
        "peer_is_trusted_proxy": peer_is_trusted_proxy(peer_ip or ""),
        "resolved_client_ip": client_ip(request),
        "cors_origins": settings.cors_origins,
        "cors_wildcard_in_use": "*" in (settings.cors_origins or []),
        "advice": advice,
    }


class ForceLogoutRequest(BaseModel):
    """Which accounts to sign out. Empty means every conflicted account."""

    parent_ids: Optional[list[int]] = None
    all_conflicted: bool = False


@router.post("/admin/force-logout-parents")
async def force_logout_parents(
    body: ForceLogoutRequest,
    db: Session = Depends(get_db),
    admin_user_id: int = Depends(require_admin),
):
    """End parent app sessions immediately.

    A token issued before the phone login refused ambiguous numbers may belong
    to the wrong family, and there is no way to tell from the token itself —
    it was signed legitimately for whichever account the old code picked. The
    only safe remedy is to end those sessions and have people sign in again
    with a username and password, which is unambiguous.

    Bumping token_version invalidates every token already issued to that parent,
    including long-lived ones that would otherwise last 60 days.
    """
    target_ids: list[int] = []

    if body.all_conflicted:
        target_ids = [
            i
            for c in list_all_conflicts(db)
            if c.account_type == "parent"
            for i in c.account_ids
        ]
    elif body.parent_ids:
        target_ids = [int(i) for i in body.parent_ids]

    target_ids = sorted(set(target_ids))
    if not target_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Give parent_ids, or set all_conflicted to sign out every "
                   "account sharing a phone number.",
        )

    updated = (
        db.query(Parent)
        .filter(Parent.id.in_(target_ids))
        .update(
            {Parent.token_version: Parent.token_version + 1},
            synchronize_session=False,
        )
    )
    db.commit()

    # Drop their push registrations too, so the next launch is a clean sign-in
    # rather than a device still receiving notifications for a dead session.
    try:
        from ...models import DeviceToken

        db.query(DeviceToken).filter(
            DeviceToken.user_id.in_(target_ids),
            DeviceToken.user_type == "parent",
        ).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        logger.error("Could not clear device tokens after force-logout: %s", e)

    logger.warning(
        "Admin %s force-logged-out %d parent account(s): %s",
        admin_user_id, updated, target_ids[:50],
    )
    return {
        "signed_out": updated,
        "parent_ids": target_ids,
        "message": f"{updated} parent account(s) signed out. They will need to "
                   "sign in again with their username and password.",
    }
