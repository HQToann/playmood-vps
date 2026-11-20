import asyncio
import json
import logging

from confluent_kafka import Consumer, KafkaError
import asyncpg
from . import config
from .ws_hub import WsHub

logger = logging.getLogger(__name__)

def _build_consumer() -> Consumer:
    """Khởi tạo Kafka Consumer đồng bộ với C-binding"""
    return Consumer(
        {
            "bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS,
            "group.id": config.KAFKA_CONSUMER_GROUP,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
            "session.timeout.ms": 6000,
        }
    )

async def _handle_song_published(data: dict, hub: WsHub, pool: asyncpg.Pool):
    """
    Xử lý sự kiện: Nghệ sĩ phát hành bài hát mới.
    Bắn thông báo tới tất cả người đang theo dõi nghệ sĩ này.
    """
    artist_id = data.get("artist_id")
    song_id = data.get("song_id")
    song_title = data.get("title", "Bài hát mới")
    if not artist_id or not pool:
        return
    try:
        async with pool.acquire() as conn:
            # 1. Lấy nghệ danh/tên của nghệ sĩ (bảng accounts_user)
            artist_row = await conn.fetchrow(
                "SELECT username FROM accounts_user WHERE id = $1::uuid",
                artist_id
            )
            artist_name = artist_row["username"] if artist_row else "Nghệ sĩ"
            # 2. Lấy danh sách ID người theo dõi (bảng social_follow)
            rows = await conn.fetch(
                "SELECT follower_id::text FROM social_follow WHERE following_id = $1::uuid",
                artist_id,
            )
        logger.info("[Kafka Worker] Bài hát '%s' đã ra mắt. Đang gửi tới %d followers...", song_title, len(rows))
        # 3. Bắn WebSocket qua WsHub tới từng người theo dõi
        notification_payload = {
            "message": "new_notification",
            "notification": {
                "notif_type": "song_published",
                "message": f'{artist_name} vừa phát hành bài hát mới "{song_title}"',
                "target_type": "song",
                "target_id": str(song_id) if song_id else None,
            },
        }
        for row in rows:
            follower_id = row["follower_id"]
            await hub.publish(f"user_{follower_id}", notification_payload)
    except Exception as e:
        logger.error("[Kafka Worker] Lỗi xử lý sự kiện 'playmood.song.published': %s", e)

async def _handle_user_followed(data: dict, hub: WsHub, pool: asyncpg.Pool):
    """
    Xử lý sự kiện: Có người theo dõi mới
    Bắn thông báo tới người được theo dõi (following_id)
    """
    follower_id = data.get("follower_id")
    following_id = data.get("following_id")

    if not following_id or not follower_id:
        return

    try:
        # lấy tên người theo dõi
        follower_name = "Ai đó"
        if pool:
            async with pool.acquire() as conn:
                user_row = await conn.fetchrow(
                    "SELECT username FROM accounts_user WHERE id = $1::uuid",
                    follower_id
                )
                if user_row:
                    follower_name = user_row["username"]

        # bắn websocket cho người nhận
        await hub.publish(
            f"user_{following_id}",
            {
                "message": "new_notification",
                "notification": {
                    "notif_type": "user_followed",
                    "message": f"{follower_name} đã bắt đầu theo dõi bạn",
                    "target_type": "user",
                    "target_id": str(follower_id),
                },
            },
        )
        logger.info("[Kafka Worker] Đã gửi thông báo theo dõi tới user_%s", following_id)

    except Exception as e:
        logger.error("[Kafka Worker] Lỗi xử lý sự kiện 'playmood.user.followed': %s", e)

async def run_kafka_worker(hub: WsHub, pool: asyncpg.Pool):
    """
    Vòng lặp chạy nền của Kafka Consumer.
    Chạy song song và không block FastAPI/Uvicorn Event Loop.
    """
    if not config.KAFKA_ENABLED:
        logger.info("[Kafka Worker] KAFKA_ENABLED=False. Tạm dừng worker Kafka.")
        return
    logger.info("[Kafka Worker] Đang kết nối tới Kafka Broker (%s)...", config.KAFKA_BOOTSTRAP_SERVERS)
    try:
        consumer = _build_consumer()
        consumer.subscribe(config.KAFKA_TOPICS)
        logger.info("[Kafka Worker] Đã đăng ký lắng nghe các topic: %s", config.KAFKA_TOPICS)
    except Exception as e:
        logger.error("[Kafka Worker] Khởi tạo Kafka Consumer thất bại: %s", e)
        return
    try:
        while True:
            # BẮT BUỘC: Dùng asyncio.to_thread để tránh nghẽn Event Loop của Uvicorn
            msg = await asyncio.to_thread(consumer.poll, 1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error("[Kafka Worker] Lỗi Kafka: %s", msg.error())
                continue
            try:
                topic = msg.topic()
                raw_value = msg.value().decode("utf-8")
                payload = json.loads(raw_value)
                if topic == "playmood.song.published":
                    await _handle_song_published(payload, hub, pool)
                elif topic == "playmood.user.followed":
                    await _handle_user_followed(payload, hub, pool)
            except Exception as e:
                logger.warning("[Kafka Worker] Lỗi phân tích gói tin Kafka: %s", e)
    except asyncio.CancelledError:
        logger.info("[Kafka Worker] Nhận tín hiệu dừng từ hệ thống.")
    finally:
        consumer.close()
        logger.info("[Kafka Worker] Đã đóng Kafka Consumer an toàn.")