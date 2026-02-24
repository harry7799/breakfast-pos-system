from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Query, WebSocketException, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import UserRole
from app.security import verify_access_token


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


def resolve_user_from_token(token: str, db: Session) -> User | None:
    payload = verify_access_token(token)
    if not payload:
        return None
    user_id = payload.get("uid")
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        return None
    return user


def resolve_default_user(db: Session) -> User | None:
    role_priority = case(
        (User.role == UserRole.owner.value, 0),
        (User.role == UserRole.manager.value, 1),
        (User.role == UserRole.staff.value, 2),
        (User.role == UserRole.kitchen.value, 3),
        else_=9,
    )
    return db.scalar(
        select(User)
        .where(User.is_active.is_(True))
        .order_by(role_priority, User.id.asc())
        .limit(1)
    )


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if settings.auth_disabled:
        fallback = resolve_default_user(db)
        if not fallback:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No active user configured")
        return fallback

    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    user = resolve_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def get_current_user_from_query(
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    if settings.auth_disabled:
        fallback = resolve_default_user(db)
        if not fallback:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No active user configured")
        return fallback

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    user = resolve_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def get_websocket_user(*, token: str | None, db: Session) -> User:
    if settings.auth_disabled:
        fallback = resolve_default_user(db)
        if not fallback:
            raise WebSocketException(code=status.WS_1011_INTERNAL_ERROR, reason="No active user configured")
        return fallback

    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
    user = resolve_user_from_token(token, db)
    if not user:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
    return user


def require_roles(*roles: UserRole | str) -> Callable[[User], User]:
    allowed_roles = {role.value if isinstance(role, UserRole) else str(role) for role in roles}

    def _guard(current_user: User = Depends(get_current_user)) -> User:
        if settings.auth_disabled:
            return current_user
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return current_user

    return _guard
