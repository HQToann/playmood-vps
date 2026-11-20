#!/bin/sh
set -e

echo "==> [PlayMood Realtime] Khởi chạy Uvicorn tại cổng ${PORT:-8001}..."

exec uvicorn realtime_service.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8001}" \
    --log-level info