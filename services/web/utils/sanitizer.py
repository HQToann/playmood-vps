import re
import bleach

# Regex tìm và xoá các cặp thẻ HTML nguy hiểm kèm theo toàn bộ nội dung bên trong
_DANGEROUS_TAGS_RE = re.compile(
    r'<(script|style|iframe|object|embed|applet|form|input|button|select|textarea|link|meta)'
    r'[^>]*>.*?</\1>',
    flags=re.DOTALL | re.IGNORECASE,
)

# Regex tìm và xoá các thẻ đơn hoặ thẻ tự đóng nguy hiểm (không có nội dung, hoặc không có thẻ đóng tương ứng)
_DANGEROUS_SELF_CLOSING_RE = re.compile(
    r'<(script|style|link|meta|input|button)[^>]*/?>',
    flags=re.IGNORECASE,
)

def sanitize_text(value: str) -> str:
    """
    Làm sạch chuỗi văn bản thuần tuý, loại bỏ hoàn toàn các thẻ HTML và nội dung độc (phòng chống XSS)
    
    Logic xử lý:
    1. Kiểm tra nếu gt trị rỗng/None thì trả về chuỗi rỗng
    2. Dùng regex loại bỏ khối thẻ nguy hiểm và mã thực thi bên trong
    3. Dùng regex loại bỏ các thẻ tự đống nguy hiểm còn sót lại
    4. Dùng thư viện bleach để bóc tách triệt để mọi thẻ HTML còn sót lại
    5. Cắt bỏ khoảng trắng thừa giữa hai đầu chuỗi
    """
    if not value:
        return ''

    # Bước 1: Xoá toàn bộ nội dung của các khối thẻ nguy hiểm
    value = _DANGEROUS_TAGS_RE.sub('', value)

    # Bước 2: Xoá các thẻ tự đóng nguy hiểm còn sót lại
    value = _DANGEROUS_SELF_CLOSING_RE.sub('', value)

    # Bước 3: Dùng bleach loại bỏ tất cả các thẻ HTML còn lại
    return bleach.clean(value, tags=[], attributes={}, strip=True).strip()

def sanitize_url(value: str) -> str:
    """
    Kiểm tra và chuẩn hoá URL, ngăn chặn các URL giả mạo hoặc chứa mã đọc
    
    Yêu cầu:
    - URL phải bắt đầu bằng 'http://' hoặc 'https://'
    - Ném ra lỗi ValueError nếu URL không hợp lệ 
    """
    if not value:
        return ''

    value = value.strip()

    # Chỉ chấp nhận giao thức web an toàn (http hoặc https)
    if not value.startswith(('http://', 'https://')):
        raise ValueError('URL phải bắt đầu bằng http:// hoặc https://')

    return value