FROM python:3.10-slim

WORKDIR /app

COPY payment_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./
COPY payment_service/ ./

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
