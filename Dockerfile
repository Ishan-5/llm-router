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

# Customer-support difficulty policies: feature_builder module + artifacts.
# support_policy.py resolves this relative to backend/router, so the layout
# must mirror the repo (customer-support sits beside backend/ -> /app).
COPY customer-support/routing/ ./customer-support/routing/
COPY customer-support/models/ ./customer-support/models/

EXPOSE 8000

CMD ["uvicorn", "router.main:app", "--host", "0.0.0.0", "--port", "8000"]
