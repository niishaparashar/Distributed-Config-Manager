from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import active_version_delete_error, service_not_found, version_not_found
from app.database import get_db
from app.models.audit import AuditLog
from app.models.config import Config
from app.models.service import Service
from app.redis_client import redis_client
from app.schemas.config import ConfigCreate, ConfigHistoryItem, ConfigRead

router = APIRouter(prefix="/configs", tags=["configs"])


def _cache_key(service_name: str) -> str:
    return f"config:{service_name}:latest"


async def _get_service(db: AsyncSession, service_name: str) -> Service:
    result = await db.execute(select(Service).where(Service.name == service_name))
    service = result.scalar_one_or_none()
    if service is None:
        raise service_not_found(service_name)
    return service


async def _write_audit(
    db: AsyncSession,
    service_id: int,
    action: str,
    version: int | None,
    performed_by: str = "admin",
    notes: str | None = None,
) -> None:
    db.add(
        AuditLog(
            service_id=service_id,
            action=action,
            version=version,
            performed_by=performed_by,
            notes=notes,
        )
    )


@router.post("/{service_name}", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
async def push_config(
    service_name: str, payload: ConfigCreate, db: AsyncSession = Depends(get_db)
) -> Config:
    service = await _get_service(db, service_name)

    latest_result = await db.execute(
        select(Config.version)
        .where(Config.service_id == service.id)
        .order_by(desc(Config.version))
        .limit(1)
    )
    latest_version = latest_result.scalar_one_or_none() or 0
    new_version = latest_version + 1

    await db.execute(
        update(Config)
        .where(Config.service_id == service.id)
        .values(is_active=False)
    )
    config = Config(
        service_id=service.id,
        version=new_version,
        config_data=payload.config_data,
        is_active=True,
        created_by=payload.created_by,
    )
    db.add(config)
    await _write_audit(
        db,
        service.id,
        "PUSH",
        new_version,
        payload.created_by,
        f"Pushed config version {new_version}",
    )
    await db.commit()
    await db.refresh(config)
    await redis_client.set_json(_cache_key(service_name), config.config_data)
    return config


@router.get("/{service_name}/latest")
async def get_latest_config(service_name: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    service = await _get_service(db, service_name)
    cached = await redis_client.get_json(_cache_key(service_name))
    if cached is not None:
        await _write_audit(db, service.id, "FETCH", None, notes="Fetched latest config from Redis")
        await db.commit()
        return cached

    result = await db.execute(
        select(Config).where(Config.service_id == service.id, Config.is_active.is_(True))
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise version_not_found(service_name, 0)

    await redis_client.set_json(_cache_key(service_name), config.config_data)
    await _write_audit(db, service.id, "FETCH", config.version, notes="Fetched latest config from PostgreSQL")
    await db.commit()
    return config.config_data


@router.get("/{service_name}/history", response_model=list[ConfigHistoryItem])
async def get_config_history(service_name: str, db: AsyncSession = Depends(get_db)) -> list[Config]:
    service = await _get_service(db, service_name)
    result = await db.execute(
        select(Config)
        .where(Config.service_id == service.id)
        .order_by(Config.version.desc())
    )
    return list(result.scalars().all())


@router.get("/{service_name}/{version}", response_model=ConfigRead)
async def get_config_version(
    service_name: str, version: int, db: AsyncSession = Depends(get_db)
) -> Config:
    service = await _get_service(db, service_name)
    result = await db.execute(
        select(Config).where(Config.service_id == service.id, Config.version == version)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise version_not_found(service_name, version)
    return config


@router.post("/{service_name}/rollback", response_model=ConfigRead)
async def rollback_config(
    service_name: str,
    version: int = Query(gt=0),
    performed_by: str = "admin",
    db: AsyncSession = Depends(get_db),
) -> Config:
    service = await _get_service(db, service_name)
    result = await db.execute(
        select(Config).where(Config.service_id == service.id, Config.version == version)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise version_not_found(service_name, version)

    await db.execute(
        update(Config)
        .where(Config.service_id == service.id)
        .values(is_active=False)
    )
    config.is_active = True
    await _write_audit(
        db,
        service.id,
        "ROLLBACK",
        version,
        performed_by,
        f"Rolled back active config to version {version}",
    )
    await db.commit()
    await db.refresh(config)
    await redis_client.delete(_cache_key(service_name))
    await redis_client.set_json(_cache_key(service_name), config.config_data)
    return config


@router.delete("/{service_name}/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config_version(
    service_name: str,
    version: int,
    performed_by: str = "admin",
    db: AsyncSession = Depends(get_db),
) -> None:
    service = await _get_service(db, service_name)
    result = await db.execute(
        select(Config).where(Config.service_id == service.id, Config.version == version)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise version_not_found(service_name, version)
    if config.is_active:
        raise active_version_delete_error()

    await db.execute(delete(Config).where(Config.id == config.id))
    await _write_audit(
        db,
        service.id,
        "DELETE",
        version,
        performed_by,
        f"Deleted config version {version}",
    )
    await db.commit()
