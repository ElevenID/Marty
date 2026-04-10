# Regula Clone API Docker Image
# Optimized with BuildKit cache mounts

# =============================================================================
# Builder Stage
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN uv pip install --system -e .

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY app/ app/
COPY ../marty_common/ marty_common/

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/api/ping', timeout=10)"

# Note: License enforcement for document-processing uses the FastAPI lifespan
# approach (create_licensed_lifespan) in app/main.py rather than the shell
# entrypoint, since this service does not copy the full src/ tree.
ENV MARTY_PRODUCT_ID=document-processing

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
