"""WSGI configuration is used only for the production environment."""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

MODULE_SCAN = ('pblog.urls',)

LOG_CONFIG = os.path.join(BASE_DIR, "conf/logging.conf")

TEMPLATE_ENGINE = 'pblog.core.templating.jinja2_engine'

DATABASES = {
    'default': {
        'ENGINE': 'pblog.core.db.mysql',
        'DATABASE': 'pblog',
        'USER': 'x-pblog',
        'PASSWORD': 'x-pblog',
        'HOST': '127.0.0.1',
        'PORT': 3306,
    }
}

SESSION = {
    "secret": "PrOmIsSiNg"
}