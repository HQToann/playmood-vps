##!/usr/bin/env bash
set -e


echo "Khởi động máy chủ thời gian thực (Starlette)..."
#khởi chạy Uvicorn server, trỏ đến file main.py và biến app

exec uvicorn realtime_service.main:app --host 0.0.0.0 --port 8000 --workers 2