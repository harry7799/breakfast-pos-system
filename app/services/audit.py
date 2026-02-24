from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def create_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    payload: dict | None = None,
) -> None:
    """Stage an audit row in the current transaction.

    This helper intentionally does not commit, so callers can control
    transaction boundaries explicitly.
    """
    row = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_username=actor.username if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        payload=payload or {},
    )
    db.add(row)
    db.flush()
