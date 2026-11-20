FROM python:3.11-slim

WORKDIR /app

# Cài thư viện hệ thống cần cho psycopg2 và confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Cài Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ source code và data
COPY . .

# Chạy với user không phải root
RUN useradd -r -u 1001 appuser && chown -R appuser /app
USER appuser

ENTRYPOINT ["sh", "entrypoint.sh"]
