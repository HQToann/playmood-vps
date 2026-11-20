from decouple import config

# 1. PostgreSQL (VM3)
# dùng để xác thức sessionid và truy vấn cơ bản (asyncpg)
DB_HOST = config("DB_HOST")
DB_PORT = config("DB_PORT")
DB_NAME = config("DB_NAME")
DB_USER = config("DB_USER")
DB_PASSWORD = config("DB_PASSWORD")

# 2. Redis (VM3)
# dùng cho  Pub/Sub đồng bộ Websocket giữa các instance
REDIS_URL = config("REDIS_URL")

# 3. Kafka (VM4)
# nhận sự kiện đăng bài hát mới , theo dòi người dùng
KAFKA_ENABLED = config("KAFKA_ENABLED", cast=bool)
KAFKA_BOOTSTRAP_SERVERS = config("KAFKA_BOOTSTRAP_SERVERS")
KAFKA_CONSUMER_GROUP = config("KAFKA_CONSUMER_GROUP")

# Danh sách Topic Kafka cần lắng nghe
KAFKA_TOPICS = [
    "playmood.song.published",
    "playmood.user.followed",
]

# 4. Cấu hình ứng dụng
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", cast = bool)
PORT = config("PORT", cast=int)