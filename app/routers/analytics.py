from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_roles
from app.database import get_db
from app.schemas import AnalyticsOverviewOut, UserRole
from app.services.analytics import overview

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewOut)
def get_overview(
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    _: object = Depends(require_roles(UserRole.manager, UserRole.owner)),
) -> dict:
    try:
        return overview(db, start_date=start_date, end_date=end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
