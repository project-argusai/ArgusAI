# ArgusAI Backend Dockerfile
# Multi-stage build for minimal image size
# Story P10-2.1: Create Backend Dockerfile

# ==============================================================================
# Stage 1: Builder - Install dependencies and build wheels
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ==============================================================================
# Stage 2: Runtime - Minimal production image
# ==============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system dependencies
# - ffmpeg: Video processing for PyAV
# - libopencv: Computer vision (opencv-python-headless)
# - libgl1: OpenGL for image processing
# - libglib2.0-0: GLib library
# - libpq5: PostgreSQL client library
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application code
COPY . .

# Local detector weights (checksum-pinned): MobileNet-SSD vehicles plus
# YuNet/SFace faces. Vehicle and face recognition are disabled without them.
# download_face_model.py fetches the legacy ResNet-10 face detector.
RUN python scripts/download_vehicle_model.py && python scripts/download_face_model.py

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set Python environment variables
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default environment variables (can be overridden at runtime)
ENV DEBUG=false
ENV LOG_LEVEL=INFO

# Health check - verify FastAPI is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Declare volume for persistent data
# Contains: database (app.db), thumbnails/, frames/, certs/, homekit/
VOLUME /app/data

# Expose the API port
EXPOSE 8000

# Run the FastAPI application with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
