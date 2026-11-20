from pathlib import Path
from decouple import config

#path dữ liệu thử nghiệm
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR/"data"
RAW_DATA_DIR = DATA_DIR/"raw"
PROCESSED_DATA_DIR = DATA_DIR/"processed"
PROCESSED_INTERACTIONS_FILE = PROCESSED_DATA_DIR/"interactions.csv"
PROCESSED_SONGS_FILE = PROCESSED_DATA_DIR/"songs.csv"

#kết nối với csdl (vm3)
DB_HOST     = config("RECSYS_DB_HOST",     default="192.168.1.30")
DB_PORT     = config("RECSYS_DB_PORT",     default="5432")
DB_NAME     = config("RECSYS_DB_NAME",     default="playmood_db")
DB_USER     = config("RECSYS_DB_USER",     default="playmood_user")
DB_PASSWORD = config("RECSYS_DB_PASSWORD", default="")

#kết nối với Kafka (vm4)
KAFKA_BOOTSTRAP_SERVERS   = config("KAFKA_BOOTSTRAP_SERVERS",    default="192.168.1.40:9092")
KAFKA_RECSYS_GROUP_ID     = config("KAFKA_RECSYS_GROUP_ID",      default="recommender-service")
KAFKA_GROUP_ID            = KAFKA_RECSYS_GROUP_ID   # alias tương thích ngược
KAFKA_TOPIC_USER_EVENTS   = config("KAFKA_TOPIC_USER_EVENTS",    default="playmood.user_events")
KAFKA_TOPIC_RECOMMENDATIONS = config("KAFKA_TOPIC_RECOMMENDATIONS", default="playmood.recommendations")

#các tham số của mô hình
TOP_K = config("RECSYS_TOP_K", default=5, cast=int)                # Số bài hát gợi ý trả về (Top 5)
K_NEIGHBORS = config("RECSYS_K_NEIGHBORS", default=20, cast=int)   # Số hồ sơ láng giềng Cosine gần nhất
MAX_USERS = config("RECSYS_MAX_USERS", default=100, cast=int)      # Giới hạn hồ sơ tập thử nghiệm
MAX_SONGS = config("RECSYS_MAX_SONGS", default=500, cast=int)      # Giới hạn bài hát phổ biến tập thử nghiệm
MIN_SIMILARITY = config("RECSYS_MIN_SIMILARITY", default=0.0, cast=float)

#tham số đánh gái mô hình
TEST_RATIO = config("RECSYS_TEST_RATIO", default=0.2, cast=float)  # Tỷ lệ giữ lại kiểm tra cho mỗi hồ sơ
RANDOM_SEED = config("RECSYS_RANDOM_SEED", default=42, cast=int)