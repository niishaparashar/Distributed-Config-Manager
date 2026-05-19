from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.database import check_database, close_database
from app.redis_client import redis_client
from app.routes.audit import router as audit_router
from app.routes.configs import router as configs_router
from app.routes.services import router as services_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await check_database()
    await redis_client.connect()
    yield
    await redis_client.close()
    await close_database()


app = FastAPI(
    title="Distributed Config Manager",
    description="Centralized versioned configuration management API for distributed services.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(services_router)
app.include_router(configs_router)
app.include_router(audit_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
