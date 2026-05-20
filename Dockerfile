# Stage 1: build frontend (so deployed app is always current, not from cache)
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ ./
RUN node ./node_modules/vite/bin/vite.js build

# Stage 2: Python app + copy built frontend
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libswe-dev \
    python3-dev \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libxshmfence1 \
    libdrm2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install chromium

COPY app/ ./app/
COPY shared/ ./shared/
COPY templates/ ./templates/
COPY ephe/ ./ephe/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY start.sh ./

# Copy built frontend from stage 1 (this is the only place dist comes from)
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

ENV PYTHONPATH=/app
EXPOSE 8000

# Railway sets PORT; start.sh expands it
CMD ["sh", "start.sh"]
