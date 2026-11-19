import json
import logging
from django.core.cache import cache

# Import các topic và producer từ realtime_bus
from music_platform.realtime_bus import (
    publish_event,
    TOPIC_SONG_PUBLISHED,
    TOPIC_SONG_PLAYED,
    TOPIC_SONG_LIKED,
    TOPIC_SONG_RATED,
)

logger = logging.getLogger(__name__)

def get_cached_recommendations(user_id) -> list[str] | None:
    """
    Lấy danh sách song_id đã được VM2 (Recommender) tính toán và lưu vào Redis.
    Key format: recsys:for_you:<user_id>
    Trả về list chuỗi UUID bài hát hoặc None nếu chưa có cache.
    """
    cache_key = f"recsys:for_you:{user_id}"
    try:
        data = cache.get(cache_key)
        if not data:
            return None

        # 1. Nếu dữ liệu lưu dưới dạng JSON String
        if isinstance(data, str):
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
            return None

        # 2. Nếu dữ liệu đã là List
        elif isinstance(data, list):
            return [str(item) for item in data]

    except Exception as e:
        logger.warning("Lỗi đọc cache gợi ý từ Redis cho user %s: %s", user_id, e)
    
    return None