#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""HTTP status and objects."""

__author__="Wenjun Xiao"

import threading, urllib, re, logging, cgi, datetime
from utils import to_str, escape, to_unicode, quote, unquote, Dict

ctx = httpctx = threading.local()

HTTP_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method not Allowed',
    406: 'Not acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}

_RE_HTTP_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')

_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',
)

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-By', 'promissing/1.0')

class HTTPError(Exception):
    """Basic class for all HTTP exceptions.

    >>> class NotFound(HTTPError):
    ...     code = 404
    >>> e = NotFound()
    >>> e.code
    404
    >>> e.name
    'Not Found'
    >>> e.status
    '404 Not Found'
    """
    code = None

    def __init__(self, code = None, message = None):
        if code is not None:
            self.code = code
        self._status = '%d %s' % (self.code, self.name)
        self._message = message

    @property
    def name(self):
        return HTTP_STATUSES.get(self.code, 'Unknown Error')

    @property
    def status(self):
        return self._status

    @property
    def headers(self, environ=None):
        return [('Content-Type', 'text/html')]

    def get_content(self):
        return u'<p>%s</p>' % escape(self.message or self.status)

    def get_body(self):
        return (
            u'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
            u'<html>\n<title>%(code)s %(name)s</title>\n<body>\n'
            u'<h1>%(name)s</h1>\n'
            u'%(description)s\n'
            u'</body></html>'
        ) % {
            'code':         self.code,
            'name':         escape(self.name),
            'description':  self.get_content()
        }

    def __call__(self, environ, start_response):
        response = ctx.response
        response.content = self.get_body()
        response.status = self.status
        for k, v in self.headers:
            response.set_header(k, v)
        return response(environ, start_response)

    def __str__(self):
        return self._status

    __repr__ = __str__


class BadRequest(HTTPError):
    """ 400 Bad Request.
    
    Raise if the browser sends something to the application that the application
    or server cannot handle.

    >>> raise BadRequest()
    Traceback (most recent call last):
      ...
    BadRequest: 400 Bad Request
    """
    code = 400

badrequest = BadRequest

class Unauthorized(HTTPError):
    """401 Unauthorized
    
    Raise if the user is not authorized.

    >>> raise Unauthorized()
    Traceback (most recent call last):
      ...
    Unauthorized: 401 Unauthorized
    """
    code = 401

unauthorized = Unauthorized

class Forbidden(HTTPError):
    """403 Forbidden

    Raise if the user doesn't have the permission for the request resource.
    but was authenticated.

    >>> raise Forbidden()
    Traceback (most recent call last):
      ...
    Forbidden: 403 Forbidden
    """
    code = 403

forbidden = Forbidden

class NotFound(HTTPError):
    """404 Not Found

    Raise if a resource doesn't exist and never existed.

    >>> raise NotFound()
    Traceback (most recent call last):
      ...
    NotFound: 404 Not Found
    """
    code = 404

notfound = NotFound

class Conflict(HTTPError):
    """409 Conflict

    Raise to signal that a request cannot be completed because it conflicts 
    with the current state on the server.

    >>> raise Conflict()
    Traceback (most recent call last):
      ...
    Conflict: 409 Conflict
    """
    code = 409

conflict = Conflict

class InternalServerError(HTTPError):
    """500 Internal Server Error

    Raise if an internal server error occurred. This is a goog fallback if an
    unknown error occurred in the dispatcher.

    >>> raise InternalServerError()
    Traceback (most recent call last):
      ...
    InternalServerError: 500 Internal Server Error
    """
    def __init__(self, message = None):
        super(InternalServerError, self).__init__(500, message)

class Redirect(HTTPError):
    """A '301 Moved Permanently' direct.
    
    >>> raise Redirect('http://www.example.com/')
    Traceback (most recent call last):
      ...
    Redirect: 301 Moved Permanently, http://www.example.com/
    """
    code = 301

    def __init__(self, location):
        super(Redirect, self).__init__()
        self.location = location

    @property
    def headers(self, environ=None):
        return [
            ('Content-Type', 'text/html'),
            ('Location', self.location)
        ]

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__

redirect = Redirect

class Found(Redirect):
    """A `302 Found` redirect.

    >>> raise Found('http://www.example.com/')
    Traceback (most recent call last):
      ...
    Found: 302 Found, http://www.example.com/
    """
    code = 302

found = Found

class SeeOther(Redirect):
    """A `303 See Other` redirect.

    >>> raise SeeOther('http://www.example.com/')
    Traceback (most recent call last):
      ...
    SeeOther: 303 See Other, http://www.example.com/
    """
    code = 303

seeother = SeeOther

class NotModified(Redirect):
    """A `304 Not Modified` status.
    
    >>> raise NotModified('http://www.example.com/')
    Traceback (most recent call last):
      ...
    NotModified: 304 Not Modified, http://www.example.com/
    """
    code = 304

notmodified = NotModified

class TemporaryRedirect(Redirect):
    """A `307 Temporary Redirect` redirect.
    
    >>> raise TemporaryRedirect('http://www.example.com/')
    Traceback (most recent call last):
      ...
    TemporaryRedirect: 307 Temporary Redirect, http://www.example.com/
    """
    code = 307

tempredirect = TemporaryRedirect

class MultipartFile(object):

    def __init__(self, storage):
        self.filename = to_unicode(storage.filename)
        self.file = storage.file

class Request(object):
    """Request object for obtaining all http request information."""

    def __init__(self, environ):
        self._environ = environ

    @property
    def method(self):
        '''Get request method. The valid returned values are 'GET', 'POST', 'HEAD'.'''
        return self._environ['REQUEST_METHOD']

    @property
    def path_info(self):
        '''Get request path as str.'''
        return to_unicode(urllib.unquote(self._environ.get('PATH_INFO', '')))

    @property
    def query_string(self):
        return self._environ.get('QUERY_STRING', '')

    def _parse_input(self):
        def _convert(item):
            if isinstance(item, list):
                return [to_unicode(i.value) for i in item]
            if item.filename:
                return MultipartFile(item)
            return to_unicode(item.value)
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        '''
        Get raw input as dict containing values as unicode, list or MultipartFile.
        '''
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, key):
        '''
        Get input parameter value.
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[0]
        return r

    def get(self, key, default=None):
        '''
        The same as request[key], but return default value if key is not found.
        '''
        r = self._get_raw_input().get(key, default)
        if isinstance(r, list):
            return r[0]
        return r

    def gets(self, key):
        '''
        Get multiple values for specified key.
        '''
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]
        return [r]

    def input(self, **kw):
        '''
        Get input as dict from request, fill dict using provided default value if key not exist.
        '''
        copy = Dict(**kw)
        raw = self._get_raw_input()
        for k, v in raw.iteritems():
            copy[k] = v[0] if isinstance(v, list) else v
        return copy

    def get_body(self):
        '''
        Get raw data from HTTP POST and return as str.

        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
        >>> r.get_body()
        '<xml><raw/>'
        '''
        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        '''
        Get remote addr. Return '0.0.0.0' if cannot get remote_addr.

        >>> r = Request({'REMOTE_ADDR': '192.168.0.100'})
        >>> r.remote_addr
        '192.168.0.100'
        '''
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        '''
        Get raw document_root as str. Return '' if no document_root.

        >>> r = Request({'DOCUMENT_ROOT': '/srv/path/to/doc'})
        >>> r.document_root
        '/srv/path/to/doc'
        '''
        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def host(self):
        '''
        Get request host as str. Default to '' if cannot get host..

        >>> r = Request({'HTTP_HOST': 'localhost:8080'})
        >>> r.host
        'localhost:8080'
        '''
        return self._environ.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            hdrs = {}
            for k, v in self._environ.iteritems():
                if k.startswith('HTTP_'):
                    # convert 'HTTP_ACCEPT_ENCODING' to 'ACCEPT-ENCODING'
                    hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
            self._headers = hdrs
        return self._headers

    @property
    def headers(self):
        '''
        Get all HTTP headers with key as str and value as unicode. The header names are 'XXX-XXX' uppercase.
        '''
        return dict(**self._get_headers())

    def header(self, header, default=None):
        '''
        Get header from request as unicode, return None if not exist, or default if specified. 
        The header name is case-insensitive such as 'USER-AGENT' or u'content-Type'.
        '''
        return self._get_headers().get(header.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    pos = c.find('=')
                    if pos>0:
                        cookies[c[:pos].strip()] = unquote(c[pos+1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        '''
        Return all cookies as dict. The cookie name is str and values is unicode.
        '''
        return Dict(**self._get_cookies())

    def cookie(self, name, default=None):
        '''
        Return specified cookie value as unicode. Default to None if cookie not exists.
        '''
        return self._get_cookies().get(name, default)

_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')
_TIMEDELTA_ZERO = datetime.timedelta(0)

class UTC(datetime.tzinfo):
    """
    A UTC tzinfo object.

    >>> tz0 = UTC('+00:00')
    >>> tz0.tzname(None)
    'UTC+00:00'
    >>> tz8 = UTC('+8:00')
    >>> tz8.tzname(None)
    'UTC+8:00'
    >>> tz7 = UTC('+7:30')
    >>> tz7.tzname(None)
    'UTC+7:30'
    >>> tz5 = UTC('-05:30')
    >>> tz5.tzname(None)
    'UTC-05:30'
    >>> from datetime import datetime
    >>> u = datetime.utcnow().replace(tzinfo=tz0)
    >>> l1 = u.astimezone(tz8)
    >>> l2 = u.replace(tzinfo=tz8)
    >>> d1 = u - l1
    >>> d2 = u - l2
    >>> d1.seconds
    0
    >>> d2.seconds
    28800
    """

    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1) == '-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-m)
            self._utcoffset = datetime.timedelta(hours=h,minutes=m)
            self._tzname = 'UTC%s' % utc
        else:
            raise ValueError('Bad utc time zone')

    def utcoffset(self, dt):
        return self._utcoffset

    def dst(self, dt):
        return _TIMEDELTA_ZERO

    def tzname(self, dt):
        return self._tzname

    def __str__(self):
        return 'UTC tzinfo object(%s)' % self._tzname

    __repr__ = __str__


UTC_0 = UTC('+00:00')

class Response(object):

    def __init__(self, content = [], status = None, headers = None):
        self._content = content
        if status is None:
            self._status = '200 OK'
        else:
            self._status = status
        if headers is None:
            self._headers = {'CONTENT-TYPE': 'text/html; charset=utf-8'}
        else:
            self._headers = dict(headers)

    @property
    def headers(self):
        '''
        Return response headers as [(key1, value1), (key2, value2)...] including cookies.
        '''
        L = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.itervalues():
                L.append(('Set-Cookie', v))
        L.append(_HEADER_X_POWERED_BY)
        return L

    def header(self, name):
        '''
        Get header by name, case-insensitive.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.header('CONTENT-type')
        'text/html; charset=utf-8'
        >>> r.header('X-Powered-By')
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    def unset_header(self, name):
        '''
        Unset header by name and value.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.unset_header('CONTENT-type')
        >>> r.header('content-type')
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        '''
        Set header by name and value.

        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.set_header('CONTENT-type', 'image/png')
        >>> r.header('content-TYPE')
        'image/png'
        '''
        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = to_str(value)

    @property
    def content_type(self):
        '''
        Get content type from response. This is a shortcut for header('Content-Type').

        >>> r = Response()
        >>> r.content_type
        'text/html; charset=utf-8'
        >>> r.content_type = 'application/json'
        >>> r.content_type
        'application/json'
        '''
        return self.header('CONTENT-TYPE')

    @content_type.setter
    def content_type(self, value):
        '''
        Set content type for response. This is a shortcut for set_header('Content-Type', value).
        '''
        if value:
            self.set_header('CONTENT-TYPE', value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        '''
        Get content length. Return None if not set.

        >>> r = Response()
        >>> r.content_length
        >>> r.content_length = 100
        >>> r.content_length
        '100'
        '''
        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self, value):
        '''
        Set content length, the value can be int or str.

        >>> r = Response()
        >>> r.content_length = '1024'
        >>> r.content_length
        '1024'
        >>> r.content_length = 1024 * 8
        >>> r.content_length
        '8192'
        '''
        self.set_header('CONTENT-LENGTH', str(value))

    @property
    def status_code(self):
        '''
        Get response status code as int.

        >>> r = Response()
        >>> r.status_code
        200
        >>> r.status = 404
        >>> r.status_code
        404
        >>> r.status = '500 Internal Error'
        >>> r.status_code
        500
        '''
        return int(self._status[:3])

    @property
    def status(self):
        '''
        Get response status. Default to '200 OK'.

        >>> r = Response()
        >>> r.status
        '200 OK'
        >>> r.status = 404
        >>> r.status
        '404 Not Found'
        >>> r.status = '500 Oh My God'
        >>> r.status
        '500 Oh My God'
        '''
        return self._status

    @status.setter
    def status(self, value):
        '''
        Set response status as int or str.

        >>> r = Response()
        >>> r.status = 404
        >>> r.status
        '404 Not Found'
        >>> r.status = '500 ERR'
        >>> r.status
        '500 ERR'
        >>> r.status = u'403 Denied'
        >>> r.status
        '403 Denied'
        >>> r.status = 99
        Traceback (most recent call last):
          ...
        ValueError: Bad response code: 99
        >>> r.status = 'ok'
        Traceback (most recent call last):
          ...
        ValueError: Bad response code: ok
        >>> r.status = [1, 2, 3]
        Traceback (most recent call last):
          ...
        TypeError: Bad type of response code.
        '''
        logging.info("status------------> %s" % isinstance(value, basestring))
        logging.info(value)
        if isinstance(value, (int, long)):
            if value>=100 and value<=999:
                st = HTTP_STATUSES.get(value, '')
                if st:
                    self._status = '%d %s' % (value, st)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d' % value)
        elif isinstance(value, basestring):
            logging.info(isinstance(value, unicode))
            logging.info(_RE_HTTP_STATUS.match(value))
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_HTTP_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('Bad response code: %s' % value)
        else:
            raise TypeError('Bad type of response code.')

    def delete_cookie(self, name):
        '''
        Delete a cookie immediately.

        Args:
          name: the cookie name.
        '''
        self.set_cookie(name, '__deleted__', expires=0)

    def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
        '''
        Set a cookie.

        Args:
          name: the cookie name.
          value: the cookie value.
          max_age: optional, seconds of cookie's max age.
          expires: optional, unix timestamp, datetime or date object that indicate an absolute time of the 
                   expiration time of cookie. Note that if expires specified, the max_age will be ignored.
          path: the cookie path, default to '/'.
          domain: the cookie domain, default to None.
          secure: if the cookie secure, default to False.
          http_only: if the cookie is for http only, default to True for better safty 
                     (client-side script cannot access cookies with HttpOnly flag).

        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
        >>> r._cookies
        {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
        >>> r.set_cookie('company', r'Example="Limited"', expires=1342274794.123, path='/sub/')
        >>> r._cookies
        {'company': 'company=Example%3D%22Limited%22; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/sub/; HttpOnly'}
        >>> dt = datetime.datetime(2012, 7, 14, 22, 6, 34, tzinfo=UTC('+8:00'))
        >>> r.set_cookie('company', 'Expires', expires=dt)
        >>> r._cookies
        {'company': 'company=Expires; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/; HttpOnly'}
        '''
        if not hasattr(self, '_cookies'):
            self._cookies = {}
        L = ['%s=%s' % (quote(name), quote(value))]
        if expires is not None:
            if isinstance(expires, (float, int, long)):
                L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
            if isinstance(expires, (datetime.date, datetime.datetime)):
                L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
        elif isinstance(max_age, (int, long)):
            L.append('Max-Age=%d' % max_age)
        L.append('Path=%s' % path)
        if domain:
            L.append('Domain=%s' % domain)
        if secure:
            L.append('Secure')
        if http_only:
            L.append('HttpOnly')
        self._cookies[name] = '; '.join(L)

    def unset_cookie(self, name):
        '''
        Unset a cookie.

        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
        >>> r._cookies
        {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
        >>> r.unset_cookie('company')
        >>> r._cookies
        {}
        '''
        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def content(self):
        self.check_content()
        return self._content

    @content.setter
    def content(self, value):
        self._content = value
        self.check_content()

    def check_content(self):
        if self._content is None:
            self._content = []
        elif isinstance(self._content, unicode):
            self._content = self._content.encode('utf-8')

    def __call__(self, environ, start_response):
        start_response(self.status, self.headers)
        self.check_content()
        return self.content

if __name__ == '__main__':
    import doctest
    doctest.testmod()
