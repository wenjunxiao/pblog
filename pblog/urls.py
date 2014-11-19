#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__="Wenjun Xiao"

import os, re, time, base64, hashlib, logging

import markdown2

from core.webapi import get, post, interceptor, ModelAndView, view, ctx, jsonbody, REQ_GET
from modules import User, Blog, Comment
from core.conf import settings
from apis import Page, api, APIError, APIPermissionError, APIValueError, APIResourceNotFoundError
from core.http import forbidden, seeother, notfound

_COOKIE_NAME = 'pblogsession'
_COOKIE_KEY = settings.session.secret
PROJECTS = Blog(id='projects', url='/projects/', category=u'开源项目')

def make_signed_cookie(id, password, max_age):
    # build cookie string by: id-expires-md5
    expires = str(int(time.time() + (max_age or 86400)))
    L = [id, expires, hashlib.md5('%s-%s-%s-%s' % (id, password, expires, _COOKIE_KEY)).hexdigest()]
    return '-'.join(L)

def parse_signed_cookie(cookie_str):
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        id, expires, md5 = L
        if int(expires) < time.time():
            return None
        user = User.get(id)
        if user is None:
            return None
        if md5 != hashlib.md5('%s-%s-%s-%s' % (id, user.password, expires, _COOKIE_KEY)).hexdigest():
            return None
        return user
    except:
        return None

def check_admin():
    user = ctx.request.user
    if user and user.admin:
        return
    raise APIPermissionError('No permission.')

@interceptor('/')
def user_interceptor(next, *args, **kwargs):
    logging.info('try to bind user from session cookie...')
    user = None
    cookie = ctx.request.cookies.get(_COOKIE_NAME)
    if cookie:
        logging.info('parse session cookie...')
        user = parse_signed_cookie(cookie)
        if user:
            logging.info('bind user <%s> to session...' % user.email)
    ctx.request.user = user
    return next(*args, **kwargs)

def _get_page_index():
    page_index = 1
    try:
        page_index = int(ctx.request.get('page', '1'))
    except ValueError:
        pass
    return page_index

def _get_blogs_by_page(**kwargs):
    total = Blog.count_all()
    page = Page(total, _get_page_index())
    blogs = Blog.find_by(order='created_at desc', offset=page.offset, limit=page.limit, **kwargs)
    return blogs, page

@view('index.html')
@get('/')
def index():
    blogs, page = _get_blogs_by_page()
    return dict(page=page, blogs=blogs, user=ctx.request.user)

@view('index.html')
@get('/category/:category')
def get_category(category):
    blogs, page = _get_blogs_by_page(category=category)
    return dict(page=page, blogs=blogs, user=ctx.request.user, category=category)

@view('blog.html')
@get('/blog/:blog_id')
def get_blog(blog_id):
    blog = Blog.get(blog_id)
    if blog is None:
        raise notfound()
    blog.read_count = blog.read_count + 1
    blog.update()
    blog.html_content = markdown2.markdown(blog.content)
    comments = Comment.find_by(order='created_at desc', limit=1000, blog_id=blog_id)
    return dict(blog=blog, comments=comments, user=ctx.request.user,category=blog.category)

@view('register.html')
@get('/register')
def register():
    return {}

@view('signin.html')
@get('/signin')
def signin():
    return {}

@jsonbody
@api
@post('/api/authenticate')
def api_authenticate():
    i = ctx.request.input(remember='')
    email = i.email.strip().lower()
    password = i.password
    remember = i.remember
    user = User.find_first(email=email)
    if user is None:
        raise APIError('auth:failed', 'email', 'Invalid email.')
    elif password != user.password:
        raise APIError('auth:failed', 'password', 'Invalid password.')
    max_age = 604800 if remember == 'true' else None
    cookie = make_signed_cookie(user.id, user.password, max_age)
    ctx.response.set_cookie(_COOKIE_NAME, cookie, max_age=max_age)
    user.password = '******'
    return user

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_MD5 = re.compile(r'^[0-9a-f]{32}$')

@jsonbody
@api
@post('/api/register')
def register_user():
    i = ctx.request.input(name='', email='', password='')
    name = i.name.strip()
    email = i.email.strip()
    password = i.password
    if not name:
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not password and not _RE_MD5.match(password):
        raise APIValueError('password')
    user = User.find_first(email=email)
    if user:
        raise APIError('register:failed', 'email', 'Email is already registed.')
    user = User(name=name, email=email, password=password,
        image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email).hexdigest())
    user.insert()
    cookie = make_signed_cookie(user.id, user.password, None)
    ctx.response.set_cookie(_COOKIE_NAME, cookie)
    return user

@get('/signout')
def signout():
    ctx.response.delete_cookie(_COOKIE_NAME)
    raise seeother('/')

@interceptor('/manage/')
def manage_interceptor(next, *args, **kwargs):
    user = ctx.request.user
    if user and user.admin:
        return next(*args, **kwargs)
    raise seeother('/signin')

@view('manage.html')
@get('/manage/')
def manage_index():
    return dict(user=ctx.request.user)

@view('manage_blog_list.html')
@get('/manage/blogs')
def manage_blog_list():
    return dict(page_index=_get_page_index(),user=ctx.request.user)

@view('/manage_blog_edit.html')
@get('/manage/blog/create')
def manage_blog_create():
    return dict(id=None, action='/api/blog/create', redirect='/manage/blogs',
        user=ctx.request.user)

@view('/manage_blog_edit.html')
@get('/manage/blog/edit/:blog_id')
def manage_blog_edit(blog_id):
    blog = Blog.get(blog_id)
    if blog is None:
        raise notfound()
    return dict(id=blog.id, action='/api/blog/%s/update' % blog.id, 
        redirect='/manage/blogs', user=ctx.request.user)

@view('manage_comment_list.html')
@get('/manage/comments')
def manage_comment_list():
    return dict(page_index=_get_page_index(),user=ctx.request.user)

@jsonbody
@api
@get('/api/blogs')
def api_blogs():
    format = ctx.request.get('format', '')
    blogs, page = _get_blogs_by_page()
    if format=='html':
        for blog in blogs:
            blog.content = markdown2.markdown(blog.content)
    return dict(blogs=blogs, page=page)

@jsonbody
@api
@get('/api/blog/:blog_id')
def api_get_blog(blog_id):
    blog = Blog.get(blog_id)
    if blog:
        return blog
    raise APIResourceNotFoundError('Blog')

@jsonbody
@api
@post('/api/blog/create')
def api_create_blog():
    check_admin()
    i = ctx.request.input(name='', summary='', content='')
    name = i.name.strip()
    summary = i.summary.strip()
    content = i.content.strip()
    if not name:
        raise APIValueError('name', 'name cannot be empty.')
    if not summary:
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content:
        raise APIValueError('content', 'content cannot be empty.')
    user = ctx.request.user
    blog = Blog(user_id=user.id, user_name=user.name, name=name, summary=summary, content=content)
    blog.insert()
    return blog

@jsonbody
@api
@post('/api/blog/:blog_id/update')
def api_update_blog(blog_id):
    check_admin()
    i = ctx.request.input(name='', summary='', content='')
    name = i.name.strip()
    summary = i.summary.strip()
    content = i.content.strip()
    if not name:
        raise APIValueError('name', 'name cannot be empty.')
    if not summary:
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content:
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog.get(blog_id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    blog.name = name
    blog.summary = summary
    blog.content = content
    blog.update()
    return blog

@jsonbody
@api
@post('/api/blog/:blog_id/delete')
def api_delete_blog(blog_id):
    check_admin()
    blog = Blog.get(blog_id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    blog.delete()
    return dict(id=blog_id)

@jsonbody
@api
@post('/api/blog/:blog_id/comment')
def api_comment_blog(blog_id):
    user = ctx.request.user
    if user is None:
        raise APIPermissionError('Need signin.')
    if blog_id != PROJECTS.id:
        blog = Blog.get(blog_id)
        if blog is None:
            raise APIResourceNotFoundError('Blog')
    else:
        blog = PROJECTS
    content = ctx.request.input(content='').content.strip()
    if not content:
        raise APIValueError('content')
    c = Comment(blog_id=blog_id, user_id=user.id, user_name=user.name, user_image=user.image, content=content)
    c.insert()
    return dict(comment=c)

@jsonbody
@api
@get('/api/blogs/top/:limit')
def api_blogs_top(limit):
    blogs = Blog.find_by(order='read_count desc', limit=limit);
    return dict(blogs=blogs)

@jsonbody
@api
@get('/api/categories')
def api_categories():
    categories = Blog.find_by(what='category, count(1) blog_count', group='category')
    return dict(categories=categories)

@jsonbody
@api
@get('/api/comments')
def api_comments():
    total = Comment.count_all()
    page = Page(total, _get_page_index())
    comments = Comment.find_by(order='created_at desc', offset=page.offset, limit=page.limit)
    return dict(comments=comments, page=page)

@jsonbody
@api
@post('/api/comment/:comment_id/delete')
def api_comments_delete(comment_id):
    check_admin()
    comment = Comment.get(comment_id)
    if comment is None:
        raise APIResourceNotFoundError('Comment')
    comment.delete()
    return dict(id=comment_id)

@jsonbody
@api
@get('/api/comments/top/:limit')
def api_comments_top(limit):
    comments = Comment.find_by(order='created_at desc', limit=limit)
    for comment in comments:
        if comment.blog_id == PROJECTS.id:
            comment.blog_url = PROJECTS.url
    return dict(comments=comments)

@jsonbody
@api
@get('/api/')
def api_multi_query():
    inputs = ctx.request.input()
    app = ctx.application
    rv = {}
    for k, v in inputs.items():
        data = app.internal_route(REQ_GET, '/api/%s' % k)
        rv.update(data)
    return rv

@view('projects.html')
@get('/projects/')
def get_projects():
    comments = Comment.find_by(order='created_at desc', limit=1000, blog_id=PROJECTS.id)
    return dict(user=ctx.request.user, comments=comments, blog_id=PROJECTS.id, 
        category=PROJECTS.category)

@view('manage_user_list.html')
@get('/manage/users')
def manage_user():
    return dict(page_index=_get_page_index(),user=ctx.request.user)

@jsonbody
@api
@get('/api/users')
def api_get_users():
    total = User.count_all()
    page = Page(total, _get_page_index())
    users = User.find_by(order='created_at desc', offset=page.offset, limit=page.limit)
    for u in users:
        u.password = '******'
    return dict(users=users, page=page)

@interceptor('/templates/')
def template_interceptor(next, *args, **kwargs):
    logging.debug('Check there is running in debug mode: %s' % settings.DEBUG)
    if settings.DEBUG:
        return next(*args, **kwargs)
    raise forbidden()

@get('^/templates/(?P<template>.*)$')
def test_template(template):
    logging.info("Show template: %s", template)
    return ModelAndView(template, {})
