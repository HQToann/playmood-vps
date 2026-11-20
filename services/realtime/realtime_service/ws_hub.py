import asyncio
import json
import logging
from typing import Dict, Set
import redis.asyncio as aioredis
from fastapi import WebSocket
from . import config

logger = logging.getLogger(__name__)

class WsHub:
    """
    Hub trung tâm quản lý các phiên kết nối WebSocket và điều phối tin nhắn
    Kết hợp lưu trữ kết nối trong RAM và đồng bộ liện Pod qua Redis Pub/Sub
    """
    def __init__(self):
        # lưu các socket kết nối nội bộ theo từng phòng: {"room_name": {ws1, ws2, ...}}
        self.rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._redis: aioredis.Redis | None = None

    async def setup(self):
        """Khởi tạo kết nối tới Redis (gọi trong lifespan startup)"""
        try:
            self._redis = aioredis.from_url(
                config.REDIS_URL,
                decode_responses=True,
            )
            # ping kiểm tra kết nối tới redis (WM3)
            await self._redis.ping()
            logger.info("Kết nối Redis Pub/Sub thành công tại %s", config.REDIS_URL)
        except Exception as e:
            logger.error("Không thể kết nối tới Redis (%s): %s", config.REDIS_URL, e)

    async def add(self, room: str, ws: WebSocket):
        """Thêm kết nối WebSocket vào một phòng cụ thể"""
        async with self._lock:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(ws)
            logger.debug("[Wshub] Socket đã tham gia phòng '%s' (Tổng: %d)", room, len(self._rooms[room]))

    async def remove(self, room: str, ws: WebSocket):
        """Xoá kết nối WebSocket khỏi phòng khi ngắt kết nối"""
        async with self._lock:
            if room in self.rooms:
                self._rooms[room].discard(ws)
                if not self._rooms[room]:
                    del self._rooms[room]
                logger.debug("[WsHub] Socket đã rời khỏi phòng '%s'", room)

    async def broadcast(self, room: str, payload: dict):
        """
        Gửi dữ liệu trực tiếp đến tất cả các client đang kết nối trong phòng trên Pob này
        Tự động phát hiện và dọn dẹp các kết nối bị đứt
        """
        text_data = json.dumps(payload)

        async with self._lock:
            # lấy bản sao danh sách socket để tránh lỗi kích thước dict khi duyệt
            sockets = set(self._rooms.get(room, set()))

        if not sockets:
            return

        dead_sockets = set()
        for ws in sockets:
            try:
                await ws.send_text(text_data)
            except Exception:
                # Socket đã đóng hoặc mất mạng đột ngột
                dead_sockets.add(ws)

        # dọn dẹp các socket đã chết
        if dead_sockets:
            async with self._lock:
                current_room_sockets = self._rooms.get(room, set())
                for dead_ws in dead_sockets.discard(dead_ws):
                    current_room_sockets.discard(dead_ws)
                if not current_room_sockets and room in self._rooms:
                    del self._rooms[room]

    async def publish(self, room: str, payload: dict):
        """
        1. Gửi tin nhắn các client nội bộ trên Pod này trước (không có độ trễ)
        2. Bắn sự kiện lên Redis Pub/Sub để các Pob khác cùng nhận được
        """
        # phát sóng nội bộ
        await self.broadcast(room, payload)

        # phát sóng qua Redis cho các Pob khác (nếu Redis khả dụng)
        if self._redis:
            try:
                channel = f"room:{room}"
                await self._redis.publish(channel, json.dumps(payload))
            except Exception as e:
                logger.warning("[WsHub] không thể publish lên Redis channel 'room:%s': %s", room, e)

    async def start_redis_listener(self):
        """
        Task chạy nền liên tục: Lắng nghe các thông điệp từ Redis Pub/Sub trên pattern 'room:*'
        Khi có thông điệp từ Pob khác gửi tới, giải mã và gọi broadcast nội bộ
        """
        if not self._redis:
            logger.warning("[WsHub] Redis chưa sẵn sàng, huỷ kích hoạt listener")
            return

        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("room:*")
        logger.info("[Wshub] đã bắt đầu lắng nghe Redis Pub/Sub trên kênh 'room:*'")

        try:
            async for message in pubsub.listen():
                if message and message.get("type") == "pmessage":
                    try:
                        channel = message.get("channel", "")
                        # trích xuất tên room từ channel "room:<room_name>"
                        room = channel[len("room:"):]
                        data = json.loads(message.get("data", "{}"))
                        # bắn xuống các client của Pod này
                        await self.broadcast(room, data)
                    except Exception as e:
                        logger.warning("[WsHub] Lỗi giải mã message từ Redis Pub/Sub: %s", e)
        except asyncio.CancelledError:
            logger.info("[WsHub] Redis listener nhận tín hiệu người dừng")
        except Exception as e:
            logger.error("[WsHub] Lỗi bất ngờ trong Redis listener loop: %s", e)
        finally:
            await pubsub.punsubscribe("room:*")
            await pubsub.close()