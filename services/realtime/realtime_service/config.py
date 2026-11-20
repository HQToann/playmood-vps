# realtime_service/config.py
from decouple import config

# 1. PostgreSQL (VM3)
DB_HOST     = config("DB_HOST", default="192.168.1.30")
DB_PORT     = config("DB_PORT", cast=int, default=5432)
DB_NAME     = config("DB_NAME", default="playmood_db")
DB_USER     = config("DB_USER", default="playmood_user")
DB_PASSWORD = config("DB_PASSWORD", default="")

# 2. Redis (VM3)
REDIS_URL   = config("REDIS_URL", default="redis://192.168.1.30:6379/0")

# 3. Kafka (VM4)
KAFKA_ENABLED           = config("KAFKA_ENABLED", cast=bool, default=False)
KAFKA_BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS", default="192.168.1.40:9092")
KAFKA_CONSUMER_GROUP    = config("KAFKA_CONSUMER_GROUP", default="realtime-service")

# Danh sách Topic Kafka cần lắng nghe
KAFKA_TOPICS = [
    "playmood.song.published",
    "playmood.user.followed",
]

# 4. Cấu hình ứng dụng
SECRET_KEY  = config("SECRET_KEY", default="insecure-secret-key-for-dev")
DEBUG       = config("DEBUG", cast=bool, default=False)
PORT        = config("PORT", cast=int, default=8001)