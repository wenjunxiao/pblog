#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Web api."""

__author__="Wenjun Xiao"

import functools, re, logging
from http import redirect, found, seeother, httpctx

ctx = httpctx

REQ_GET = 'GET'
REQ_POST = 'POST'

RE_ROUTE = re.compile(r'(\:[a-zA-Z_]\w*)')
_RE_REG_ARGS = re.compile(r'(\<[a-zA-Z_]\w*)\>')

def request(path, method=REQ_GET):
    """A decorator that is used to register a view function for a given
    request URL rule."""
    def _decorator(func):
        if path and path[:1] == '^':
            def_args = _RE_REG_ARGS.findall(path)
        else:
            def_args = RE_ROUTE.findall(path)
        if func.func_code.co_argcount != len(def_args):
            raise TypeError(r"%s() takes %d arguments (%d given by decorator path)" % (
                    func.__name__, func.func_code.co_nlocals, len(def_args)))
        varnames = func.func_code.co_varnames
        for i, arg in enumerate(def_args):
            if arg[1:] != varnames[i]:
                raise TypeError(r"The name of args[%d] (%s) doesn't match with "
                    "the path given (%s)" % (i, varnames[i],arg[1:]))
        if hasattr(func, '__request_route__'):
            raise AttributeError(
                r"Function '%s' has set attr '%s', can't set again!" % 
                (func.__name__, '__request_route__'))
        func.__request_route__ = path
        func.__request_method__ = method
        return func
    return _decorator

def get(path):
    """A decorator that is used to register a view function  
    get-request URL rule."""
    return request(path, REQ_GET)

def post(path):
    """A decorator that is used to register a view function for a given
    post-request URL rule."""
    return request(path, REQ_POST)

class ModelAndView(object):
    """A template object with template name, model.

    >>> t = ModelAndView('index.html', {'title':'Index Page', 'content':'Hello world!'})
    >>> t.model['title']
    'Index Page'
    >>> t.model['content']
    'Hello world!'
    """

    def __init__(self, view_name, model):
        self.view = view_name
        if isinstance(model, dict):
            self.model = model
        else:
            raise ValueError('A dict expected with view.')

def view(view_name):
    """A decorator that is used to change result to a ModelAndView with given
     view and the result of  a view function result."""
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kw):
            return ModelAndView(view_name, func(*args, **kw))
        return _wrapper
    return _decorator

_RE_INTERCEPTOR = re.compile(r"^(\*?)([^\*\?]+)(\*?)$")
def interceptor(pattern):
    """A interceptor decorator."""
    def _decorator(func):
        if func.func_code.co_nlocals < 1:
            raise TypeError(r"Interceptor takes at least 1 arguments (%s() gives 0)" % \
                func.__name__)
        m = _RE_INTERCEPTOR.match(pattern)
        if m:
            re_list = ['^']
            if m.group(1):
                re_list.append('.+')
            re_list.append(re.escape(m.group(2)))
            if m.group(3):
                re_list.append('.+')
            else:
                re_list.append('.*')
            re_list.append('$')
            func.__interceptor__ = re.compile(''.join(re_list), re.IGNORECASE)
            func.__interceptor_pattern__ = pattern
            func.__match__ = func.__interceptor__.match
        else:
            raise ValueError('Invalid pattern definition in interceptor.')
        return func
    return _decorator

class JsonModel(object):

    def __init__(self, model, encoder=None):
        self.model = model
        self.encoder = encoder

def jsonbody(*args, **kwargs):
    encoder=None
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kw):
            try:
                return JsonModel(func(*args, **kw), encoder)
            except Exception as e:
                logging.exception('jsonbody:')
                return JsonModel(dict(error='internalerror', data=e.__class__.__name__,
                    message=e.message))
        return _wrapper
    if args:
        func = args[0]
        if hasattr(func, '__json_encoder__'):
            encoder = func.__json_encoder__
        return _decorator(func)
    else:
        encoder = kwargs.get('encoder', None)
        return _decorator


if __name__ == '__main__':
    import doctest
    doctest.testmod()
