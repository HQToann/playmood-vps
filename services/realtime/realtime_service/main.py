# realtime_service/main.py
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from . import config
from .auth_db import get_db_pool, get_user_from_session
from .ws_hub import WsHub
from .worker import run_kafka_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

hub = WsHub()
db_pool = None


# 1. Lifespan: Quản lý vòng đời khởi động / tắt ứng dụng
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logger.info("==> [PlayMood Realtime] Đang khởi động service...")
    
    # 1. Khởi tạo Connection Pool PostgreSQL
    try:
        db_pool = await get_db_pool()
    except Exception as e:
        logger.error("Không thể khởi tạo PostgreSQL pool: %s", e)

    # 2. Khởi tạo Redis kết nối và lắng nghe Pub/Sub
    await hub.setup()
    redis_task = asyncio.create_task(hub.start_redis_listener())

    # 3. Khởi tạo Kafka Consumer Worker (nếu bật)
    kafka_task = None
    if config.KAFKA_ENABLED and db_pool:
        kafka_task = asyncio.create_task(run_kafka_worker(hub, db_pool))

    logger.info("==> [PlayMood Realtime] Đã sẵn sàng phục vụ tại cổng %d", config.PORT)
    yield

    # Shutdown: Dọn dẹp tài nguyên
    logger.info("==> [PlayMood Realtime] Đang đóng tài nguyên...")
    redis_task.cancel()
    if kafka_task:
        kafka_task.cancel()
    if db_pool:
        await db_pool.close()
    logger.info("==> [PlayMood Realtime] Đã tắt an toàn.")


app = FastAPI(title="PlayMood Realtime Service", lifespan=lifespan)


# 2. Helper: Trích xuất sessionid từ Cookie Header
def _extract_session_id(ws: WebSocket) -> str | None:
    cookie_header = ws.headers.get("cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("sessionid="):
            return part[len("sessionid="):]
    return None


# 3. Health Checks cho K3s (Liveness & Readiness)
@app.get("/health/")
async def health(type: str = "readiness"):
    if type == "liveness":
        return JSONResponse({"status": "alive"})

    # Readiness: Kiểm tra ping Redis
    try:
        if hub._redis:
            await hub._redis.ping()
            return JSONResponse({"status": "healthy"})
        return JSONResponse({"status": "unhealthy", "reason": "Redis client not ready"}, status_code=503)
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "reason": str(e)}, status_code=503)


# 4. WebSocket: Thông báo cá nhân (/ws/notifications/)
@app.websocket("/ws/notifications/")
async def ws_notifications(ws: WebSocket):
    session_id = _extract_session_id(ws)
    user = await get_user_from_session(db_pool, session_id)
    if not user:
        await ws.close(code=4001)
        return

    room = f"user_{user['id']}"
    await ws.accept()
    await hub.add(room, ws)
    logger.info("[WS Notifications] User %s (%s) đã kết nối.", user["username"], room)

    try:
        while True:
            # Giữ kết nối mở, client notifications chỉ nhận sự kiện
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.remove(room, ws)
        logger.info("[WS Notifications] User %s ngắt kết nối.", user["username"])


# 5. WebSocket: Hiện diện toàn cục & Bạn bè (/ws/chat/global/)
@app.websocket("/ws/chat/global/")
async def ws_global(ws: WebSocket):
    session_id = _extract_session_id(ws)
    user = await get_user_from_session(db_pool, session_id)
    if not user:
        await ws.close(code=4001)
        return

    room = f"user_global_{user['id']}"
    await ws.accept()
    await hub.add(room, ws)

    # Lấy danh sách bạn bè (follow chéo) để thông báo mình vừa Online
    friend_ids = await _get_friend_ids(user["id"])
    for fid in friend_ids:
        await hub.publish(f"user_global_{fid}", {
            "type": "presence_update",
            "user_id": user["id"],
            "status": "online",
        })

    logger.info("[WS Global] User %s online.", user["username"])

    try:
        while True:
            text = await ws.receive_text()
            data = json.loads(text)
            if data.get("type") == "heartbeat":
                pass  # Giữ kết nối sống
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await hub.remove(room, ws)
        # Thông báo bạn bè mình đã Offline
        for fid in friend_ids:
            await hub.publish(f"user_global_{fid}", {
                "type": "presence_update",
                "user_id": user["id"],
                "status": "offline",
            })
        logger.info("[WS Global] User %s offline.", user["username"])


# 6. WebSocket: Trò chuyện 1-1 (/ws/chat/conversation/{conv_id}/)
@app.websocket("/ws/chat/conversation/{conv_id}/")
async def ws_chat(ws: WebSocket, conv_id: str):
    session_id = _extract_session_id(ws)
    user = await get_user_from_session(db_pool, session_id)
    if not user:
        await ws.close(code=4001)
        return

    # Kiểm tra quyền truy cập vào đoạn chat
    has_access = await _check_conversation_access(user["id"], conv_id)
    if not has_access:
        await ws.close(code=4003)
        return

    room = f"chat_{conv_id}"
    await ws.accept()
    await hub.add(room, ws)
    logger.info("[WS Chat] User %s vào phòng %s", user["username"], room)

    try:
        while True:
            text = await ws.receive_text()
            data = json.loads(text)
            event_type = data.get("type")

            # 1. Gửi tin nhắn mới
            if event_type == "send_message":
                new_msg = await _create_message(user, conv_id, data)
                if new_msg:
                    # Phát sóng tin nhắn cho tất cả người trong phòng chat
                    await hub.publish(room, {
                        "type": "new_message",
                        "data": new_msg
                    })
                    # Bắn thông báo Toast chuông cho người nhận ở màn hình ngoài
                    recipients = await _get_other_participants(conv_id, user["id"])
                    content_preview = data.get("content", "")
                    short_content = (content_preview[:50] + "...") if len(content_preview) > 50 else content_preview
                    for rid in recipients:
                        await hub.publish(f"user_{rid}", {
                            "message": "new_chat_message",
                            "notification": {
                                "title": f"Tin nhắn từ {user['username']}",
                                "message": short_content or "Đã gửi một đính kèm",
                            },
                        })

            # 2. Đang gõ tin nhắn (Typing indicator)
            elif event_type == "typing_status":
                await hub.publish(room, {
                    "type": "typing_status",
                    "user_id": user["id"],
                    "is_typing": data.get("is_typing", False),
                })

            # 3. Đánh dấu đã đọc (Read receipt)
            elif event_type == "mark_read":
                updated_count = await _mark_messages_read(conv_id, user["id"])
                if updated_count > 0:
                    await hub.publish(room, {
                        "type": "read_receipt",
                        "user_id": user["id"],
                    })

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await hub.remove(room, ws)
        logger.info("[WS Chat] User %s rời phòng %s", user["username"], room)


# 7. WebSocket: Bảng tin (/ws/feed/)
@app.websocket("/ws/feed/")
async def ws_feed(ws: WebSocket):
    session_id = _extract_session_id(ws)
    user = await get_user_from_session(db_pool, session_id)
    if not user:
        await ws.close(code=4001)
        return

    room = "live_feed"
    await ws.accept()
    await hub.add(room, ws)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.remove(room, ws)


# 8. Database Helpers (asyncpg)
async def _get_friend_ids(user_id: str) -> list[str]:
    """Lấy danh sách ID bạn bè (theo dõi lẫn nhau) từ bảng social_follow."""
    if not db_pool:
        return []
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT f1.follower_id::text
                FROM social_follow f1
                INNER JOIN social_follow f2
                  ON f1.follower_id = f2.following_id
                 AND f1.following_id = f2.follower_id
                WHERE f1.following_id = $1::uuid
                """,
                user_id,
            )
            return [r["follower_id"] for r in rows]
    except Exception as e:
        logger.error("Lỗi lấy danh sách bạn bè: %s", e)
        return []


async def _check_conversation_access(user_id: str, conv_id: str) -> bool:
    """Kiểm tra xem người dùng có phải thành viên của cuộc trò chuyện hay không."""
    if not db_pool:
        return False
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM chat_conversation_participants
                WHERE conversation_id = $1::uuid AND user_id = $2::uuid
                """,
                conv_id, user_id,
            )
            return row is not None
    except Exception as e:
        logger.error("Lỗi kiểm tra quyền conversation: %s", e)
        return False


async def _create_message(user: dict, conv_id: str, data: dict) -> dict | None:
    """Tạo tin nhắn mới trong PostgreSQL và cập nhật updated_at của Conversation."""
    if not db_pool:
        return None
    content = data.get("content", "").strip()
    image_url = data.get("image_url")
    if not content and not image_url:
        return None

    try:
        new_msg_id = str(uuid.uuid4())
        async with db_pool.acquire() as conn:
            # 1. Thêm tin nhắn mới vào bảng chat_message
            row = await conn.fetchrow(
                """
                INSERT INTO chat_message
                  (id, conversation_id, sender_id, content, image_url, is_read, reactions, created_at)
                VALUES
                  ($1::uuid, $2::uuid, $3::uuid, $4, $5, FALSE, '{}'::jsonb, NOW())
                RETURNING id::text, content, image_url, created_at::text
                """,
                new_msg_id, conv_id, user["id"], content, image_url,
            )
            # 2. Đẩy conversation lên đầu danh sách chat
            await conn.execute(
                "UPDATE chat_conversation SET updated_at = NOW() WHERE id = $1::uuid",
                conv_id,
            )

        return {
            "id": row["id"],
            "conversation_id": conv_id,
            "sender": {
                "id": user["id"],
                "username": user["username"],
            },
            "content": row["content"],
            "image_url": row["image_url"],
            "is_read": False,
            "created_at": row["created_at"],
        }
    except Exception as e:
        logger.error("Lỗi lưu tin nhắn vào DB: %s", e)
        return None


async def _mark_messages_read(conv_id: str, user_id: str) -> int:
    """Đánh dấu tất cả tin nhắn gửi cho mình trong phòng chat thành đã đọc."""
    if not db_pool:
        return 0
    try:
        async with db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE chat_message
                SET is_read = TRUE
                WHERE conversation_id = $1::uuid
                  AND sender_id != $2::uuid
                  AND is_read = FALSE
                """,
                conv_id, user_id,
            )
            return int(result.split()[-1])
    except Exception as e:
        logger.error("Lỗi đánh dấu tin nhắn đã đọc: %s", e)
        return 0


async def _get_other_participants(conv_id: str, current_user_id: str) -> list[str]:
    """Lấy danh sách ID các thành viên khác trong phòng chat."""
    if not db_pool:
        return []
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id::text
                FROM chat_conversation_participants
                WHERE conversation_id = $1::uuid AND user_id != $2::uuid
                """,
                conv_id, current_user_id,
            )
            return [r["user_id"] for r in rows]
    except Exception:
        return []