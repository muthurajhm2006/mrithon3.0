"""
Django settings for manual_assistant project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-manufacturing-rag-assistant-key-2026')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    
    # Local apps
    'accounts.apps.AccountsConfig',
    'machines.apps.MachinesConfig',
    'manual_manager.apps.ManualManagerConfig',
    'rag_engine.apps.RagEngineConfig',
    'chat.apps.ChatConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'manual_assistant.urls'

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
                'accounts.context_processors.user_role_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'manual_assistant.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 4},  # Beginner friendly for demo passwords
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard_redirect'
LOGOUT_REDIRECT_URL = 'login'

# RAG & LLM Configuration
RAG_CONFIG = {
    'LLM_PROVIDER': os.getenv('LLM_PROVIDER', 'gemini'),  # 'gemini', 'openai', or 'development'
    'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY', os.getenv('GOOGLE_API_KEY', '')),
    'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
    'GEMINI_MODEL': os.getenv('GEMINI_MODEL', 'gemini-3.5-flash'),
    'OPENAI_MODEL': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
    'EMBEDDING_MODEL': os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2'),
    'VECTOR_STORE_DIR': BASE_DIR / 'vector_store_data',
    'TOP_K': int(os.getenv('RAG_TOP_K', '4')),
    'TIMEOUT': int(os.getenv('LLM_TIMEOUT', '25')),
}
