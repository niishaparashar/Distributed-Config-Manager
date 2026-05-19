from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditRead(BaseModel):
    id: int
    service_id: int
    action: str
    version: int | None
    performed_by: str
    timestamp: datetime
    notes: str | None

    model_config = ConfigDict(from_attributes=True)
