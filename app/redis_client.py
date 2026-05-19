import json
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import get_settings


class RedisClient:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        settings = get_settings()
        client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await client.ping()
        except RedisError:
            await client.aclose()
            self._client = None
            return
        self._client = client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None

    async def get_json(self, key: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        try:
            value = await self._client.get(key)
        except RedisError:
            return None
        if value is None:
            return None
        return json.loads(value)

    async def set_json(self, key: str, value: dict[str, Any]) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.set(key, json.dumps(value))
        except RedisError:
            return False
        return True

    async def delete(self, key: str) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.delete(key)
        except RedisError:
            return False
        return True


redis_client = RedisClient()
