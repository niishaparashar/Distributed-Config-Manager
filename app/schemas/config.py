from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigCreate(BaseModel):
    config_data: dict[str, Any] = Field(
        examples=[
            {
                "db_host": "postgres://prod-db:5432",
                "max_connections": 100,
                "feature_flags": {"enable_dark_mode": True, "beta_users_only": False},
                "timeout_ms": 3000,
                "log_level": "INFO",
            }
        ]
    )
    created_by: str = "admin"


class ConfigRead(BaseModel):
    id: int
    service_id: int
    version: int
    config_data: dict[str, Any]
    is_active: bool
    created_at: datetime
    created_by: str

    model_config = ConfigDict(from_attributes=True)


class ConfigHistoryItem(BaseModel):
    id: int
    version: int
    is_active: bool
    created_at: datetime
    created_by: str

    model_config = ConfigDict(from_attributes=True)
