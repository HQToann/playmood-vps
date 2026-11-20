from .base import *


# Chế độ debug khi chạy local
DEBUG = True

# Cho phép mọi host
ALLOWED_HOSTS = ['*']

# Cookie không bắt buộc HTTPS ở local
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
