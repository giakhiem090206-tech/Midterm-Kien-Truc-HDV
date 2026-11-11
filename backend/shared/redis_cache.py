import os
import json
import logging
from typing import Any, Optional
import redis

logger = logging.getLogger("redis_cache")

REDIS_URL = os.getenv("REDIS_URL")
if REDIS_URL:
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
else:
    REDIS_HOST = os.getenv("REDIS_HOST", "redis" if os.path.exists("/.dockerenv") else "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )

try:
    r.ping()
    print("Connected to Redis")
except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
    print(f"Error connecting to Redis: {e}. Falling back to postgreSQL.")



def get_cache(key: str) -> Optional[Any]:
    try:
        data = r.get(key)
        if data is not None:
            return json.loads(data)
    except Exception as e:
        logger.warning("Error reading Redis (key=%s): %s. Automatically falling back to PostgreSQL.", key, e)
    return None


def set_cache(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    try:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        r.setex(key, ttl_seconds, serialized)
        return True
    except Exception as e:
        logger.warning("Lỗi ghi Redis (key=%s): %s", key, e)
        return False


def delete_cache(key: str) -> bool:
    try:
        r.delete(key)
        return True
    except Exception as e:
        logger.warning("Lỗi xóa cache Redis (key=%s): %s", key, e)
        return False

