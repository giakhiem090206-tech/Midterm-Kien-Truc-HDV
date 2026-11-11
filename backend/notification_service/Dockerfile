FROM python:3.10-slim

WORKDIR /app

COPY notification_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./
COPY notification_service/ ./

EXPOSE 8004

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
