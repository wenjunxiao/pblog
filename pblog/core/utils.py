#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""General utilities.
This module implements various utilities for WSGI applications."""

__author__="Wenjun Xiao"

import urllib, operator

def load_module(module_name):
    last_dot = module_name.rfind('.')
    if last_dot==(-1):
        return __import__(module_name, globals(), locals())
    from_module = module_name[:last_dot]
    import_module = module_name[last_dot+1:]
    m = __import__(from_module, globals(), locals(), [import_module])
    return getattr(m, import_module)

def to_unicode(s, encoding='utf-8'):
    r"""Convert to unicode.

    >>> to_unicode('\xe6\xb1\x89\xe5\xad\x97')
    u'\u6c49\u5b57'
    """
    return s.decode(encoding)

def to_str(s):
    r"""Convert to str.

    >>> to_str('abc123')
    'abc123'
    >>> to_str(u'\u6c49\u5b57')
    '\xe6\xb1\x89\xe5\xad\x97'
    >>> to_str(-123)
    '-123'
    """
    if isinstance(s, str):
        return s
    if isinstance(s, unicode):
        return s.encode('utf-8')
    return str(s)

def quote(s, encoding='utf-8'):
    r"""Quote url as a str.

    >>> quote('http://www.example.com/?test=1+')
    'http%3A//www.example.com/%3Ftest%3D1%2B'
    >>> quote('Hello world!')
    'Hello%20world%21'
    """
    if isinstance(s, unicode):
        s = s.encode(encoding)
    return urllib.quote(s)

def unquote(s, encoding='utf-8'):
    r"""Unquote url as unicode.

    >>> unquote('http%3A//www.example.com/%3Ftest%3D1%2B')
    u'http://www.example.com/?test=1+'
    """
    return urllib.unquote(s).decode(encoding)

def escape(s):
    return s.replace('&', '&amp;').replace('<', '&lt;') \
        .replace('>', '&gt;').replace('"', "&quot;")

class Dict(dict):
    r"""Extend dict to support access as d.x style.
    
    For example::
    >>> d1 = Dict()
    >>> d1['x'] = 1
    >>> d1.x
    1
    >>> d1.y = 2
    >>> d1['y']
    2
    >>> d2 = Dict(x=1, y='2', z=3)
    >>> d2.y
    '2'
    >>> d3 = Dict()
    >>> d3.x
    Traceback (most recent call last):
      ...
    AttributeError: 'Dict' object has no attribute 'x'
    >>> d3['x']
    Traceback (most recent call last):
      ...
    KeyError: 'x'
    """

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

class CaseInsensitiveDict(Dict):
    """Case insensitive dict.

    >>> d = CaseInsensitiveDict()
    >>> d = CaseInsensitiveDict(a=1, b=2)
    >>> d.A
    1
    >>> d.update({'A': 3})
    >>> d.a
    3
    >>> d.update(B=5)
    >>> d.b
    5
    >>> d.setdefault('B',6)
    5
    >>> d.setdefault('C', 7)
    7
    >>> d.pop('c', 8)
    7
    """
    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(((k.lower(), v) for k, v in kw.items()))
        for k, v in zip(names, values):
            self[k.lower()] = v

    def __getitem__(self, key):
        return super(CaseInsensitiveDict, self).__getitem__(key.lower())

    def __setitem__(self, key, value):
        super(CaseInsensitiveDict, self).__setitem__(key.lower(), value)

    def get(self, key, default=None):
        return super(CaseInsensitiveDict, self).get(key.lower())

    def update(self, *args, **kwargs):
        d = dict()
        for arg in args:
            for k,v in arg.items():
                d[k.lower()] = v
        for k, v in kwargs.items():
            d[k.lower()] = v
        super(CaseInsensitiveDict, self).update(d)

    def setdefault(self, key, default=None):
        return super(CaseInsensitiveDict, self).setdefault(key.lower(), default)

    def pop(self, key, *args):
        return super(CaseInsensitiveDict, self).pop(key.lower(), *args)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
