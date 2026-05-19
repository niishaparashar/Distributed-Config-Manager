from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import duplicate_service
from app.database import get_db
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceRead

router = APIRouter(prefix="/services", tags=["services"])


@router.post("", response_model=ServiceRead, status_code=201)
async def register_service(payload: ServiceCreate, db: AsyncSession = Depends(get_db)) -> Service:
    service = Service(name=payload.name, description=payload.description)
    db.add(service)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise duplicate_service(payload.name) from exc
    await db.refresh(service)
    return service


@router.get("", response_model=list[ServiceRead])
async def list_services(db: AsyncSession = Depends(get_db)) -> list[Service]:
    result = await db.execute(select(Service).order_by(Service.name))
    return list(result.scalars().all())
