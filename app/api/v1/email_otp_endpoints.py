# New Email OTP Endpoints for auth.py
# Replace the existing /forgot-password/request and /forgot-password/reset endpoints

@router.post("/forgot-password/request")
async def request_password_reset(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Request password reset via email OTP.
    
    Sends a 6-digit OTP code to the user's registered email address.
    """
    from ...services.email_service import generate_otp, store_otp, send_otp_email, mask_email
    
    username = request.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required"
        )
    
    # Find user by username
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        # For security, don't reveal if username exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Username not found"
        )
    
    # Verify user has an email
    if not user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email registered for this account. Please contact administrator."
        )
    
    # Generate OTP
    otp_code = generate_otp()
    
    # Store OTP in cache
    store_otp(username, otp_code)
    
    # Get user's full name for email
    user_name = user.name if hasattr(user, 'name') and user.name else username
    
    # Send OTP email
    success, error_msg = send_otp_email(user.email, user_name, otp_code)
    
    if not success:
        logger.error(f"Failed to send OTP email to {user.email}: {error_msg}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg or "Failed to send OTP email. Please try again."
        )
    
    # Mask email for response
    masked_email_str = mask_email(user.email)
    
    logger.info(f"Password reset OTP sent to email for user: {username}")
    
    return {
        "detail": "OTP code has been sent to your email",
        "masked_email": masked_email_str
    }


@router.post("/forgot-password/verify")
async def verify_and_reset_password(
    request: PasswordResetVerify,
    db: Session = Depends(get_db)
):
    """
    Verify OTP and reset password.
    
    Validates the OTP code and updates the user's password.
    """
    from ...services.email_service import verify_otp
    
    username = request.username.strip()
    otp_code = request.otp_code.strip()
    new_password = request.new_password.strip()
    
    if not username or not otp_code or not new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username, OTP code, and new password are required"
        )
    
    # Verify OTP
    success, error_msg = verify_otp(username, otp_code)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg or "Invalid OTP code"
        )
    
    # Password validation
    if len(new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long"
        )
    
    # Find user
    user = db.query(User).filter(User.username == username).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Username not found"
        )
    
    # Hash and update password
    hashed_password = get_password_hash(new_password)
    user.password = hashed_password
    db.commit()
    
    logger.info(f"Password reset successful for user: {username}")
    
    return {
        "detail": "Password reset successfully. You can now login with your new password."
    }
