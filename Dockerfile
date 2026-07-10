FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only copy what's actually needed at runtime
COPY backend/router/ ./router/
COPY backend/src/ ./src/
COPY backend/models/ ./models/

EXPOSE 8000

CMD ["uvicorn", "router.main:app", "--host", "0.0.0.0", "--port", "8000"]
