FROM python:3.11-slim

# Disable Python stdout buffering to ensure logs print immediately
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies directly
RUN pip install --no-cache-dir \
    "fastapi>=0.100.0" \
    "uvicorn>=0.22.0" \
    "python-telegram-bot>=20.3" \
    "httpx>=0.24.1" \
    "python-dotenv>=1.0.0" \
    "pydantic>=2.0" \
    "websockets>=11.0" \
    "psutil>=5.9.0" \
    "fastembed>=0.2.0" \
    "qdrant-client>=1.13.2" \
    "matplotlib>=3.7.0" \
    "docker>=6.1.0" \
    "pandas>=2.0.0" \
    "openpyxl>=3.1.0" \
    "beautifulsoup4>=4.12.0" \
    "python-multipart>=0.0.7" \
    "google-auth>=2.20.0" \
    "google-auth-oauthlib>=1.0.0" \
    "google-auth-httplib2>=0.2.0" \
    "google-api-python-client>=2.95.0" \
    "todoist-api-python>=2.1.3" \
    "faster-whisper>=1.1.0"



# Copy source code and environment configuration
COPY backend/ /app/backend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
