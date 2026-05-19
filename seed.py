import asyncio
from typing import Any

from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.config import Config
from app.models.service import Service
from app.redis_client import redis_client


SEED_DATA: dict[str, list[dict[str, Any]]] = {
    "auth-service": [
        {"jwt_ttl_seconds": 900, "issuer": "auth.internal", "mfa_required": False, "log_level": "INFO"},
        {"jwt_ttl_seconds": 1200, "issuer": "auth.internal", "mfa_required": True, "log_level": "INFO"},
        {"jwt_ttl_seconds": 900, "issuer": "auth.internal", "mfa_required": True, "log_level": "WARN"},
    ],
    "payment-service": [
        {"provider": "stripe", "retry_count": 2, "currency": "USD", "capture_mode": "manual"},
        {"provider": "stripe", "retry_count": 3, "currency": "USD", "capture_mode": "automatic"},
        {"provider": "adyen", "retry_count": 3, "currency": "USD", "capture_mode": "automatic"},
    ],
    "notification-service": [
        {"email_provider": "ses", "sms_provider": "twilio", "batch_size": 100, "quiet_hours": False},
        {"email_provider": "ses", "sms_provider": "twilio", "batch_size": 250, "quiet_hours": True},
        {"email_provider": "sendgrid", "sms_provider": "twilio", "batch_size": 250, "quiet_hours": True},
    ],
}


async def main() -> None:
    await redis_client.connect()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AuditLog))
        await db.execute(delete(Config))
        await db.execute(delete(Service))

        for service_name, configs in SEED_DATA.items():
            service = Service(name=service_name, description=f"Seeded {service_name} configuration owner")
            db.add(service)
            await db.flush()

            for index, config_data in enumerate(configs, start=1):
                db.add(
                    Config(
                        service_id=service.id,
                        version=index,
                        config_data=config_data,
                        is_active=index == len(configs),
                        created_by="seed",
                    )
                )
                db.add(
                    AuditLog(
                        service_id=service.id,
                        action="PUSH",
                        version=index,
                        performed_by="seed",
                        notes=f"Seeded config version {index}",
                    )
                )

            await redis_client.set_json(f"config:{service_name}:latest", configs[-1])

        await db.commit()
    await redis_client.close()
    print("Seeded services, config versions, audit logs, and Redis latest keys.")


if __name__ == "__main__":
    asyncio.run(main())
