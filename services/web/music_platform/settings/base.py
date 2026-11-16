import os

from pathlib import Path
from decouple import config, Csv

# 1. Đường dẫn dự án và bảo mật cơ bản
BASE_DIR = Path(__file__).resolve().parent.parent.parent # trỏ về thư mục server/web

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', cast=bool)

# Header nhận diện giao thức HTTPS qua Reverse Proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'

# 2. ALLOWED HOSTS, CSRF và CORS
ALLOWED_HOSTS = list(
    config(
        'ALLOWED_HOSTS',
        cast=Csv()
    )
)

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = list(
    config(
        'CSRF_TRUSTED_ORIGINS',
        cast=Csv()
    )
)

# Frontend URL
FRONTEND_URL = config('FRONTEND_URL')

# CORS Configuration: Cho phép frontend gọi API mà không bị chặn
CORS_ALLOWED_ORIGINS = list(
    config(
        'CORS_ALLOWED_ORIGINS',
        cast=Csv()
    )
)

# Tự động tách nếu FRONTEND_URL có dấu phẩy và thêm vào CORS
if FRONTEND_URL:
    for url in [u.strip() for u in FRONTEND_URL.split(',') if u.strip()]:
        if url not in CORS_ALLOWED_ORIGINS:
            CORS_ALLOWED_ORIGINS.append(url)
            
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# 3. Danh sách ứng dụng
INSTALLED_APPS = [
    # Django Built-in Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Thư viện bên thứ ba
    'corsheaders',
    'anymail',
    'cloudinary',
    'cloudinary_storage',

    # Ứng dụng nội bộ
    'accounts',
    'music',
    'playlists',
    'artists',
    'social',
    'notifications',
    'search',
    'recommendations',
    'chat',
    'posts',
]

# 4. Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Phục vụ file tĩnh nén
    'corsheaders.middleware.CorsMiddleware',        # Đứng trước CommonMiddleware để xử lý CORS preflight
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom Middlewares (Đo performance và gom lỗi tập trung)
    # Lưu ý: Phải đảm bảo đường dẫn import đúng với vị trí file trong project
    'middlewares.logging_middleware.RequestLoggingMiddleware',
    'middlewares.error_middleware.GlobalErrorMiddleware',
]

ROOT_URLCONF = 'music_platform.urls'

# 5. Templates và Applications
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'music_platform.wsgi.application'

# 6. Database
db_name = config('DB_NAME', default=None)

if db_name:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': db_name,
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT'),
        }
    }
else:
    # Môi trường chạy test cục bộ không cần cài đặt Postgres
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db_test.sqlite3',
        }
    }

# 7. Redis và Channels
REDIS_URL = config('REDIS_URL', default=None)

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# 8. Kafka Message Broker
KAFKA_ENABLED = config('KAFKA_ENABLED', cast=bool)
KAFKA_BOOTSTRAP_SERVERS = config('KAFKA_BOOTSTRAP_SERVERS')

# 9. Định dạng và thời gian
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 10. File tĩnh và file media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_DIR = BASE_DIR / 'static'
if STATIC_DIR.exists():
    STATICFILES_DIRS = [STATIC_DIR]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cấu hình Cloudinary cho Media storage
CLOUDINARY_STORAGE = {
    'PREFIX': config('CLOUDINARY_PREFIX'),
}
cloudinary_url = config('CLOUDINARY_URL', default=None)
if cloudinary_url:
    os.environ['CLOUDINARY_URL'] = cloudinary_url
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage" if cloudinary_url else "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Khi DEBUG=False dùng WhiteNoise nén tĩnh; Khi DEBUG=True dùng Storage chuẩn tránh lỗi cache manifest
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if not DEBUG else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# 11. Bảo mật Session và CSRF COOKIE
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', cast=int)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = 'sessionid'

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_NAME = 'csrftoken'

# 12. Email và Rate Limit
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
ANYMAIL = {"RESEND_API_KEY": config("RESEND_API_KEY")}
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')
RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', cast=bool)

# 13. Logging (Đồng bộ với các custom middleware)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'middlewares': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
