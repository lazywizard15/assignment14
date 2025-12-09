# app/auth/redis.py
import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

async def get_redis():
    """Return a Redis client singleton"""
    if not hasattr(get_redis, "redis"):
        # Create a Redis client
        get_redis.redis = redis.Redis.from_url(
            settings.REDIS_URL or "redis://localhost", decode_responses=True
        )
    return get_redis.redis

async def add_to_blacklist(jti: str, exp: int):
    """Add a token's JTI to the blacklist"""
    r = await get_redis()
    await r.set(f"blacklist:{jti}", "1", ex=exp)

async def is_blacklisted(jti: str) -> bool:
    """Check if a token's JTI is blacklisted"""
    r = await get_redis()
    return await r.exists(f"blacklist:{jti}") > 0
