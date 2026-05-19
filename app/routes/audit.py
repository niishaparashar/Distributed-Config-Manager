from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import service_not_found
from app.database import get_db
from app.models.audit import AuditLog
from app.models.service import Service
from app.schemas.audit import AuditRead

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{service_name}", response_model=list[AuditRead])
async def get_audit_trail(service_name: str, db: AsyncSession = Depends(get_db)) -> list[AuditLog]:
    service = await _get_service(db, service_name)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.service_id == service.id)
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    )
    return list(result.scalars().all())


async def _get_service(db: AsyncSession, service_name: str) -> Service:
    result = await db.execute(select(Service).where(Service.name == service_name))
    service = result.scalar_one_or_none()
    if service is None:
        raise service_not_found(service_name)
    return service
