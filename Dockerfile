FROM python:3.11-slim

# System dependencies
# - poppler-utils  → pdf2image (PDF to image conversion)
# - ghostscript    → camelot-py (table extraction from PDFs)
# - libsm6 etc.   → opencv-python-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    ghostscript \
    libsm6 \
    libxext6 \
    libxrender1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs as non-root user (required)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /home/user/app

# Install Python dependencies (cached layer)
COPY --chown=user requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy project source files
COPY --chown=user backend/    ./backend/
COPY --chown=user frontend/   ./frontend/
COPY --chown=user modules/    ./modules/

# Create writable runtime directories
RUN mkdir -p /tmp/uploads /tmp/reports

# Hugging Face Spaces MUST expose port 7860
EXPOSE 7860

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "7860"]
