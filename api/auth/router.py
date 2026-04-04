import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status

from api.auth.email import send_reset_email, send_verification_email
from api.auth.jwt import create_access_token, generate_api_key, hash_password, verify_password
from api.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserRegisterResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from storage.db_client import (
    activate_user,
    consume_reset_token,
    consume_verification_token,
    create_reset_token,
    create_verification_token,
    fetch_reset_token,
    fetch_user_by_email,
    fetch_verification_token,
    insert_user,
    update_user_password,
)

router = APIRouter()


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
async def register(body: UserRegisterRequest, request: Request):
    existing = fetch_user_by_email(body.email)
    if existing:
        if existing["is_active"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        # Unverified account: resend a fresh OTP so the user is not stuck
        user_id = existing["id"]
        otp = "".join(str(secrets.randbelow(10)) for _ in range(6))
        token_hash = hashlib.sha256(otp.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        create_verification_token(user_id, token_hash, expires_at)
        sent = send_verification_email(body.email, otp)
        if not sent:
            return UserRegisterResponse(user_id=user_id, email=body.email, api_key=existing["api_key"], verify_token=otp)
        return UserRegisterResponse(user_id=user_id, email=body.email, api_key=existing["api_key"])

    hashed = hash_password(body.password)
    api_key = generate_api_key()
    user_id = insert_user(email=body.email, hashed_password=hashed, api_key=api_key)

    otp = "".join(str(secrets.randbelow(10)) for _ in range(6))
    token_hash = hashlib.sha256(otp.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    create_verification_token(user_id, token_hash, expires_at)

    sent = send_verification_email(body.email, otp)
    if not sent:
        return UserRegisterResponse(user_id=user_id, email=body.email, api_key=api_key, verify_token=otp)

    return UserRegisterResponse(user_id=user_id, email=body.email, api_key=api_key)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(body: VerifyEmailRequest):
    """Verify a user's email address using a one-time OTP."""
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    record = fetch_verification_token(token_hash)
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification code.")
    activate_user(record["user_id"])
    consume_verification_token(record["id"])
    return VerifyEmailResponse(message="Email verified. You can now log in.")


@router.post("/token", response_model=TokenResponse)
async def login(body: TokenRequest, request: Request):
    """Login with email + password. Returns JWT access token."""
    user = fetch_user_by_email(body.email)
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please check your inbox for the verification OTP.",
        )
    token = create_access_token({"sub": user["email"], "user_id": user["id"]})
    return TokenResponse(access_token=token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(body: ForgotPasswordRequest):
    """
    Request a password reset token.
    Always returns 200 to avoid revealing whether the email exists.
    When SMTP is not configured (dev mode), returns the token directly in the response.
    """
    user = fetch_user_by_email(body.email)
    if user and user["is_active"]:
        otp = "".join(str(secrets.randbelow(10)) for _ in range(6))
        token_hash = hashlib.sha256(otp.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        create_reset_token(user["id"], token_hash, expires_at)

        sent = send_reset_email(body.email, otp)
        if not sent:
            # Dev mode: no SMTP configured — return OTP in response
            return ForgotPasswordResponse(
                message="SMTP not configured. Use the OTP below to reset your password.",
                reset_token=otp,
            )

    return ForgotPasswordResponse(
        message="If that email is registered, a one-time password (OTP) has been sent."
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(body: ResetPasswordRequest):
    """Validate a reset token and update the user's password."""
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    record = fetch_reset_token(token_hash)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token.",
        )
    hashed = hash_password(body.new_password)
    update_user_password(record["user_id"], hashed)
    consume_reset_token(record["id"])
    return ResetPasswordResponse(message="Password updated successfully. Please log in.")
