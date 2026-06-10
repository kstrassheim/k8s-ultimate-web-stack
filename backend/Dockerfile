# ==============================
# Backend Dockerfile
# ==============================
FROM python:3.12-slim

WORKDIR /app

# Install build dependencies for pymongo
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists*

# Install Python dependencies via uv (locked transitive tree with hashes)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY backend/requirements.txt /app/
RUN uv pip sync --system --break-system-packages requirements.txt

# Copy backend source
COPY backend/ /app/

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