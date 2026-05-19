import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.routes import configs as configs_route


class FakeRedisClient:
    def __init__(self) -> None:
        self.store: dict[str, dict] = {}

    async def get_json(self, key: str) -> dict | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: dict) -> bool:
        self.store[key] = value
        return True

    async def delete(self, key: str) -> bool:
        self.store.pop(key, None)
        return True


@pytest_asyncio.fixture
async def client(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(configs_route, "redis_client", fake_redis)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        test_client.fake_redis = fake_redis
        yield test_client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_service_successfully(client: AsyncClient) -> None:
    response = await client.post("/services", json={"name": "inventory-service", "description": "Inventory API"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "inventory-service"
    assert body["description"] == "Inventory API"


@pytest.mark.asyncio
async def test_push_config_increments_versions(client: AsyncClient) -> None:
    await client.post("/services", json={"name": "billing-service"})

    first = await client.post("/configs/billing-service", json={"config_data": {"timeout_ms": 1000}})
    second = await client.post("/configs/billing-service", json={"config_data": {"timeout_ms": 2000}})

    assert first.status_code == 201
    assert first.json()["version"] == 1
    assert second.status_code == 201
    assert second.json()["version"] == 2
    assert second.json()["is_active"] is True


@pytest.mark.asyncio
async def test_fetch_latest_populates_redis_cache(client: AsyncClient) -> None:
    await client.post("/services", json={"name": "search-service"})
    await client.post("/configs/search-service", json={"config_data": {"replicas": 3}})

    client.fake_redis.store.clear()
    response = await client.get("/configs/search-service/latest")

    assert response.status_code == 200
    assert response.json() == {"replicas": 3}
    assert client.fake_redis.store["config:search-service:latest"] == {"replicas": 3}


@pytest.mark.asyncio
async def test_rollback_flips_active_version(client: AsyncClient) -> None:
    await client.post("/services", json={"name": "edge-service"})
    await client.post("/configs/edge-service", json={"config_data": {"rate_limit": 100}})
    await client.post("/configs/edge-service", json={"config_data": {"rate_limit": 200}})

    rollback = await client.post("/configs/edge-service/rollback?version=1")
    history = await client.get("/configs/edge-service/history")

    assert rollback.status_code == 200
    assert rollback.json()["version"] == 1
    assert rollback.json()["is_active"] is True
    active_versions = [item["version"] for item in history.json() if item["is_active"]]
    assert active_versions == [1]
    assert client.fake_redis.store["config:edge-service:latest"] == {"rate_limit": 100}


@pytest.mark.asyncio
async def test_audit_log_contains_push_and_rollback_entries(client: AsyncClient) -> None:
    await client.post("/services", json={"name": "routing-service"})
    await client.post("/configs/routing-service", json={"config_data": {"region": "us-east-1"}})
    await client.post("/configs/routing-service", json={"config_data": {"region": "us-west-2"}})
    await client.post("/configs/routing-service/rollback?version=1")

    response = await client.get("/audit/routing-service")

    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert actions.count("PUSH") == 2
    assert "ROLLBACK" in actions
    rollback_entry = next(entry for entry in response.json() if entry["action"] == "ROLLBACK")
    assert rollback_entry["version"] == 1
