import logging
from uuid import uuid4

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def get_cache(request: Request) -> Redis:
    return request.app.state.redis


async def invalidate_users(cache: Redis):
    try:
        await cache.set("users:version", uuid4().hex)
    except RedisError:
        logger.warning("Не удалось обновить версию кэша", exc_info=True)
