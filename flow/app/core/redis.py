from redis.asyncio import ConnectionPool, Redis

from core.config import settings


class RedisService:
    """Сервис для асинхронного управления кэшем в Redis."""

    def __init__(self) -> None:
        self._pool = ConnectionPool.from_url(
            settings.redis_settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        self.client: Redis = Redis(connection_pool=self._pool)

    async def get(self, key: str) -> str | None:
        """Получить сырую строку из кэша по ключу."""
        return await self.client.get(key)

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        """Записать сериализованную строку в кэш с TTL в секундах."""
        await self.client.set(key, value, ex=ttl)

    async def invalidate(self, pattern: str) -> None:
        """Пакетно удалить ключи кэша по заданной маске."""
        keys = await self.client.keys(pattern)
        if keys:
            await self.client.delete(*keys)

    async def close(self) -> None:
        """Явно закрыть пул соединений при остановке сервера."""
        await self.client.aclose()


redis_service = RedisService()
