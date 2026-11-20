# 1. Base Image
FROM python:3.11-slim

# 2. Cấu hình biến môi trường hệ thống của Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# 3. Cài đặc các thư viện hệ thống cần thiết (gcc, libpq-dev cho psycopg2, curl cho health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists*

# 4. Thiết lập thư mục làm việc trong container
WORKDIR /app

# 5. Tận dụng Docker Cache: Copy requirements và cài đặc thư viện Python trước
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy toàn bộ mã nguồn vào container
COPY . .

# 7. Chạy collectstatic lúc build với Dummy Environment Variables
# (giúp Pod khởi động ngay lập tức mà không phải tốn thời gian gom file tĩnh lúc runtime)
RUN SECRET_KEY="build-time-dummy-secret-key-not-for-production" \
    DEBUG="False" \
    ALLOWED_HOSTS="*" \
    CSRF_TRUSTED_ORIGINS="http://localhost" \
    FRONTEND_URL="http://localhost:3000" \
    CORS_ALLOWED_ORIGINS="http://localhost:3000" \
    KAFKA_ENABLED="False" \
    KAFKA_BOOTSTRAP_SERVERS="localhost:9092" \
    CLOUDINARY_PREFIX="playmood" \
    SESSION_COOKIE_AGE="86400" \
    RESEND_API_KEY="dummy-resend-key" \
    DEFAULT_FROM_EMAIL="noreply@playmood.local" \
    RATELIMIT_ENABLE="False" \
    python manage.py collectstatic --noinput

# 8. Tạo Non-Root User (appuser) để đảm bảo an toàn bảo mật trên Kubernets
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup --no-create-home appuser && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/entrypoint.sh

# 9. Chuyển sang user bảo mật
USER appuser

# 10. Expose cổng HTTP
EXPOSE 8000

# 11. Khởi chạy thông quan entrypoint script
ENTRYPOINT [ "/app/entrypoint.sh" ]