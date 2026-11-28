# Multi-stage production Dockerfile for smartrx-safety-agents
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/

RUN python -m pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels .


FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    ENVIRONMENT=production \
    REQUIRE_AUTH=true \
    SMART_PORT=8080 \
    SMARTRX_DB_PATH=/app/data/smartrx_ledger.db \
    AUDIT_LOG_DIR=/app/audit_logs

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

COPY src/ src/
COPY config/ config/
COPY prompts/ prompts/

RUN groupadd --gid 10001 smartrx \
    && useradd --uid 10001 --gid smartrx --shell /usr/sbin/nologin --create-home smartrx \
    && mkdir -p /app/data /app/audit_logs \
    && chown -R smartrx:smartrx /app

USER smartrx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"]

CMD ["python", "-m", "smartrx_safety_agents.cli", "serve", "--host", "0.0.0.0", "--port", "8080"]
