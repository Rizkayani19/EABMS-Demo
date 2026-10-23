import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DEPLOYMENT_ENV = os.environ.get('DJANGO_ENV', 'development').strip().lower()
IS_PRODUCTION = DEPLOYMENT_ENV in ('production', 'prod')

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '').strip()
if IS_PRODUCTION and not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set in production.')
if not SECRET_KEY:
    SECRET_KEY = 'abms-development-only-insecure-key'

DEBUG = os.environ.get('DJANGO_DEBUG', 'False' if IS_PRODUCTION else 'True').lower() in ('true', '1', 'yes')

_allowed_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '').strip()
ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(',') if host.strip()]
if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must be set in production.')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'masters.apps.MastersConfig',
    'accounts.apps.AccountsConfig',
    'reports.apps.ReportsConfig',
    'django.contrib.humanize',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AccountContextMiddleware',
]

ROOT_URLCONF = 'abms_config.urls'

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
                'core.context_processors.abms_context',
            ],
            'builtins': [
                'django.contrib.humanize.templatetags.humanize',
                'core.templatetags.abms_filters',
            ],
        },
    },
]

USE_L10N = False
DATE_FORMAT = 'd-m-Y'
DATETIME_FORMAT = 'd-m-Y H:i'
SHORT_DATE_FORMAT = 'd-m-Y'

WSGI_APPLICATION = 'abms_config.wsgi.application'

# Production defaults to PostgreSQL. Development falls back to SQLite when no
# database is configured, so a fresh clone runs without any setup.
DB_ENGINE = os.environ.get('DB_ENGINE', 'postgresql' if IS_PRODUCTION else 'sqlite3').strip().lower()

FUND_DB_MAP = {
    'NGL': 'eabms_ngl',
    'EWF': 'eabms_ewf',
    'CPF': 'eabms_cpf',
}
FUND_NAMES = {
    'NGL': 'NexGen Holdings Ltd.',
    'EWF': 'Employee Welfare Fund',
    'CPF': 'Corporate Provident Fund',
}

_raw_fund = os.environ.get('ABMS_FUND', '').strip().upper()
if not _raw_fund:
    import sys
    _args_str = ' '.join(sys.argv)
    if ':8022' in _args_str or ' 8022' in _args_str:
        _raw_fund = 'CPF'
    elif ':8021' in _args_str or ' 8021' in _args_str:
        _raw_fund = 'EWF'
    elif ':8020' in _args_str or ' 8020' in _args_str:
        _raw_fund = 'NGL'
    else:
        _raw_fund = 'NGL'

if _raw_fund == 'EWF':
    ABMS_FUND = 'EWF'
elif _raw_fund == 'CPF':
    ABMS_FUND = 'CPF'
else:
    ABMS_FUND = 'NGL'

ABMS_FUND_NAME = FUND_NAMES.get(ABMS_FUND, 'NexGen Holdings Ltd.')
DEFAULT_DB_NAME = FUND_DB_MAP.get(ABMS_FUND, 'eabms_ngl')

if DB_ENGINE in ('postgresql', 'postgres', 'psycopg2'):
    DB_NAME = os.environ.get('DB_NAME', DEFAULT_DB_NAME)
    DB_USER = os.environ.get('DB_USER', 'postgres')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '').strip()
    if IS_PRODUCTION and not DB_PASSWORD:
        raise ImproperlyConfigured('DB_PASSWORD must be set for production PostgreSQL.')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'abms_foundation.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 6},
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:home'
LOGOUT_REDIRECT_URL = 'accounts:login'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 43200  # 12 hours max

ABMS_SYSTEM_NAME = 'Enterprise Accounts & Business Management System (EABMS)'
ABMS_DEFAULT_ACCOUNT_CODE = 'NGL'
ABMS_DEFAULT_FY_CODE = '2026-27'
ABMS_CURRENCY_SYMBOL = os.environ.get('ABMS_CURRENCY_SYMBOL', 'Rs').strip() or 'Rs'

if IS_PRODUCTION:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False
