"""
Cấu hình Django cho dự án Dashboard giám sát Wi-Fi.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Đường dẫn gốc của dự án
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

# Khóa bí mật cho môi trường phát triển
SECRET_KEY = 'django-insecure-wifimon-dashboard-dev-key-2024'

# Chế độ debug - chỉ dùng trong phát triển
DEBUG = True

# Cho phép tất cả host trong môi trường phát triển
ALLOWED_HOSTS = ['*']

# Các ứng dụng đã cài đặt
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'monitor',
]

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Cấu hình URL gốc
ROOT_URLCONF = 'dashboard.urls'

# Cấu hình template
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

# Cấu hình WSGI
WSGI_APPLICATION = 'dashboard.wsgi.application'

# PostgreSQL URL dùng chung với tiến trình WifiMon.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Thiếu DATABASE_URL trong file .env.")
DATABASES_CONFIG = dj_database_url.parse(DATABASE_URL, conn_max_age=60)
schema_option = DATABASES_CONFIG.get("OPTIONS", {}).pop("schema", None)
if schema_option not in (None, "public"):
    raise RuntimeError(
        "DATABASE_URL chỉ hỗ trợ schema=public; cấu hình schema khác bằng search_path."
    )
if DATABASES_CONFIG.get("HOST") == "localhost":
    DATABASES_CONFIG["HOST"] = "127.0.0.1"
DATABASES = {
    "default": DATABASES_CONFIG,
}

# Xác thực mật khẩu
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Cấu hình ngôn ngữ và múi giờ
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# Cấu hình file tĩnh
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'monitor' / 'static',
]

# Khóa chính mặc định
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
