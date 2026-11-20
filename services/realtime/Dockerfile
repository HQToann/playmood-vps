FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001

# Cài đặt các gói phụ thuộc hệ thống cần cho asyncpg và confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cài đặt Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ mã nguồn service
COPY . .

# Tạo user không đặc quyền và cấp quyền thực thi cho entrypoint
RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app \
    && chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8001

ENTRYPOINT ["/app/entrypoint.sh"]