# ==============================
# web image — FastAPI backend that also serves the React SPA.
# (The SPA is a static build; FastAPI serves it from ./dist via the
#  frontend_router in main.py, so no separate frontend container is needed.)
# ==============================

# ---- Stage 1: build the SPA ----
FROM node:22-alpine AS frontend
# Deploy sub-path the app is served under (e.g. /ultimate-web-stack-dev/).
# Sets Vite base so assets/router/API resolve under the ingress path.
ARG BASE_PATH=/
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* /fe/
RUN npm ci --legacy-peer-deps
COPY frontend/ /fe/
# CI provides frontend/terraform.config.json (real Entra output) before build.
# Override outDir to /fe/dist (vite.config.js points it at ../backend/dist).
RUN npm run build -- --base="$BASE_PATH" --outDir dist --emptyOutDir

# ---- Stage 2: backend + bundled SPA ----
FROM python:3.12-slim

WORKDIR /app

# Install build dependencies for pymongo
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists*

# Install Python dependencies
COPY backend/requirements.txt /app/
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Remove Cosmos/TinyDB-related deps; add MongoDB
RUN pip uninstall -y azure-cosmos tinydb opencensus-ext-azure opencensus-ext-fastapi 2>/dev/null || true \
    && pip install --no-cache-dir --break-system-packages \
    pymongo==4.10.1 \
    opentelemetry-api \
    opentelemetry-sdk \
    opentelemetry-instrumentation-fastapi \
    opentelemetry-exporter-otlp

# Copy backend source
COPY backend/ /app/

# Bundle the built SPA; FastAPI serves it from ./dist (see main.py)
COPY --from=frontend /fe/dist /app/dist

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV MONGODB_URI=mongodb://mongodb:27017
ENV MONGODB_DB=future_gadget_lab

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
