#!/usr/bin/env python
# -*- coding: utf-8 -*
"""Pblog application entry."""

__author__="Wenjun Xiao"
__version__ = '0.0.1'

import logging.config; logging.basicConfig(level=logging.DEBUG)
import os; os.environ.setdefault('SETTINGS_MODULE', 'pblog.setting')

from .core.conf import settings

logging.config.fileConfig(settings.LOG_CONFIG)

from core.db import create_engine

create_engine(**settings.DATABASES.default)

from core.wsgi import WSGIApplication
application = WSGIApplication(os.path.dirname(os.path.abspath(__file__)))
