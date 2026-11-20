#!/bin/sh
set -e

echo "==> [PlayMood Recommender] Khởi động Kafka Consumer Worker..."

exec python -m recommender.main
