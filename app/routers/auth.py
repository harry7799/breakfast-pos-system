from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserCreate, UserOut, UserRole
from app.security import create_access_token, hash_password, verify_password
from app.services.audit import create_audit_log
from app.services.rate_limit import login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def _resolve_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else "unknown"


def _login_identity(request: Request, username: str) -> str:
    return f"{_resolve_client_ip(request)}::{username.strip().lower()}"


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    identity = _login_identity(request, payload.username)
    if await login_rate_limiter.should_block(identity):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active:
        await login_rate_limiter.add_failure(identity)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not verify_password(payload.password, user.password_hash):
        await login_rate_limiter.add_failure(identity)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    await login_rate_limiter.reset(identity)
    token, expires_at = create_access_token(user_id=user.id, username=user.username, role=user.role)
    create_audit_log(
        db,
        actor=user,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        payload={},
    )
    db.commit()
    return LoginResponse(
        access_token=token,
        expires_at=expires_at.isoformat(),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.get(
    "/users",
    response_model=list[UserOut],
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.owner)),
) -> list[User]:
    return db.scalars(select(User).order_by(User.id)).all()


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.owner)),
) -> User:
    exists = db.scalar(select(User).where(User.username == payload.username))
    if exists:
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    create_audit_log(
        db,
        actor=current_user,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        payload={"username": user.username, "role": user.role, "is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    return user
