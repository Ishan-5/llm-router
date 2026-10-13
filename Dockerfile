FROM python:3.11-slim

# Unbuffered logs so platform log drains see lines as they happen; no .pyc
# clutter; no pip cache in the layer.
# FORWARDED_ALLOW_IPS is read by uvicorn: behind a platform proxy (Render,
# Fly), trust its X-Forwarded-* headers so client IPs and scheme are right.
# HOME is set explicitly so the app user can write the Hugging Face cache
# (sentence-transformers) instead of falling back to an unwritable /root.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FORWARDED_ALLOW_IPS=* \
    HOME=/home/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The toolchain is only needed to build wheels, and every dependency here
# installs from a manylinux wheel -- so a served image has no business carrying
# gcc/make. libgomp1 is re-installed explicitly: lightgbm and scikit-learn need
# it at runtime, and --auto-remove would otherwise take it along with gcc.
RUN apt-get update \
    && apt-get purge -y --auto-remove build-essential \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Only copy what's actually needed at runtime
COPY backend/router/ ./router/
COPY backend/src/ ./src/
COPY backend/models/ ./models/

# Customer-support difficulty policies: feature_builder module + artifacts.
# support_policy.py resolves this relative to backend/router, so the layout
# must mirror the repo (customer-support sits beside backend/ -> /app).
COPY customer-support/routing/ ./customer-support/routing/
COPY customer-support/models/ ./customer-support/models/

# Run unprivileged. /app is owned by the app user so the SQLite fallback
# (used only when DATABASE_URL is unset) stays writable.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# Liveness probe from the observability work. The process is up as soon as it
# answers, so the slow first-boot model load does not flap the healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"

CMD ["uvicorn", "router.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
