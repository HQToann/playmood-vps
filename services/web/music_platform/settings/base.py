import os
from pathlib import Path
from decouple import config

#lấy đường dẫn hiện tại services/web/music_platform/settings/base.py (sâu 3 cấp)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

#SECRET_KEY đọc từ biến môi trường
SECRET_KEY = config('SECRET_KEY')

#trỏ về model User trong accounts
AUTH_USER_MODEL = 'accounts.User'

#khai báo các app
INSTALLED_APPS = [
    #các app mặc định
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

#các lớp trung gian xử lý các request
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Phải nằm trên cùng để xử lý CORS
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Tối ưu phục vụ file tĩnh
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

#urls quản lý chính của dự án
ROOT_URLCONF = 'music_platform.urls'

#cấu hình hệ thống template cho web
TEMPLATES = [
    {   
        #chỉnh định django sử dụng lõi mặc định
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')], #nơi chứa các file HTML
        'APP_DIRS': True, #choe phép django tìm kiếm template trong từng app
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ]
        }
    }
]

#cầu nối web server Gateway interface
WSGI_APPLICATION = 'music_platform.wsgi.application'

#kiểm tra độ mạnh của mật khẩu
# AUTH_PASSWORD_VALIDATORS = [
#     {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
#     {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
#     {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
#     {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
# ]

LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

#cấu hình css của web
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

#cấu hình cloud
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': config('CLOUDINARY_CLOUD_NAME', default=''),
    'API_KEY': config('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': config('CLOUDINARY_API_SECRET', default=''),
}
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
