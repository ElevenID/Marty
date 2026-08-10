# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential libpcsclite-dev swig \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY proto ./proto
COPY packages/marty-common ./packages/marty-common
COPY native-wheels /native-wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel --wheel-dir /wheels --find-links=/native-wheels ./packages/marty-common \
    && python -m pip wheel --wheel-dir /wheels --find-links=/native-wheels --find-links=/wheels .

FROM python:3.12-slim AS production
ARG VERSION
ARG VCS_REF
LABEL org.opencontainers.image.source="https://github.com/ElevenID/Marty" \
      org.opencontainers.image.title="Marty MMF plugin" \
      org.opencontainers.image.description="Open-source identity and trust services for Marty" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
RUN groupadd --system --gid 10001 marty \
    && useradd --system --uid 10001 --gid marty --home-dir /app marty \
    && apt-get update \
    && apt-get install --yes --no-install-recommends libpcsclite1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-cache-dir --no-index --find-links=/wheels marty-trust-pki-plugin \
    && python -c "from marty_plugin.native_backends import require_native_backends; require_native_backends()" \
    && rm -rf /wheels
WORKDIR /app
USER 10001:10001
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MARTY_ENV=production
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1
CMD ["uvicorn", "marty_plugin.runtime:app", "--host", "0.0.0.0", "--port", "8080"]
