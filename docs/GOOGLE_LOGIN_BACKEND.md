# Google Login Backend Implementation

## Overview

This document explains the backend implementation for Google Sign-In authentication.

## Requirements

- **Case 1:** Email exists in database → Login (issue JWT)
- **Case 2:** Email does NOT exist → Deny with message

---

## What We Need from Firebase

### 1. Firebase Web Client ID

From Firebase Console:
- Go to: **Authentication → Sign-in method → Google**
- Copy the **Web client ID**
- Format: `123456789-abcdefghijklmnop.apps.googleusercontent.com`

This is used to verify Google ID tokens on the backend.

### 2. Firebase Project Configuration

- **Project ID**: Your Firebase project ID
- **Project Name**: Your Firebase project name

---

## Implementation Plan

### Step 1: Install Dependencies

Add to `requirements.txt`:
```txt
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
```

### Step 2: Add Configuration

In `app/core/config.py`:
```python
class Settings(BaseSettings):
    # ... existing settings ...
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
```

In `.env`:
```
GOOGLE_CLIENT_ID=your-firebase-web-client-id.apps.googleusercontent.com
```

### Step 3: Create Endpoint

New endpoint in `app/api/v1/auth.py`:

```python
@router.post("/login-google", response_model=Token)
async def login_with_google(
    google_token: str,
    db: Session = Depends(get_db)
):
    """
    Login with Google ID token.
    
    Flow:
    1. Verify Google ID token
    2. Extract email
    3. Check if email exists in database
    4. If exists → Issue JWT
    5. If not → Return error
    """
```

### Step 4: Database Check Logic

Check email in:
1. `users` table (teachers) - column: `email`
2. `students` table - column: `email` (verify exists)
3. `parents` table - column: `pEmail`

---

## Database Schema Verification

### Required Columns

1. **users.email** ✅ (already exists) - Column: `email` (String, nullable)
2. **students.email** ❌ (does NOT exist) - Students table has no email column
3. **parents.pEmail** ✅ (already exists) - Column: `pEmail` (String, nullable)

**Note:** Students table does not have an email column. Google login will only work for:
- Teachers (users table)
- Parents (parents table)

If you need Google login for students, you'll need to add an `email` column to the `students` table.

---

## Error Response Format

### Success (200)
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### Email Not Found (403)
```json
{
  "detail": "You are not part of our school. Please contact administrator."
}
```

### Invalid Token (401)
```json
{
  "detail": "Invalid Google token"
}
```

---

## Security Notes

1. **Always verify token** - Never trust client-side token
2. **Use Firebase Web Client ID** - For token verification
3. **Case-insensitive email matching** - Handle email case variations
4. **Rate limiting** - Consider adding rate limits to prevent abuse

---

**Ready to implement once Firebase Web Client ID is provided!**

