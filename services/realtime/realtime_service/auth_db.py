# realtime_service/auth_db.py
import asyncpg
import base64
import json
import logging
import zlib
from . import config

logger = logging.getLogger(__name__)


async def get_db_pool() -> asyncpg.Pool:
    """
    Tạo Connection Pool kết nối PostgreSQL (Asyncpg).
    Hàm này được gọi 1 lần duy nhất trong lifespan startup của FastAPI.
    """
    logger.info("Đang khởi tạo connection pool PostgreSQL (%s:%d)...", config.DB_HOST, config.DB_PORT)
    return await asyncpg.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        database=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        min_size=2,
        max_size=10,
    )


def decode_django_session(session_data: str) -> dict | None:
    """
    Giải mã session_data chuẩn của Django (bao gồm cả uncompressed lẫn compressed zlib).
    Cấu trúc: '<payload_base64>:<timestamp>:<signature>'
    """
    try:
        if not session_data:
            return None

        # 1. Dữ liệu thực sự nằm ở TRƯỚC dấu ':' đầu tiên
        raw_payload = session_data.split(':', 1)[0]

        # 2. Kiểm tra xem Django có nén zlib không (bắt đầu bằng dấu '.')
        is_compressed = raw_payload.startswith('.')
        if is_compressed:
            raw_payload = raw_payload[1:]

        # 3. Bổ sung padding URL-safe base64 và giải mã
        pad = '=' * (-len(raw_payload) % 4)
        decoded_bytes = base64.urlsafe_b64decode(raw_payload + pad)

        # 4. Giải nén zlib nếu cần
        if is_compressed:
            decoded_bytes = zlib.decompress(decoded_bytes)

        return json.loads(decoded_bytes.decode('utf-8'))
    except Exception as e:
        logger.warning("[Auth] Giải mã session_data thất bại: %s", e)
        return None


async def get_user_from_session(pool: asyncpg.Pool, session_id: str) -> dict | None:
    """
    Xác thực session_id từ cookie của Django và trả về thông tin user.
    Trả về dict user hoặc None nếu session không hợp lệ/hết hạn.
    """
    if not session_id or not pool:
        return None

    try:
        async with pool.acquire() as conn:
            # 1. Tìm phiên đăng nhập còn hạn trong bảng django_session
            query_session = """
                SELECT session_data 
                FROM django_session 
                WHERE session_key = $1 AND expire_date > NOW()
            """
            session_row = await conn.fetchrow(query_session, session_id)
            if not session_row:
                return None

            # 2. Giải mã session để lấy ID người dùng
            session_dict = decode_django_session(session_row['session_data'])
            if not session_dict:
                return None

            user_id = session_dict.get('_auth_user_id')
            if not user_id:
                return None

            # 3. Lấy thông tin người dùng từ bảng accounts_user (Khóa chính là UUID)
            query_user = """
                SELECT id::text, username, email, role, is_active
                FROM accounts_user 
                WHERE id = $1::uuid AND is_active = TRUE
            """
            user_row = await conn.fetchrow(query_user, str(user_id))
            if not user_row:
                return None

            return dict(user_row)

    except Exception as e:
        logger.error("[Auth] Lỗi cơ sở dữ liệu khi xác thực session: %s", e)
        return None