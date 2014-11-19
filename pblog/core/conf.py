#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""WSGI configuration."""

__author__ = "Wenjun Xiao"

import os, operator, importlib, logging
from utils import CaseInsensitiveDict

SETTINGS_MODULE = 'SETTINGS_MODULE'

class SettingError(Exception):
    """Raised when setting module missing necessary setting item or error."""
    pass

def _lazy_proxy(func):
    def inner(self, *args):
        if self._wrapped is None:
            self._setup()
        try:
            return func(self._wrapped, *args)
        except (KeyError, AttributeError,StandardError) as e:
            raise SettingError("Settings module is missing necessary setting '%s'" % args[0])
    return inner

_DEFAULT_SETTINGS = {
    "BASE_DIR": None,
    "DEBUG": False,
    "TEMPLATE_ENGINE": None,
}

class LazySettings(object):
    """A lazy proxy for settings.

    >>> import os, sys
    >>> sys.path.append('../')
    >>> os.environ[SETTINGS_MODULE] = 'settings_dev'
    >>> settings = LazySettings()
    >>> settings.DEBUG
    True
    >>> settings['DEBUG']
    """
    _wrapped = None

    _test = 11111

    def __init__(self):
        super(LazySettings, self).__init__()

    def init_defaults(self, **kw):
        if self._wrapped is None:
            _DEFAULT_SETTINGS.update(kw)
        else:
            for key, value in kw.items():
                self.setdefault(key, value)

    def _setup(self):
        settings_module = os.environ.get(SETTINGS_MODULE, "setting")
        try:
            mod = importlib.import_module(settings_module)
        except ImportError as e:
            raise ImportError("Could not import settings '%s': %s" % (settings_module, e))

        logging.info('Settings module: %s' % settings_module)
        self._wrapped = CaseInsensitiveDict(**_DEFAULT_SETTINGS)
        for setting in dir(mod):
            if setting.isupper():
                setting_value = self._check_dict(getattr(mod, setting))
                setattr(self._wrapped, setting, setting_value)
        self.check_setting(settings_module)
        import sys
        del sys.modules[mod.__name__]
        del mod

    def _check_dict(self, value):
        if isinstance(value, dict):
            D = CaseInsensitiveDict()
            for k, v in value.iteritems():
                D[k] = self._check_dict(v)
            return D
        else:
            return value

    def check_setting(self, settings_module):
        module_scann = self.get('MODULE_SCAN')
        if module_scann and not isinstance(module_scann, tuple):
            raise SettingError(
                r"'MODULE_SCAN' in Setting module '%s' is '%s' (not a tuple)" % 
                (settings_module, type(module_scann)))

    __getattr__ = _lazy_proxy(getattr)

    def __setattr__(self, name, value):
        if name == "_wrapped":
            # Assign to __dict__ to avoid infinite __setattr__ loops.
            self.__dict__["_wrapped"] = value
        else:
            if self._wrapped is None:
                self._setup()
            setattr(self._wrapped, name, value)

    def __delattr__(self, name):
        if name == "_wrapped":
            raise TypeError("can't delete _wrapped.")
        if self._wrapped is None:
            self._setup()
        delattr(self._wrapped, name)

    # Dictionary methods support
    __getitem__ = _lazy_proxy(operator.getitem)
    __setitem__ = _lazy_proxy(operator.setitem)
    __delitem__ = _lazy_proxy(operator.delitem)
    __len__ = _lazy_proxy(len)
    __contains__ = _lazy_proxy(operator.contains)

settings = LazySettings()

if __name__ == '__main__':
    import doctest
    doctest.testmod()
