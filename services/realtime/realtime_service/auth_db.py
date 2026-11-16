import psycopg2
from psycopg2.extras import RealDictCursor
import base64
import json
from .config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

def get_db_connection():
    #tạo kết nối tới PostgreSQL
    return psycopg2.connect(
        host = DB_HOST,
        port = DB_PORT,
        dbname = DB_NAME,
        user = DB_USER,
        password = DB_PASSWORD
    )

def decode_django_session(session_data):
    #giải mã session data của Django
    try:
        if ':' not in session_data:
            return None
        #lấy phần data đằng sau dấu ':'
        encoded_data = session_data.split(':', 1)[1]
        decoded_bytes = base64.b64decode(encoded_data).decode('utf8-8')
        return json.loads(decoded_bytes)
    except Exception as e:
        print(f"[Xác thực lỗi] không thể giải mã session: {e}")
        return None

def get_user_from_session(session_id: str):
    #truy vấn postgreSQL để lấy tông tin user dựa vào cookie sessionid
    #trả về dict chứa thông tin user hoặc None nếu không hợp lệ
    if not session_id:
        return None

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        #tìm session còn hạn trong bảng django_session
        query_session = """
        SELECT session_data 
        FROM django_session 
        WHERE session_key = %s AND expire_date > NOW()
        """
        cur.execute(query_session, (session_id,))
        session_row = cur.fetchone()

        if not session_row:
            return None

        #giải mã session để lấy _auth_user_id
        session_dict = decode_django_session(session_row['session_data'])
        if not session_dict:
            return None

        user_id = session_dict.get('_auth_user_id')
        if not user_id:
            return None

        #lấy thông tin cơ bản của user (bảng accounts_user tự định nghĩa)
        query_user = """
            SELECT id, username, email 
            FROM accounts_user 
            WHERE id = %s
        """

        cur.execute(query_user, (int(user_id),))
        user = cur.fetchone()

        return dict(user) if user else None

    except Exception as e:
        print(f"[Database lỗi] {e}")
        return None
    finally:
        if conn:
            conn.close()

        