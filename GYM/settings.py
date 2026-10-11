"""
Django settings for GYM project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- ROBUST ENV LOADING ---
try:
    from dotenv import load_dotenv
    # Explicitly point to the .env file in the BASE_DIR
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    # If python-dotenv is not installed, it will fall back to system env variables
    pass

# Quick-start development settings - unsuitable for production
_INSECURE_KEY = 'django-insecure-q_2uz@czn8zn!aks2)zxc3v4z28h4=3&ge1e6ex5afr&^e#-t3'
SECRET_KEY = os.environ.get('SECRET_KEY', _INSECURE_KEY)
if SECRET_KEY == _INSECURE_KEY:
    import warnings
    warnings.warn(
        "\n⚠️  SECRET_KEY is using the insecure default. Set a strong SECRET_KEY in your .env file before deploying to production.",
        stacklevel=2,
    )
DEBUG = os.environ.get('DEBUG', 'True').lower() in ('true', '1', 'yes')
BASE_URL = os.environ.get('BASE_URL', 'https://fitstack.nextgenapplication.com')

# Safely split hosts and origins (removes accidental spaces)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'OneX-Fitness.com,fitstack.nextgenapplication.com,127.0.0.1,localhost').split(',') if h.strip()]
for default_host in ['localhost', '127.0.0.1', 'testserver']:
    if default_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(default_host)
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'https://OneX-Fitness.com,https://fitstack.nextgenapplication.com,https://fitness.nextgenapplication.com').split(',')

# HTTPS Security - Conditional based on DEBUG
if DEBUG:
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    X_FRAME_OPTIONS = "SAMEORIGIN"
else:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 2592000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = False
SESSION_COOKIE_AGE = 7200
SESSION_SAVE_EVERY_REQUEST = True

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'ckeditor',
    'apps.dashboard',
    'apps.members',
    'apps.enquiry',
    'apps.trainers',
    'apps.management',
    'apps.billing',
    'apps.attendance',
    'apps.expenses',
    'apps.settings',
    'apps.superadmin',
    'apps.business_report',
    'apps.events',
    'apps.inventory',
    'apps.login',
    'apps.whatsapp',
    'apps.website',
    'apps.member_portal',
    'apps.trainer_portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'GYM.session_middleware.SessionExpiredMiddleware',   # ← redirect on session expiry
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'GYM.tenant_middleware.TenantMiddleware',
    'apps.login.middleware.PasswordResetMiddleware',
]

ROOT_URLCONF = 'GYM.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.superadmin.context_processors.gym_details',
                'apps.settings.context_processors.payment_settings_context',
                  'apps.login.context_processors.registration_credentials_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'GYM.wsgi.application'

db_engine = os.environ.get('DB_ENGINE')
db_password = os.environ.get('DB_PASSWORD')
db_user = os.environ.get('DB_USER')

if db_engine:
    DATABASES = {
        'default': {
            'ENGINE': db_engine,
            'NAME': os.environ.get('DB_NAME', 'gymdb'),
            'USER': db_user or 'gymuser',
            'PASSWORD': db_password or '',
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
elif db_password or db_user:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'gymdb'),
            'USER': db_user or 'gymuser',
            'PASSWORD': db_password or '',
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# ============ WhatsApp & Twilio Configuration ============
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')
TWILIO_CONTENT_SID = os.environ.get('TWILIO_CONTENT_SID', '')
TWILIO_MEMBERSHIP_ASSIGN_SID = os.environ.get('TWILIO_MEMBERSHIP_ASSIGN_SID', '')
TWILIO_MEMBERSHIP_EXPIRED_SID = os.environ.get('TWILIO_MEMBERSHIP_EXPIRED_SID', '')
TWILIO_MEMBERSHIP_EXPIRING_SOON_SID = os.environ.get('TWILIO_MEMBERSHIP_EXPIRING_SOON_SID', '')
TWILIO_BIRTHDAY_WISHES_SID = os.environ.get('TWILIO_BIRTHDAY_WISHES_SID', '')
TWILIO_DUE_PAYMENT_SID = os.environ.get('TWILIO_DUE_PAYMENT_SID', '')
TWILIO_DUE_FOLLOW_UP_SID = os.environ.get('TWILIO_DUE_FOLLOW_UP_SID', '') # Due follow-up date reminder


STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

CKEDITOR_BASEPATH = "/static/ckeditor/ckeditor/"
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
ITEMS_PER_PAGE = 15
LOGOUT_REDIRECT_URL = '/'

# ============ LOGGING ============
LOG_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# ── Authentication Redirects ──────────────────────────────────────────────────
# Django's default is /accounts/login/ which doesn't exist in this project.
# Expired sessions will now redirect to the correct login page.
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'},
        'simple': {'format': '{levelname} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
        'whatsapp_file': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOG_DIR, 'whatsapp.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'level': 'DEBUG',
        },
        'apps_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'apps.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 3,
            'level': 'WARNING',
        },
        'errors_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(LOG_DIR, 'errors.log'),
            'formatter': 'verbose',
            'encoding': 'utf-8',
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 3,
            'level': 'ERROR',
        },
    },
    'loggers': {
        'apps': {
            'handlers': ['console', 'apps_file', 'errors_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps.whatsapp': {
            'handlers': ['console', 'whatsapp_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {'handlers': ['console', 'errors_file'], 'level': 'WARNING'},
        'django.request': {'handlers': ['console', 'errors_file'], 'level': 'ERROR', 'propagate': False},
    },
}