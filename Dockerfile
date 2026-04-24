# Build stage
# Build the static frontend on the runner architecture so multi-arch image
# creation does not need to execute npm under QEMU emulation.
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS builder
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --no-audit

COPY index.html ./
COPY vite.config.js ./
COPY postcss.config.js ./
COPY tailwind.config.js ./
COPY src ./src
COPY Dataset ./Dataset
RUN npm run build

# Runtime stage
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

COPY agent4 ./agent4
COPY agent5 ./agent5
COPY backend ./backend
COPY brain ./brain
COPY Dataset ./Dataset
COPY synthetic_data ./synthetic_data
COPY docker/run_combined.py ./docker/run_combined.py
COPY --from=builder /app/dist /usr/share/nginx/html
COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["python", "docker/run_combined.py"]
