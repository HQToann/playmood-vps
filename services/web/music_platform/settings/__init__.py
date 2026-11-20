from decouple import config

# 1. Đọc và chuẩn hoá giá trị môi trường
env = config('DJANGO_ENV', default='').strip().lower()

# 2. Fallback dựa vào biến DEBUG nếu chưa khai báo DJANGO_ENV
if not env:
    is_debug = config('DEBUG', default=False, cast=bool)
    env = 'dev' if is_debug else 'prod'

# 3. Phân nhánh rõ ràng, an toàn
if env in ('prod', 'production'):
    from .prod import *
elif env in ('dev', 'development', 'local'):
    from .dev import *
elif env in ('test', 'testing'):
    # Hỗ trợ thêm môi trường test
    from .dev import *
else:
    raise ValueError(
        f"Môi trường DJANGO_ENV='{env} không hợp lệ! "
        "Vui lòng chỉ sử dụng 'dev', 'prod' hoặc 'test'."
    )