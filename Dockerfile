# syntax=docker/dockerfile:1
# Stage 1: build the SPA
FROM node:24 AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.14.9-slim-trixie
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PATH="/app/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    STRYDR_DB_PATH=/data/strydr.db
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/strydr ./strydr
# thresholds.toml and routes.toml, read from /app/backend/config at runtime
COPY backend/config ./config
RUN uv sync --frozen --no-dev
# Served by the app port via STRYDR_WEB_DIST (default /app/web/dist).
COPY --from=web /web/dist /app/web/dist

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin strydr \
    && mkdir -p /data/backups && chown -R strydr:strydr /data
USER strydr
VOLUME /data
EXPOSE 8080 8081

# No health endpoint yet: TCP check on the app port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health', timeout=3)"]

ENTRYPOINT ["strydr"]
CMD ["serve"]
