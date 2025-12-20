# syntax=docker/dockerfile:1
# Multi-stage Dockerfile for Marty MMF Plugin
# Optimized for both development and production deployment in Kubernetes

# Build stage
FROM python:3.11-slim as builder

# Set build arguments
ARG BUILD_ENV=production
ARG PLUGIN_VERSION=latest

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./
COPY requirements_cedar.txt ./

# Install dependencies using uv with BuildKit cache
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv pip install -r pyproject.toml

# Copy source code
COPY src/ ./src/
COPY proto/ ./proto/
COPY config/ ./config/

# Install the plugin package
RUN uv pip install -e .

# Production stage
FROM python:3.11-slim as production

# Set runtime arguments
ARG PLUGIN_VERSION=latest
ARG BUILD_DATE
ARG VCS_REF

# Add metadata labels
LABEL org.opencontainers.image.title="Marty MMF Plugin" \
      org.opencontainers.image.description="ICAO-compliant PKI and trust services plugin for MMF" \
      org.opencontainers.image.version="${PLUGIN_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.vendor="Educational Project" \
      org.opencontainers.image.licenses="Educational Use Only" \
      mmf.plugin.name="marty" \
      mmf.plugin.version="${PLUGIN_VERSION}" \
      mmf.plugin.type="trust-pki"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r marty && useradd -r -g marty -s /bin/false marty

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application files
COPY --from=builder /app/src /app/src
COPY --from=builder /app/config /app/config
COPY --from=builder /app/proto /app/proto

# Create directories with proper permissions
RUN mkdir -p /app/data /app/logs /app/tmp \
    && chown -R marty:marty /app

# Set working directory
WORKDIR /app

# Switch to non-root user
USER marty

# Environment variables for plugin
ENV PYTHONPATH="/app/src:$PYTHONPATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MMF_PLUGIN_NAME="marty" \
    MMF_PLUGIN_TYPE="trust-pki" \
    MARTY_ENV="production"

# Health check for plugin
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from src.mmf_plugin import MartyPlugin; p=MartyPlugin(); print('Plugin healthy')" || exit 1

# Expose ports for plugin services
# Note: These are default ports, actual ports determined by MMF framework
EXPOSE 8080 9090 8081

# Default command runs the plugin in MMF mode
CMD ["python", "-m", "src.mmf_plugin.main"]

# Development stage (for local Kind development)
FROM production as development

# Switch back to root for development tools
USER root

# Install development dependencies
RUN pip install pytest pytest-asyncio pytest-cov mypy ruff bandit safety

# Install debugging tools
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    strace \
    tcpdump \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Copy test files for development
COPY tests/ ./tests/

# Install development version of the plugin
RUN pip install -e .

# Create development entrypoint
COPY docker/dev-entrypoint.sh /usr/local/bin/dev-entrypoint.sh
RUN chmod +x /usr/local/bin/dev-entrypoint.sh

# Switch back to marty user
USER marty

# Override for development
ENV MARTY_ENV="development"
ENTRYPOINT ["/usr/local/bin/dev-entrypoint.sh"]
CMD ["python", "-m", "src.mmf_plugin.main"]