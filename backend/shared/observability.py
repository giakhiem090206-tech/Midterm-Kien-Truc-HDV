"""
Logging & tracing dùng chung cho mọi service.

Mỗi request mang một X-Request-ID: API Gateway (Nginx) sinh ra khi request vào hệ thống,
các service ghi ID này vào mọi dòng log và gửi tiếp khi gọi service khác. Lọc log theo một
ID sẽ thấy toàn bộ đường đi của request đó qua Gateway -> Payment -> Auth/Tuition/Notification:

    docker compose logs | grep <request-id>
"""
import logging
import time
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def get_logger(service_name: str) -> logging.Logger:
    logger = logging.getLogger(service_name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(name)s] [rid=%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        handler.addFilter(_RequestIdFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def setup_observability(app, service_name: str) -> logging.Logger:
    """Gắn middleware: nhận/sinh X-Request-ID, ghi log mỗi request (method, path, status, thời gian)"""
    logger = get_logger(service_name)

    @app.middleware("http")
    async def trace_request(request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = _request_id.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("%s %s -> lỗi không xử lý được", request.method, request.url.path)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
        response.headers[REQUEST_ID_HEADER] = request_id
        _request_id.reset(token)
        return response

    return logger


def current_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    """Dùng cho tác vụ nền (không xuất phát từ request), ví dụ worker phục hồi giao dịch"""
    _request_id.set(request_id)


def tracing_headers() -> dict:
    """Header cần gửi kèm khi gọi service khác để giữ nguyên request ID"""
    request_id = _request_id.get()
    return {REQUEST_ID_HEADER: request_id} if request_id != "-" else {}
