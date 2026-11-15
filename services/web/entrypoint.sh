#!/bin/sh
set -e

echo "==> [PlayMood] Kiểm tra kết nối tới Database ($DB_HOST:$DB_PORT)..."
python << 'EOF'
import os
import socket
import time

host = os.environ.get('DB_HOST', '127.0.0.1')
port = int(os.environ.get('DB_PORT', 5432))

# Chờ tối đa 30s để DB sẵn sàng
for i in range(30):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"===> [PlayMood Web] Kết nối Database ({host}:{port}) thành công !")
            break
        except (socket.error, ConnectionRefusedError):
            print(f"===> [PlayMood Web] Đang chờ Database ({host}:{port}) ... ({i+1}/30)")
            time.sleep(1)
else:
    print("===> [PlayMood Web] LỖI: Hết thời gian chờ Database!")
    exit(1)
EOF

echo "===> [PlayMood Web] Chạy Database Migrations..."
python manage.py migrate --noinput

echo "===> [PlayMood Web] Khởi chạy Gunicorn WSGI..."
exec gunicorn music_platform.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -