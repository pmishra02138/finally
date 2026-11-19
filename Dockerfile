# Stage 1: Build Next.js static export
FROM node:20-slim AS frontend-builder

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 3.12 + uv FastAPI runtime
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies from lockfile (production only)
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/app ./app
RUN uv sync --frozen --no-dev

# Copy Next.js static export into /app/static
COPY --from=frontend-builder /frontend/out /app/static

# Volume mount point for SQLite database (/app/db/finally.db)
RUN mkdir -p /app/db

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/db/finally.db

EXPOSE 8000

# Single worker required (in-memory PriceCache, simulator/poller, and snapshot task)
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
