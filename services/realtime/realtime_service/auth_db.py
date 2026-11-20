import asyncpg
import base64
import json
import logging

from . import config

logger = logging.getLogger(__name__)

async def get_db_pool() -> asyncpg.Pool:
    """
    Tạo Connection Pool kết nối PostgreSQL (Asyncpg)
    Hàm này được gọi 1 lần duy nhất trong lifespan startup của FastAPI
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
    Giải mã session_data chuẩn của Django 4.1+
    Định dạng lưu trong DB: '<hash>:<base64_encoded_json>'
    """
    try:
        if not session_data or ':' not in session_data:
            return None
        
        # bỏ qua phần chữ ký băm (hash), chỉ lấy phần base64 phía sau
        encoded_payload = session_data.split(':', 1)[1]
        decoded_json = base64.b64decode(encoded_payload).decode('utf-8')
        return json.loads(decoded_json)
    except Exception as e:
        logger.warning("[Auth] Giải mã session_data thất bại: %s", e)
        return None

async def get_user_from_session(pool: asyncpg.Pool, session_id: str) -> dict | None:
    """
    Xác thực session_id từ cookie của Django và trả về thông tin user
    Trả về dict user hoặc None nếu session không hợp lệ/hết hạn
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
            
            # 3. Lấy thông tin người dùng từ bảng accounts_user (Khoá chính là UUID)
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