#!/usr/bin/env python
# -*- coding: utf-8 -*

__author__="Wenjun Xiao"

"""WSGI application entry."""

import logging; logging.basicConfig(level=logging.INFO)

from core.wsgi import WSGIApplication

application = WSGIApplication(__name__)

if __name__ == "__main__":
    application.run(host='0.0.0.0', port=5100)
