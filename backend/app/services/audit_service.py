import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def log_audit(
    db: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    performed_by: str | None = None,
):
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        performed_by=performed_by,
        performed_at=datetime.now(timezone.utc),
    )
    db.add(entry)


async def get_audit_trail(db: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.performed_at.desc())
    )
    return list(result.scalars().all())
