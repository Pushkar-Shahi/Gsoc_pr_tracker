# ==============================================================================
# Multi-Stage Production Dockerfile for Issue-to-PR Platform
# Builds React SPA frontend & runs unified FastAPI service with healthchecks
# ==============================================================================

# --- Stage 1: Build React Frontend ---
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps

COPY frontend/ ./
RUN npm run build

# --- Stage 2: Production Python Runtime ---
FROM python:3.12-slim-bookworm AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend:/app \
    PORT=8000

WORKDIR /app

# Install minimal OS runtime dependencies (git for worktrees, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy Backend Application Code & Standalone Runner Daemon
COPY backend/app /app/backend/app
COPY runner /app/runner

# Copy Built Frontend from Stage 1 into the location expected by FastAPI SPA mount
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Create dedicated non-root application user
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -d /home/appuser -m -s /bin/bash appuser && \
    mkdir -p /home/appuser/.issue_to_pr && \
    chown -R appuser:appuser /app /home/appuser

# Create startup entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Issue-to-PR Platform on port ${PORT:-8000}..."\n\
cd /app/backend\n\
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --proxy-headers --forwarded-allow-ips "*"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]

