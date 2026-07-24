from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.modules.auth.schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse


router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def _public_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "full_name": row["full_name"],
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    user = db.get_user(str(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    if db.get_user_by_email(request.email):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = db.create_user(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(request.password),
    )
    token = create_access_token(user["id"], {"email": user["email"]})
    return AuthResponse(access_token=token, user=user)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    user = db.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    public = _public_user(user)
    token = create_access_token(public["id"], {"email": public["email"]})
    return AuthResponse(access_token=token, user=public)


@router.get("/me", response_model=UserResponse)
async def me(user: dict = Depends(get_current_user)):
    return UserResponse(user=_public_user(user))
