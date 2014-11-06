#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__="Wenjun Xiao"

"""Lightweight WSGI-compatible web framework."""

import logging

class WSGIApplication(object):
    """The WSGIApplication object implements a WSGI application and acts as the
    central object. It is passed the name of the module or package of the 
    application.

    Args::
        import_name: the name of the application package

    For example::
    >>> app = WSGIApplication(__name__)
    >>> app = WSGIApplication(__name__.split('.')[0])
    """

    def __init__(self, import_name):
        self.name = import_name

    def run(self, host=None, port=None):
        """Runs the application on a local development server.

        Args:
            host: the hostname to listen on. Defaults to ``'127.0.0.1'``.
            port: the port of the webserver. Defaults to ``5100``.
        """
        from wsgiref.simple_server import make_server
        if host is None:
            host = '127.0.0.1'
        if port is None:
            port = 5100
        logging.info('application (%s) will start at %s:%s' % (self.name, host, port))
        server = make_server(host, port, self)
        server.serve_forever()

    def wsgi_app(self, environ, start_response):
        """The actual WSGI application."""
        start_response('200 OK', [('Content-Type', 'text/html')])
        return '<h1>Hello, welcome to my blog!</h1>'

    def __call__(self, environ, start_response):
        """Shortcut for :attr: `wsgi_app`"""
        return self.wsgi_app(environ, start_response)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
