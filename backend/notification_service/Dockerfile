FROM python:3.10-slim

WORKDIR /app

COPY notification_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Module logging/tracing dùng chung (backend/shared) + code của service
COPY shared/ ./
COPY notification_service/ ./

EXPOSE 8004

# Tắt access log mặc định: middleware trong observability.py đã log mỗi request kèm X-Request-ID
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
