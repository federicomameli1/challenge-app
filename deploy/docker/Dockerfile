# syntax=docker/dockerfile:1.7
#
# Build context expected: repository root.
# Build:  docker build -f deploy/docker/Dockerfile -t challenge-app .

# ---------- Frontend build stage ----------
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit

COPY frontend/index.html ./
COPY frontend/vite.config.js ./
COPY frontend/postcss.config.js ./
COPY frontend/tailwind.config.js ./
COPY frontend/src ./src

RUN npm run build

# ---------- Runtime stage ----------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY agents ./agents
COPY backend ./backend
COPY datasets ./datasets
COPY deploy/docker/run_combined.py ./deploy/docker/run_combined.py
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html
COPY deploy/docker/nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["python", "deploy/docker/run_combined.py"]
