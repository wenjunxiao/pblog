#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""This module is used to reload the modules automatically when any changes is
detected. This can work in two ways: process-mode or thread-mode. When any 
changes occurred, if in process-mode, the subprocess will be killed and start 
new subprocess; if in thread-mode, worker will terminated and reload modules,
and then, load the main module to continue work. So the work will be 
interrupted for a while, depending on the creating process or reload modules.

For examples::

    def main_loop(*args, **kwargs):
         while 1:
            do_something()

    1. In process mode::
    --------------------
        run_with_reloader(main_loop, mode=PROCESS, args=(), kwargs={})

    2. In thread mode::
    -------------------
        run_with_reloader(main_loop, mode=THREAD, args=(), kwargs={})

There is usefull features for running in python interpreter. Use environ
variable 'PYTHONSTARTUP' to specify a module to run after startup. In this
file you can have code like this::

    from autoreload import start_reloader
    start_reloader()

After do this, any impoted module will be auto-reloaded if it is changed.
"""
__author__="Wenjun Xiao"

__all__ = [
    "run_with_reloader",
    "start_reloader",
    "PROCESS",
    "THREAD",
    "create_module",
    'open_print_change',
    'convert_filename',
]

import os,sys,time,threading

def convert_filename(filename):
    """Convert module filename to source filename.

    For examples::
        >>> convert_filename('/examples/tester.pyc')
        '/examples/tester.py'
        >>> convert_filename('/examples/tester.pyo')
        '/examples/tester.py'
        >>> convert_filename('/examples/tester.py')
        '/examples/tester.py'
        >>> convert_filename('/examples/tester.so')
        '/examples/tester.so'
    """
    if filename and filename[-4:] in ('.pyc', '.pyo'):
        if not os.path.isfile(filename) or os.path.isfile(filename[:-1]):
            return filename[:-1]
    return filename

def _iter_module_files(includes=(), filefilter=None):
    """Iterator to module's source filename of sys.modules (built-in 
    excluded).

    Args::
        includes: more modules to iterate.
        filefilter: a filter function for module's filename.
    
    For examples::
        >>> import os
        >>> cf = os.path.abspath(__file__)
        >>> cf = convert_filename(cf)
        >>> def filefilter(filename):
        ...     return not filename.endswith('/os.py')
        >>> l = [f for f in _iter_module_files(filefilter=filefilter)]
        >>> convert_filename(os.__file__) in l
        False
    """
    from itertools import chain
    for module in chain(includes, list(sys.modules.values())):
        filename = convert_filename(getattr(module, '__file__', None))
        if filename and (filefilter is None or filefilter(filename)):
            yield filename

_PRINT_CHANGE = False

def open_print_change():
    global _PRINT_CHANGE
    _PRINT_CHANGE = True

def _changed_files(mtimes, includes=(), filefilter=None):
    """Return changed files if there is any source file of sys.modules changed. 

    Args::
        mtimes: dict to store the last modify time for comparing.
        includes: more files to watch.
        filefilter: function to filter some you don't want to watch.
    """
    L = []
    for filename in _iter_module_files(includes, filefilter):
        try:
            mtime = os.stat(filename).st_mtime
        except (IOError, OSError):
            continue
        old_time = mtimes.get(filename, None)
        if old_time is None:
            mtimes[filename] = mtime
        elif mtime > old_time:
            if _PRINT_CHANGE:
                print "\nFile changed: %s\n" % filename
            L.append(filename)
    return L

def _start_change_detector(reloader, interval, includes=(), filefilter=None, 
    args=(), kwargs=None):
    """Check file state ervry interval. If any change is detected, the reloader
    will be called.

    Args::
        reloader: a function to reload,which the first argument must be a list
                  of changed files. Other arguments are passed by args and 
                  kwargs.
        interval: detecte interval, in seconds.
        includes: more file want to be detected.
        filefilter: filter some file don't want to be detected.
        args: tuple argument(s) for reloader.
        kwargs: key-word arguments for reloader.
    """
    assert reloader, "Must have a reloader for detector!"
    if kwargs is None:
        kwargs = {}
    mtimes = {}
    while 1:
        changes = _changed_files(mtimes, includes, filefilter)
        if changes:
            reloader(changes, *args, **kwargs)
            break
        time.sleep(interval)

# current subprocess
_sub_proc = None

def _signal_handler(*args):
    """Signal handler for process terminated. If there is a subprocess, 
    terminate it firstly."""
    global _sub_proc
    if _sub_proc:
        _sub_proc.terminate()
    sys.exit(0)

def _restart_with_reloader():
    """Deamon for subprocess."""
    import subprocess, signal
    signal.signal(signal.SIGTERM, _signal_handler)
    while 1:
        args = [sys.executable] + sys.argv
        if sys.platform == "win32":
            args = ['"%s"' % arg for arg in args]
        new_env = os.environ.copy()
        new_env['RUN_FLAG'] = 'true'
        global _sub_proc
        _sub_proc = subprocess.Popen(args, env=new_env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        _ridrect_stdout(_sub_proc.stdout)
        exit_code = _sub_proc.wait()
        if exit_code != 3:
            return exit_code

def _ridrect_stdout(stdout):
    """Redirect stdout to current stdout."""
    while 1:
        data = os.read(stdout.fileno(), 2**15)
        if len(data) > 0:
            sys.stdout.write(data)
        else:
            stdout.close()
            sys.stdout.flush()
            break

PROCESS = -1
THREAD = -2

def run_with_reloader(runner, mode=PROCESS, interval=1, stopper=None,
    args=(), kwargs=None):
    """Run the runner with reloader in deamon-mode, that is blocked until 
    process exit.

    Args::
        runner: main loop function.
        mode: running mode: PROCESS or THREAD, default to PROCESS
        interval: the interval for detecting changes.
        stopper: a function to be called before reload. use to clear some
                resources,such as, port, etc.
        args: tuple arguments for runner.
        kwargs: key-word arguments for runner.
    """
    if kwargs is None:
        kwargs = {}
    if mode == PROCESS:
        _run_process_reloader(runner, interval, stopper, args, kwargs)
    elif mode == THREAD:
        _run_thread_reloader(runner, interval, stopper, args, kwargs)
    else:
        raise ValueError("Unsupported mode '%s'" % mode)


def _run_process_reloader(runner, interval, stopper, args, kwargs):
    if os.environ.get('RUN_FLAG') == 'true':
        t = threading.Thread(target=runner, name='runner', args=args,
            kwargs=kwargs)
        t.setDaemon(True)
        t.start()
        try:
            def _reloader(files, stopper):
                if stopper:
                    stopper()
                sys.exit(3)
            _start_change_detector(_reloader, interval, args=(stopper,))
        except KeyboardInterrupt:
            pass
    else:
        try:
            sys.exit(_restart_with_reloader())
        except KeyboardInterrupt:
            pass

def _run_thread_reloader(runner, interval, stopper, args, kwargs):
    t = threading.Thread(target=runner, name='runner', args=args, 
        kwargs=kwargs)
    t.setDaemon(True)
    t.start()
    try:
        def _stopper():
            if stopper:
                stopper()
            if t and t.is_alive():
                t.join(10)
        _start_change_detector(_thread_reloader, interval, 
            kwargs={
                'stopper': _stopper,
                'filefilter': None,
                'onlychange': True,
            })
    except KeyboardInterrupt:
        pass

def start_reloader(interval=1, filefilter=None):
    """Start reloader in thread-mode, that returns immediatelly after starting.
    When reloader need to reload, reloader will call stopper to stop server
    firstly, and then to reload all modules. Finally, the main module is loaded
    to make the server run just as before.

    Args::
        stopper: function to stop main loop.
        args: arguments for stopper.
        kwargs: arguments for stopper.
    """
    ff = None
    # in sub thread can't reload(threading), or it will causes an exception::
    ## Exception KeyError: KeyError(-1219803392,) in <module 'threading' from 
    ## '/usr/lib/python2.7/threading.pyc'> ignored
    # Can't reload this file too, because this reload function will del firstly,
    # or it will causes NoneType exception in this module.
    filtfiles = (
        convert_filename(os.path.abspath(threading.__file__)),
        convert_filename(os.path.abspath(__file__)),
        )
    if filefilter:
        ff = lambda f: filefilter(f) and f not in filtfiles
    else:
        ff = lambda f: f not in filtfiles
    kwargs = {
        'includes':(),
        'filefilter':ff,
        'kwargs': {
            'stopper': None,
            'filefilter': ff,
            'onlychange': True,
            'reloadfilter': lambda mn: mn not in ('threading',__name__)
        }
    }
    def _exception_handler(*args, **kwargs):
        try:
            while 1:
                _start_change_detector(*args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
    t = threading.Thread(target=_exception_handler, name='reloader', 
        args=(_thread_reloader, interval), kwargs=kwargs)
    t.setDaemon(True)
    t.start()

def _thread_reloader(changes, stopper=None, filefilter=None,onlychange=False,
    reloadfilter=None):
    if stopper:
        stopper()
    _reload_modules(changes, filefilter, onlychange, reloadfilter)

def _iter_file_modules(filter=None):
    modules = dict(sys.modules.items())
    module_names = list(modules.keys())
    module_names.sort()
    module_names.reverse()
    for module_name in module_names:
        module = modules.get(module_name)
        module_file = convert_filename(getattr(module, '__file__', None))
        if module_file and (filter is None or filter(module_file)):
            yield module_file, module_name, module

def _reload_modules(changes, filefilter, onlychange, reloadfilter=None):
    loader = create_module(_source, 'module_loader')
    main_module = None
    if sys.argv[0].strip() != '':
        main_file = os.path.abspath(sys.argv[0])
        main_name = os.path.split(os.path.splitext(main_file)[0])[1]
    else:
        main_file = ''
        main_name = '__main__'
    module_files = dict()
    ff = None
    if onlychange:
        if filefilter:
            ff = lambda f: filefilter(f) and f in changes
        else:
            ff = lambda f: f in changes
    else:
        ff = filefilter
    for mf, mn, mod in _iter_file_modules(ff):
        if mf == main_file or mn == main_name:
            main_file = mf
            main_name = mn
            main_module = mod
        module_files[mn] = mf
        del sys.modules[mn]
        del mod
    loader.reload_from_files(module_files, main_name, reloadfilter)
    loader.reload_module(main_name, main_file)
    if onlychange and _PRINT_CHANGE:
        for filename in changes:
            print "Module file reloaded: %s\n" % filename

_source = """
import imp, os, sys

def reload_module(module_name, module_file):
    '''reload module named as module_name from module_file.'''
    try:
        return __import__(module_name)
    except:
        if module_file[-4:] in ('.pyc', '.pyo'):
            if os.path.isfile(module_file[:-1]):
                return imp.load_source(module_name, module_file[:-1])
            else:
                return imp.load_compiled(module_name, module_file)
        elif module_file[-3:] in ('.py'):
            return imp.load_source(module_name, module_file)
        else:
            return imp.load_dynamic(module_name, module_file)

def reload_from_files(module_files, main_name, reloadfilter):
    module_names = module_files.keys()
    module_names.sort()
    last_len = len(module_names)
    while last_len > 0:
        for index in range(last_len - 1, -1, -1):
            module_name = module_names[index]
            module_file = module_files[module_name]
            if module_name != main_name:
                try:
                    module = loader.reload_module(module_name, module_file)
                    sys.modules[module_name] = module
                    del module_names[index]
                except:
                    pass
        if len(module_names) < last_len:
            last_len = len(module_names)
        else:
            break
    for module_name, module in sys.modules.items():
        try:
            if reloadfilter is None or reloadfilter(module_name):
                reload(module)
        except:
            pass
"""
def create_module(source, name):
    """Create a new seprarate module from source code, which is not in sys
    and temprary for loading sys source, and then will be deleted.

    Args::
        source: source code string or file.
        name: the new module's name you want.

    For examples::
        >>> source_code = '''
        ... def print_module():
        ...     print __name__
        ... '''
        >>> mod = create_module(source_code, "mod_created")
        >>> mod.print_module()
        mod_created
    """
    import imp
    module = imp.new_module(name)
    exec source in module.__dict__
    return module

if __name__=='__main__':
    import doctest
    doctest.testmod()
