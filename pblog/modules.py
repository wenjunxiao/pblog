#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from core.orm import *
from core.db import next_id

class User(Model):
    __table__='users'

    id = StringField(primary_key=True, default=next_id, max_length=50)
    email = StringField(updatable=False, max_length=50)
    password = StringField(max_length=50)
    admin = BooleanField()
    name = StringField(max_length=50)
    image = StringField(max_length=500)
    created_at = FloatField(updatable=False, default=time.time)

class Blog(Model):
    __table__ = 'blogs'

    id = StringField(primary_key=True, default=next_id, max_length=50)
    user_id = StringField(updatable=False, max_length=50)
    user_name = StringField(max_length=50)
    user_image = StringField(max_length=500)
    name = StringField(max_length=50)
    summary = StringField(max_length=200)
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)
    read_count = IntegerField(default=0)
    category = StringField(max_length=50)
    tags = StringField(max_length=50)

class Comment(Model):
    __table__ = 'comments'

    id = StringField(primary_key=True, default=next_id, max_length=50)
    blog_id = StringField(updatable=False, max_length=50)
    user_id = StringField(updatable=False, max_length=50)
    user_name = StringField(max_length=50)
    user_image = StringField(max_length=50)
    content = TextField()
    created_at = FloatField(updatable=False, default=time.time)
