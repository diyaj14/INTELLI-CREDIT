# ============================================================
#  Dockerfile — General Purpose (Railway, Fly.io, VPS)
#  Build: docker build -t intelli-credit .
#  Run:   docker run -p 8001:8001 --env-file .env intelli-credit
# ============================================================

FROM python:3.11-slim

# System dependencies
# - poppler-utils  → required by pdf2image (PDF to image conversion)
# - ghostscript    → required by camelot-py (table extraction)
# - libsm6 libxext6 libxrender1 → required by opencv-python-headless
# - libglib2.0-0   → required by opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    ghostscript \
    libsm6 \
    libxext6 \
    libxrender1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory to app root
WORKDIR /code

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy all project files
COPY backend/    /code/backend/
COPY frontend/   /code/frontend/
COPY modules/    /code/modules/

# Create writable dirs for uploads and reports (needed at runtime)
RUN mkdir -p /tmp/uploads /tmp/reports

# Expose port
EXPOSE 8001

# Start FastAPI with uvicorn
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8001"]
