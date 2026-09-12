from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from ..core.database import get_db
from ..schemas import Token, UserCreate, UserResponse
from ..services.crud import create_user, get_user_by_username, get_user_by_email
from ..utils import authenticate_user, async_authenticate_user, create_access_token, get_password_hash, get_current_active_user
from ..core.config import settings
from ..models import User

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user."""
    # Check if username already exists
    if get_user_by_username(db, user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if get_user_by_email(db, user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    return create_user(db=db, user=user)

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login and get access token."""
    user = await async_authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user information including allowed branches."""
    from sqlalchemy import text
    
    # Get allowed branches from attendance__allowed_branches table
    allowed_query = text(
        "SELECT branch_id FROM attendance__allowed_branches WHERE user_id = :user_id"
    )
    allowed_result = db.execute(allowed_query, {"user_id": current_user.id}).fetchall()
    allowed_branches = [row[0] for row in allowed_result]
    
    # Create response dict with all user fields plus allowed_branches
    user_dict = {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "status": current_user.status,
        "eName": current_user.eName,
        "kName": current_user.kName,
        "phone": current_user.phone,
        "workplace": current_user.workplace,
        "workplace_id": current_user.workplace,
        "branch_id": current_user.workplace,
        "allowed_branches": allowed_branches,
        "allowedBranches": allowed_branches,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
    }
    
    return user_dict

@router.get("/users", response_model=list[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of users (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    users = db.query(User).offset(skip).limit(limit).all()
    return users
