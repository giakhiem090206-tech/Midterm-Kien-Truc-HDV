FROM python:3.10-slim

WORKDIR /app

COPY payment_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Module logging/tracing dùng chung (backend/shared) + code của service
COPY shared/ ./
COPY payment_service/ ./

EXPOSE 8003

# Tắt access log mặc định: middleware trong observability.py đã log mỗi request kèm X-Request-ID
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
