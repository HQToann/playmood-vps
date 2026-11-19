import json
import logging

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

logger = logging.getLogger(__name__)

# Định nghĩa danh sách các topic chuẩn giao tiếp với VM2 và VM4
TOPIC_SONG_PLAYED = "playmood.song.played"
TOPIC_SONG_LIKED = "playmood.song.liked"
TOPIC_SONG_PUBLISHED = "playmood.song.published"
TOPIC_SONG_RATED = "playmood.song.rated"
TOPIC_USER_FOLLOWED = "playmood.user.followed"
TOPIC_MOOD_UPDATED = "playmood.mood.updated"

_kafka_producer = None

def _delivery_report(err, msg):
    """Callback kích hoạt khi tin nhắn gửi thành công hoặc thất bại tới kafka."""
    if err is not None:
        logger.error("Kafka delivery thất bại cho topic %s: %s", msg.topic(), err)

def _get_producer():
    """Khởi tạo Kafka Producer singleton nếu KAFKA_ENABLED=True"""
    global _kafka_producer
    # Sửa: dùng 'settings' thay vì 'string'
    if not getattr(settings, 'KAFKA_ENABLED', False):
        return None
    if _kafka_producer is None:
        try:
            from confluent_kafka import Producer
            _kafka_producer = Producer(
                {
                    'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                    'socket.timeout.ms': 2000,
                    'message.timeout.ms': 3000,
                }
            )
        except Exception as e:
            logger.error("Không thể khởi tạo Kafka Producer: %s", e)
    return _kafka_producer

def publish_event(topic: str, key: str, payload: dict):
    """
    Bắn event sang Kafka (VM4)
    Nếu KAFKA_ENABLED=False thì tự động bỏ qua để không gây lỗi request HTTP
    """
    producer = _get_producer()
    if not producer:
        logger.debug("[KAFKA DISABLED] Bỏ qua event topic=%s key=%s", topic, key)
        return
    
    try:
        # Dùng DjangoJSONEncoder để tự động serialize an toàn UUID và datetime
        serialized_value = json.dumps(
            payload,
            ensure_ascii=False,
            cls=DjangoJSONEncoder
        ).encode('utf-8')

        # Sửa: đổi 'prodece' thành 'produce'
        producer.produce(
            topic=topic,
            key=str(key),
            value=serialized_value,
            on_delivery=_delivery_report  # Bắt lỗi bất đồng bộ nếu có
        )
        producer.poll(0)
    except Exception as e:
        logger.warning("Lỗi gửi event Kafka (topic=%s, key=%s): %s", topic, key, e)