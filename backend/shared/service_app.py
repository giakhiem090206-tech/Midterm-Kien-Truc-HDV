"""Khởi tạo FastAPI dùng chung cho mọi service: Swagger qua Gateway, lỗi validate trả 400, logging/tracing"""
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from observability import setup_observability


def create_app(title: str, service_name: str, docs_prefix: Optional[str] = None, lifespan=None):
    """
    docs_prefix: đường dẫn công khai của service (vd "/api/v1/auth") để Swagger xem được qua Gateway,
    ví dụ http://localhost/api/v1/auth/docs. Không truyền -> service nội bộ, Swagger ở /docs
    (chỉ xem được khi mở port bằng docker-compose.dev.yml).
    """
    docs = {"docs_url": f"{docs_prefix}/docs", "openapi_url": f"{docs_prefix}/openapi.json"} if docs_prefix else {}
    app = FastAPI(title=title, version="1.0.0", redoc_url=None, lifespan=lifespan, **docs)

    @app.exception_handler(RequestValidationError)
    def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Trả 400 với thông báo tiếng Việt thay cho 422 mặc định của FastAPI"""
        fields = ", ".join(str(err["loc"][-1]) for err in exc.errors())
        return JSONResponse(status_code=400, content={"detail": f"Dữ liệu không hợp lệ: {fields}"})

    logger = setup_observability(app, service_name)
    return app, logger
