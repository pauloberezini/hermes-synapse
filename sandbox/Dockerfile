FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential needed for some pip packages)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --gid 10002 sandbox \
    && useradd --uid 10002 --gid sandbox --create-home --home-dir /home/sandbox sandbox \
    && mkdir -p /mnt/data \
    && touch /mnt/data/.keep \
    && chown -R sandbox:sandbox /app /mnt/data /home/sandbox

USER sandbox

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
