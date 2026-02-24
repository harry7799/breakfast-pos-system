from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut, UserRole

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/logs",
    response_model=list[AuditLogOut],
    dependencies=[Depends(require_roles(UserRole.manager, UserRole.owner))],
)
def list_audit_logs(limit: int = 200, db: Session = Depends(get_db)) -> list[AuditLog]:
    capped = max(1, min(limit, 1000))
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(capped),
    ).all()
    return rows

