from fastapi import APIRouter, HTTPException, Request, status

from api.auth.jwt import create_access_token, generate_api_key, hash_password, verify_password
from api.schemas import (
    TokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserRegisterResponse,
)
from storage.db_client import fetch_user_by_email, insert_user

router = APIRouter()


@router.post("/register", response_model=UserRegisterResponse, status_code=201)
async def register(body: UserRegisterRequest, request: Request):
    """Register a new user. Returns user_id and api_key."""
    # Check if email already exists
    existing = fetch_user_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    hashed = hash_password(body.password)
    api_key = generate_api_key()
    user_id = insert_user(
        email=body.email,
        hashed_password=hashed,
        api_key=api_key,
    )
    return UserRegisterResponse(user_id=user_id, email=body.email, api_key=api_key)


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
            detail="Account is inactive",
        )
    token = create_access_token({"sub": user["email"], "user_id": user["id"]})
    return TokenResponse(access_token=token)
