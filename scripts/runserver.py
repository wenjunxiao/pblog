#!/usr/bin/env python
# -*- coding: utf-8 -*
"""Run pblog application for development."""

__author__="Wenjun Xiao"

import sys,os

sys.path.append('../')

from pblog import application, settings

settings.DEBUG = True
application.run(host='0.0.0.0',autoreload=True)
