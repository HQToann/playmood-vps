import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, KafkaError, Producer

from .config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_RECSYS_GROUP_ID,
    KAFKA_TOPIC_RECOMMENDATIONS,
    KAFKA_TOPIC_USER_EVENTS,
    TOP_K,
)
from .cosine_cf import CosineCFRecommender
from .data_prep import (
    InteractionDataset,
    ensure_recsys_tables,
    load_from_csv,
    load_from_postgres,
    upsert_listen_event,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("playmood.recommender.worker")

# "postgres" khi chạy hệ thống thật nối VM3; "csv" nếu muốn test Kafka mà chưa bật PostgreSQL
DATA_SOURCE = os.getenv("RECSYS_DATA_SOURCE", "postgres").strip().lower()


class RecommenderWorker:
    """Kafka Worker chạy trên VM2: nhận sự kiện nghe nhạc -> cập nhật DB -> xuất Top K gợi ý."""

    def __init__(self, data_source: str = DATA_SOURCE) -> None:
        self.data_source = data_source
        self.running = True
        self.dataset: Optional[InteractionDataset] = None
        # Mặc định tự dùng K_NEIGHBORS=30, use_log=True và fallback Popularity (user_count)
        self.model = CosineCFRecommender()

        self.consumer = Consumer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                "group.id": KAFKA_RECSYS_GROUP_ID,
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
        )
        self.producer = Producer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            }
        )

    def _load_and_fit(self) -> None:
        """Nạp tập dữ liệu tương tác và huấn luyện lại mô hình Cosine CF."""
        if self.data_source == "postgres":
            ensure_recsys_tables()
            dataset = load_from_postgres(apply_limits=False)
            # Nếu DB mới khởi tạo chưa có dòng nào, tự động lấy tập CSV làm dữ liệu nền ban đầu
            if dataset.num_users == 0 or dataset.num_songs == 0:
                logger.warning(
                    "Bảng recsys_interactions trên PostgreSQL đang trống. "
                    "Tạm nạp dữ liệu nền từ CSV cục bộ."
                )
                dataset = load_from_csv(apply_limits=True)
        else:
            dataset = load_from_csv(apply_limits=True)

        self.dataset = dataset
        self.model.fit(self.dataset)
        logger.info(
            "Đã nạp mô hình thành công: %d users, %d songs (nguồn: %s).",
            self.dataset.num_users,
            self.dataset.num_songs,
            self.data_source,
        )

    def _delivery_report(self, err: Any, msg: Any) -> None:
        if err is not None:
            logger.error("Gửi gợi ý lên Kafka thất bại: %s", err)
        else:
            logger.info(
                "Đã gửi gợi ý tới topic=%s partition=%d offset=%d",
                msg.topic(),
                msg.partition(),
                msg.offset(),
            )

    def _publish_recommendations(self, user_id: str, trigger_event: str) -> None:
        recs = self.model.recommend(
            user_id=user_id,
            top_k=TOP_K,
            exclude_listened=True,
        )
        payload = {
            "user_id": user_id,
            "trigger_event": trigger_event,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "top_k": TOP_K,
            "recommendations": recs,
        }
        self.producer.produce(
            topic=KAFKA_TOPIC_RECOMMENDATIONS,
            key=user_id.encode("utf-8"),
            value=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            callback=self._delivery_report,
        )
        self.producer.poll(0)

    def handle_event(self, event: Dict[str, Any]) -> None:
        """Xử lý một thông điệp JSON từ topic playmood.user_events."""
        user_id = str(event.get("user_id", "")).strip()
        if not user_id:
            logger.warning("Bỏ qua sự kiện thiếu user_id: %s", event)
            return

        event_type = str(event.get("event_type", "song_played")).strip().lower()
        song_id = str(event.get("song_id", "")).strip()
        listen_count = int(event.get("listen_count", 1))

        if event_type != "request_recommendations" and song_id:
            if self.data_source == "postgres":
                new_total = upsert_listen_event(
                    user_id=user_id,
                    song_id=song_id,
                    increment=listen_count,
                )
                logger.info(
                    "Đã cập nhật DB: user=%s song=%s (+%d -> tổng %d).",
                    user_id,
                    song_id,
                    listen_count,
                    new_total,
                )
                # Nạp lại ma trận và tính lại tương đồng (rất nhanh ở quy mô vài trăm bài/user)
                self._load_and_fit()
            else:
                logger.info(
                    "[Chế độ CSV] Nhận sự kiện nghe: user=%s song=%s (+%d).",
                    user_id,
                    song_id,
                    listen_count,
                )

        self._publish_recommendations(user_id=user_id, trigger_event=event_type)

    def stop(self, *_args: Any) -> None:
        logger.info("Nhận tín hiệu dừng worker, đang đóng kết nối an toàn...")
        self.running = False

    def run(self) -> None:
        self._load_and_fit()
        self.consumer.subscribe([KAFKA_TOPIC_USER_EVENTS])
        logger.info(
            "Recommender Worker đang lắng nghe topic '%s' tại %s...",
            KAFKA_TOPIC_USER_EVENTS,
            KAFKA_BOOTSTRAP_SERVERS,
        )

        try:
            while self.running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Lỗi Kafka Consumer: %s", msg.error())
                    continue

                try:
                    raw_value = msg.value().decode("utf-8")
                    event = json.loads(raw_value)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.warning("Bỏ qua thông điệp JSON không hợp lệ: %s", exc)
                    self.consumer.commit(message=msg, asynchronous=False)
                    continue

                try:
                    self.handle_event(event)
                    self.producer.flush(timeout=5.0)
                    self.consumer.commit(message=msg, asynchronous=False)
                except Exception as exc:
                    logger.exception("Lỗi khi xử lý sự kiện %s: %s", event, exc)
        finally:
            self.producer.flush(timeout=5.0)
            self.consumer.close()
            logger.info("Đã dừng Recommender Worker.")


def main() -> None:
    worker = RecommenderWorker()
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    worker.run()


if __name__ == "__main__":
    main()