import os
import json
import logging
from typing import Any, Optional
import redis

logger = logging.getLogger("redis_cache")

# Cấu hình kết nối:
# - Trong Docker container: host là 'redis' (hoặc đọc từ biến REDIS_URL)
# - Chạy trực tiếp trên máy host: host là 'localhost'
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

# 1. Kiểm tra kết nối khi khởi động:
# Nếu Redis chưa bật hoặc lỗi, KHÔNG để app bị crash. 
# Thay vào đó chỉ in cảnh báo để app tiếp tục chạy và tự động dùng PostgreSQL.
try:
    r.ping()
    print("Connected to Redis")
except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
    print(f"Error connecting to Redis: {e}. Falling back to postgreSQL.")


# 2. Các hàm thao tác Cache có sẵn cơ chế Fallback sang PostgreSQL:

def get_cache(key: str) -> Optional[Any]:
    """
    Đọc dữ liệu từ Redis.
    Nếu Redis lỗi hoặc không tìm thấy key (Cache Miss), hàm trả về None.
    -> Lúc này service gọi hàm sẽ tự động tiếp tục truy vấn từ PostgreSQL.
    """
    try:
        data = r.get(key)
        if data is not None:
            return json.loads(data)
    except Exception as e:
        logger.warning("Error reading Redis (key=%s): %s. Automatically falling back to PostgreSQL.", key, e)
    return None


def set_cache(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """
    Lưu dữ liệu vào Redis với thời gian sống TTL (mặc định 300s = 5 phút).
    Nếu Redis gặp sự cố, ghi nhận cảnh báo và bỏ qua (không làm lỗi luồng chính).
    """
    try:
        serialized = json.dumps(value) if not isinstance(value, str) else value
        r.setex(key, ttl_seconds, serialized)
        return True
    except Exception as e:
        logger.warning("Lỗi ghi Redis (key=%s): %s", key, e)
        return False


def delete_cache(key: str) -> bool:
    """
    Xóa cache khi dữ liệu bị thay đổi (Cache Invalidation).
    Nếu Redis lỗi, ghi nhận cảnh báo và bỏ qua.
    """
    try:
        r.delete(key)
        return True
    except Exception as e:
        logger.warning("Lỗi xóa cache Redis (key=%s): %s", key, e)
        return False

