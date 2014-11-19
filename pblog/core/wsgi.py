#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lightweight WSGI-compatible web framework."""

__author__="Wenjun Xiao"

import os,logging, types, importlib, re, mimetypes, functools, json
from threading import Lock
from http import ctx, Request, Response, HTTPError, NotFound, Redirect, InternalServerError
from conf import settings
from webapi import *
from utils import load_module 
from autoreload import run_with_reloader

class RouteBase(object):
    r"""Basic class for all routes is callable object. Call this with match 
    result when result is non-null. If there are two objects that have the 
    same pattern, so is considered to be same route. Typically, when placed
    in tuple, list, or dict, it should to check whether it exists.

    Args::
        pattern:
            The pattern of request path, which is used to route.
        method:
            The request method ,like GET, POST, HEAD, etc,which is used
            to identify the type of route.
        callback: 
            The callback function when a request matches this route.
        ignorecase: 
            Indicates that the pattern is case sensitive. Defaults to True.
        ignore_interceptor: 
            Indicates that interceptor can intercepete this route's callback.


    For examples::
        >>> def func(*args):
        ...     print "func is called with", args
        >>> r1 = RouteBase('/test/index', 'GET', func)
        >>> r2 = RouteBase('/Test/index', 'GET', func)
        >>> r3 = RouteBase('/test', 'GET', func, False)
        >>> r4 = RouteBase('/Test', 'GET', func, False)
        >>> r1 == None
        False
        >>> r1 == r2
        True
        >>> r1 == r3
        False
        >>> r3 == r4
        False
        >>> args = r1.match('/Test/index/more')
        >>> 'Mismatch' if args is None else r1(*args)
        func is called with ()
        >>> args = r1.match('/test/')
        >>> 'Mismatch' if args is None else r1(*args)
        'Mismatch'
    """

    # the priority for matching the request,to avoid conflicts.
    priority = 0

    def __init__(self, pattern, method, callback, ignorecase=True, 
        ignore_interceptor=False):
        self._pattern = pattern
        self._method = method
        self.callback = callback
        self._orig_callback = callback
        self._ignorecase = ignorecase
        self.ignore_interceptor = ignore_interceptor
        self._regex = re.compile(self._gen_regex_pattern(pattern), 
            re.IGNORECASE if ignorecase else 0)

    def call_witout_interceptor(self, *args):
        return self._orig_callback(*args)

    def _gen_regex_pattern(self, pattern):
        """Generate regex pattern according to the original pattern. Default,
        return the escape str of original pattern. Subclass implements this to
        change the regex pattern."""
        return re.escape(pattern)

    @property
    def pattern(self):
        """Return the original pattern."""
        return self._pattern

    @property
    def method(self):
        """Return the request method"""
        return self._method

    @property
    def regex_pattern(self):
        return self._regex.pattern

    def match(self, path):
        """Called when want to determine whether a request path is matched with
        current route item. Return the argument(s) path included if matched 
        (usually used as argument(s) to call this object), or None if mismatch.
        """
        m = self._regex.match(path)
        if m:
            return m.groups()
        return None

    def _get_cmp_pattern(self):
        """Return the pattern , which is used to compare, according to attr 
        'ignorecase'."""
        if self._ignorecase:
            return self._pattern.lower()
        else:
            return self._pattern

    def __eq__(self, other):
        """Return True if they have same pattern, else False."""
        if other is None or not isinstance(other, RouteBase):
            return False
        return self._get_cmp_pattern() == other._get_cmp_pattern()
        
    def __cmp__(self, other):
        if other is None or not isinstance(other, RouteBase):
            return 1
        return cmp(self._get_cmp_pattern(), other._get_cmp_pattern())

    def __hash__(self):
        """Return the pattern's hash to ensure the eq object have same hash 
        when put in hash container,like dict, etc."""
        return self._get_cmp_pattern().hash()

    def __call__(self, *args):
        """Call the route callback function."""
        return self.callback(*args)

    def __str__(self):
        return '<%s:%s, %s, pattern=%s>' % (
            self.priority,
            self.__class__.__name__, 
            self._method, 
            self._pattern
        )

    __repr__ = __str__

class DynamicRoute(RouteBase):
    """A route, with a dynamic pattern that contains (an) argument flag(s) (with
    a ':' before the word), can match a series of path.

    For examples::
        >>> def comment(user, artical):
        ...     print "Comment on the article '%s' of %s" % (artical, user)
        >>> r = DynamicRoute('/:user/:artical/comment', 'GET', comment)
        >>> args = r.match('/lilei/5100/comment')
        >>> 'Mismatch' if args is None else r(*args)
        Comment on the article '5100' of lilei
    """
    priority = 3

    def _gen_regex_pattern(self, pattern):
        re_list = ['^']
        is_var = False
        for v in RE_ROUTE.split(pattern):
            if is_var:
                var_name = v[1:]
                re_list.append(r'(?P<%s>[^\/]+)' % var_name)
            else:
                re_list.append(re.escape(v))
            is_var = not is_var
        re_list.append('$')
        return ''.join(re_list)

class RegexRoute(RouteBase):
    """Regex pattern route, for simply test some path.

    For examples::
    >>> def get_static(path):
    ...     print "read file:", path
    >>> r = RegexRoute('^/static/(?P<path>.*$)', 'GET', get_static)
    >>> args = r.match('/static/js/jquery.min.js')
    >>> r(*args) if args else 'Mismatch'
    read file: js/jquery.min.js
    """
    priority = 1

    def _gen_regex_pattern(self, pattern):
        """Return the original pattern as regex pattern, and simply remove the
        begin regex flag just for match some simple interceptor like '/static/',
        '/', etc.
        """
        self._pattern = pattern[1:]
        return pattern

class StaticRoute(RouteBase):
    """A route can match the pattern which is same to the route pattern.

    For examples::
        >>> def func(*args):
        ...     print "func is called with", args
        >>> r = StaticRoute('/signin', 'GET', None)
        >>> args = r.match('/signin/')
        >>> 'Mismatch' if args is None else r(*args)
        'Mismatch'
    """
    priority = 5
    def _gen_regex_pattern(self, pattern):
        return ''.join(['^', re.escape(pattern),'$'])

def _static_file_generator(fpath):
    BLOCK_SIZE = 8192
    with open(fpath, 'rb') as f:
        block = f.read(BLOCK_SIZE)
        while block:
            yield block
            block = f.read(BLOCK_SIZE)

def _read_static_file(fpath):
    fpath = os.path.join(ctx.document_root, fpath)
    if not os.path.isfile(fpath):
        raise NotFound()
    fext = os.path.splitext(fpath)[1]
    ctx.response.content_type = mimetypes.types_map.get(fext.lower(),
        'application/octet-stream')
    return _static_file_generator(fpath)

class StaticFileRoute(RouteBase):
    """A route return static file if matched. The result is generator of read
    file that it should use for-loop to read full content of file.

    For examples::
        >>> def read_full_file(g):
        ...     for l in g:
        ...         print l
        >>> doc_root, folder = os.path.split(os.path.dirname(__file__))
        >>> target_file = '%s/%s/test.tmp' % (doc_root, folder)
        >>> with open(target_file, 'w') as f:
        ...     f.write('test file content.')
        >>> ctx.document_root = doc_root
        >>> ctx.response = Response()
        >>> r = StaticFileRoute('/core/')
        >>> args = r.match('/core/test.tmp')
        >>> 'Mismatch' if args is None else read_full_file(r(*args))
        test file content.
        >>> os.remove(target_file)
    """
    priority = 7
    def __init__(self, pattern):
        super(StaticFileRoute, self).__init__(pattern, REQ_GET, 
            _read_static_file, ignore_interceptor=True)

    def _gen_regex_pattern(self, pattern):
        re_list = ['^']
        if pattern.startswith('/'):
            re_list.append('\/(')
            re_list.append(re.escape(pattern[1:]))
        else:
            re_list.append('(')
            re_list.append(re.escape(pattern))
        fname = os.path.split(pattern)[1]
        if not fname:
            re_list.append('.+')
        re_list.append(')$')
        return ''.join(re_list)

def _route_factory(func):
    if hasattr(func, '__request_route__'):
        pattern = func.__request_route__
        if RE_ROUTE.search(pattern):
            return DynamicRoute(pattern, func.__request_method__, func)
        elif pattern and pattern[:1] == '^':
            return RegexRoute(pattern, func.__request_method__, func)
        else:
            return StaticRoute(pattern, func.__request_method__, func)
    elif isinstance(func, RouteBase):
        return func
    else:
        return None

def _build_call_chain(func, target):
    """Build function call chain. The first argument of the 'func' must be a 
    function, other argument must be the argument(s) the 'target' required.

    For examples::
        >>> def target(n):
        ...     print 'target called with', n
        ...     return n
        >>> def f1(next, *args):
        ...     print 'f1():before'
        ...     return next(*args)
        >>> def f2(next, *args):
        ...     print 'f2():before'
        ...     try:
        ...         return next(*args)
        ...     finally:
        ...         print 'f2():after'
        >>> target = _build_call_chain(f1, target)
        >>> target = _build_call_chain(f2, target)
        >>> print "Result: %s" % target(5100)
        f2():before
        f1():before
        target called with 5100
        f2():after
        Result: 5100
    """
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        logging.debug("Call %s() before %s()", func.__name__, target.__name__)
        return func(target, *args, **kw)
    return _wrapper

class WSGIApplication(object):
    """The WSGIApplication object implements a WSGI application and acts as the
    central object. It is passed the document root path.

    Args::
        document_root: document root path.
    """
    def __init__(self, document_root):
        self.document_root = document_root
        self._interceptors = []
        self._route_table = {'GET':[], 'POST':[]}
        self._template_engine = None
        settings.init_defaults(document_root=document_root)

    @property
    def template_engine(self):
        return self._template_engine

    @template_engine.setter
    def template_engine(self, engine):
        if not callable(engine):
            engine = load_module(engine)
        self._template_engine = engine

    def _preprocess_interceptor(self):
        """Preprocess interceptors to update interceptors to all matched 
        routes's call-chain, that ensure interceptor into force when route
        called."""
        for fn in self._interceptors:
            self.update_route_table(fn)
            
    def update_route_table(self, ifunc):
        """Update full route table with interceptor 'ifunc' when matched."""
        for routes in self._route_table.itervalues():
            self._update_routes(ifunc, routes)

    def _update_routes(self, ifunc, routes):
        """Update routes with interceptor 'ifunc' when matched and un-updated.
        """
        for r in routes:
            if r.ignore_interceptor:
                logging.info(
                    'Mismatch <%s> because %s ignore interceptor)' % (
                    ifunc.__name__, str(r))
                )
            elif ifunc.__match__(r.pattern) and (r not in ifunc.__routes__):
                ifunc.__routes__.append(r)
                r.callback = _build_call_chain(ifunc, r.callback)
                logging.info('Match <%s> -> %s)' % (ifunc.__name__, str(r)))

    def scan_modules(self, mods):
        """Scan modules to find function with decorator."""
        changed = False
        for mod in mods:
            if self._add_module(mod):
                changed = True
        if changed:
            self._preprocess_interceptor()

    def _add_module(self, mod):
        """Add interceptor(s) and route(s) in module 'mod' and return True
        if there are any, otherwise False."""
        added = False
        m = mod if type(mod) == types.ModuleType else load_module(mod)
        for name in dir(m):
            fn = getattr(m, name)
            if callable(fn):
                if self._add_interceptor(fn) or self._add_route(fn):
                    added = True
        return added

    def _add_interceptor(self, ifunc):
        if hasattr(ifunc, '__interceptor__'):
            if ifunc in self._interceptors:
                raise ValueError(r"Interceptor <%s> already exists" % 
                    ifunc.__name__)
            ifunc.__routes__ = []
            self._interceptors.append(ifunc)
            logging.info('Interceptor: <%s, pattern=%s, regex=%s>' % (
                ifunc.__name__,
                ifunc.__interceptor_pattern__,
                ifunc.__interceptor__.pattern
            ))
            return True
        return False

    def add_interceptor(self, ifunc):
        """Add interceptor function and preprocess if added."""
        if self._add_interceptor(ifunc):
            self._preprocess_interceptor()

    def _add_route(self, rfunc):
        route = _route_factory(rfunc)
        if route:
            if not self._route_table.has_key(route.method):
                L = self._route_table[route.method] = []
            else:
                L = self._route_table[route.method]
            if route in L:
                raise ValueError(r"The route %s already exists" % str(route))
            L.append(route)
            logging.info('Route: %s,regex=%s' % (str(route), 
                route.regex_pattern))
            return True
        return False

    def add_route(self, rfunc):
        """Add route function and preprocess if added."""
        if self._add_route(rfunc):
            self._preprocess_interceptor()

    def run(self, host=None, port=None, autoreload=None, debug=False):
        """Runs the application on a local development server.

        Args:
            host: the hostname to listen on. Defaults to ``'127.0.0.1'``.
            port: the port of the webserver. Defaults to ``5100`` or the
                  port defined in the ``SERVER_NAME`` config variable if
                  present.
        """
        from wsgiref.simple_server import make_server
        if debug: settings.DEBUG = True
        self.autoreload = autoreload
        if host is None:
            host = '127.0.0.1'
        if port is None:
            server_name = settings.get('SERVER_NAME')
            if server_name and ':' in server_name:
                port = int(server_name.rsplit(':', 1)[1])
            else:
                port = 5100
        logging.info('application (%s) will start at %s:%s' % (self.document_root, host, port))
        server = None
        def runner():
            server = make_server(host, port, self)
            server.serve_forever()
        def stopper():
            if server:
                server.shutdown()
                server.close()
        if autoreload:
            run_with_reloader(runner, stopper=stopper)
        else:
            runner()

    def dispatch_request(self):
        request = ctx.request
        route, args = self.find_route(request.method, request.path_info)
        if route:
            return route(*args)
        return None

    def find_route(self, method, path_info):
        for route in self._route_table[method]:
            args = route.match(path_info)
            if isinstance(args, tuple):
                logging.debug("[%s]<%s> match %s with args<%s>",method, path_info, route, args)
                return route, args
        logging.debug("Mismatch request:%s, %s", method, path_info)
        return None, None

    def make_model(self, rv):
        if isinstance(rv, dict):
            return rv
        elif isinstance(rv, (ModelAndView, JsonModel)):
            return rv.model
        else:
            return {}

    def internal_route(self, method, path_info):
        route, args = self.find_route(method, path_info)
        if route:
            rv = route.call_witout_interceptor(*args)
            return self.make_model(rv)
        return {}

    def make_response(self, rv):
        if rv is None:
            raise NotFound()
        elif isinstance(rv, HTTPError):
            return rv
        elif isinstance(rv, ModelAndView):
            rv = self._template_engine(rv.view, rv.model)
        elif isinstance(rv, JsonModel):
            try:
                rv = json.dumps(rv.model, default=rv.encoder)
            except Exception as e:
                logging.exception(e)
                rv = json.dumps(dict(error='internalerror', data=e.__class__.__name__, 
                    message=e.message))
            ctx.response.content_type = 'application/json'
        ctx.response.content = rv
        return ctx.response

    def handle_exception(self, e):
        if isinstance(e, HTTPError):
            return e
        else:
            logging.exception('exception here::')
            return InternalServerError(str(e))

    def _init_ctx(self, environ):
        ctx.request = Request(environ)
        ctx.response = Response()
        ctx.document_root = self.document_root
        ctx.application = self

    def _load_settings(self):
        if settings.DEBUG:
            logging.warning("Run in debug module, that can't be "
                "turned on in production...")
            self.add_route(StaticFileRoute('/static/'))
            self.add_route(StaticFileRoute('/favicon.ico'))
        self.scan_modules(settings.MODULE_SCAN)
        def _iter_route(rs):
            for r in rs:
                yield str(r)
        for method, routes in self._route_table.items():
            # sort by priority, the greater the priority match.
            routes.sort(lambda a, b: cmp(b.priority, a.priority))
            logging.debug("=============='%s' Route Table===================\n%s",
                method, '\n'.join(_iter_route(routes)))
        if self.template_engine is None:
            self.template_engine = settings.TEMPLATE_ENGINE

    initLock = Lock()

    def _lazy_load(self, environ):
        if self.__lazy__ == self._lazy_load:
            with self.initLock:
                if self.__lazy__ == self._lazy_load:
                    self._load_settings()
                    self.__lazy__ = self._init_ctx
        self._init_ctx(environ)

    __lazy__ = _lazy_load

    def wsgi_app(self, environ, start_response):
        """The actual WSGI application."""
        self.__lazy__(environ)
        try:
            logging.debug("request: %s, %s", ctx.request.method, ctx.request.path_info)
            try:
                response = self.make_response(self.dispatch_request())
            except Exception as e:
                response = self.make_response(self.handle_exception(e))
            return response(environ, start_response)
        finally:
            del ctx.application
            del ctx.document_root
            del ctx.response
            del ctx.request

    def __call__(self, environ, start_response):
        """Shortcut for :attr: `wsgi_app`"""
        try:
            return self.wsgi_app(environ, start_response)
        except:
            logging.exception(" WSGI interface occurs exception:")
            raise

if __name__ == '__main__':
    import doctest
    doctest.testmod()
