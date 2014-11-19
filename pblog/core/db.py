#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Database operation module."""

__author__="Wenjun Xiao"

import logging, threading, functools, time, uuid

from utils import CaseInsensitiveDict, load_module, Dict

def next_id(t = None):
    """
    Return next id as 50-char string.

    Args:
        t: unix timestamp, default to None and using time.time().
    For example::
        >>> len(next_id())
        50
    """
    if t is None:
        t = time.time()
    return '%015d%s000' % (int(t *1000),uuid.uuid4().hex)

class DBError(Exception):
    pass

class MultiColumnsError(DBError):
    pass

class _LazyConnection(object):

    def __init__(self, connect):
        self.connect = connect
        self.connection = None

    def cursor(self):
        if self.connection is None:
            connection = self.connect()
            logging.info('open connection at <0x%08x>' % id(connection))
            self.connection = connection
        return self.connection.cursor()

    def commit(self):
        if self.connection:
            self.connection.commit()

    def rollback(self):
        if self.connection:
            self.connection.rollback()

    def cleanup(self):
        if self.connection:
            connection = self.connection
            self.connection = None
            logging.info('close connection at <0x%08x>' % id(connection))
            connection.close()

class _DBCtx(threading.local):

    def __init__(self, connect):
        self.connection = None
        self.transactions = 0
        self.connect = connect

    def is_init(self):
        return not self.connection is None

    def init(self):
        logging.info('open lazy connection...')
        self.connection = _LazyConnection(self.connect)
        self.transactions = 0

    def in_transaction(self):
        return self.transactions

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        self.connection.cleanup()
        self.connection = None

class _TransactionCtx(object):

    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        self.shuold_cleanup = False
        if not self.ctx.is_init():
            self.ctx.init()
            self.shuold_cleanup = True
        self.ctx.transactions = self.ctx.transactions + 1
        return self

    def __exit__(self, exctype, excvalue, traceback):
        self.ctx.transactions = self.ctx.transactions - 1
        try:
            if self.ctx.transactions == 0:
                if exctype is None:
                    self.commit()
                else:
                    logging.warning("%s\n\t%s\n\t\t%s", exctype, execvalue, traceback)
                    self.rollback()
        finally:
            if self.shuold_cleanup:
                self.ctx.cleanup()

    def commit(self):
        logging.info('commit transaction...')
        try:
            self.ctx.commit()
            logging.info('commit ok')
        except:
            logging.warning('commit failed, try rollback...')
            self.ctx.rollback()
            logging.warning('rollback ok')
            raise

    def rollback(self):
        logging.info('rollback transaction...')
        self.ctx.rollback()
        logging.info('rollback ok')

def _transactionctx(func):
    @functools.wraps(func)
    def _wrapper(self, *args, **kwargs):
        with self.transaction():
            return func(self, *args, **kwargs)
    return _wrapper

class _ConnectionCtx(object):

    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        self.shuold_cleanup = False
        if not self.ctx.is_init():
            self.ctx.init()
            self.shuold_cleanup = True

    def __exit__(self, exctype, excvalue, traceback):
        if self.shuold_cleanup:
            self.ctx.cleanup()

def _connectionctx(func):
    @functools.wraps(func)
    def _wrapper(self, *args, **kwargs):
        with self.connection():
            return func(self, *args, **kwargs)
    return _wrapper

# Database engine object.
class DBEngine(object):

    def __init__(self, driver=None, placeholder='%s', **kwargs):
        kwargs.pop('driver', None)
        self.driver = driver
        self.kwargs = kwargs
        self.placeholder = placeholder
        self._ctx = _DBCtx(self._connect)

    @property
    def ctx(self):
        if not self._ctx.is_init():
            self._ctx.init()
        return self._ctx

    def _connect(self):
        return self.driver.connect(**self.kwargs)

    def _cursor(self):
        return self.ctx.cursor()

    @_connectionctx
    def execute(self, sql, *args):
        cursor = self._cursor()
        try:
            return self._execute(cursor, sql, *args)
        finally:
            cursor.close()

    def _execute(self, cursor, sql, *args):
        logging.debug('SQL: %s, ARGS: %s', sql, args)
        return cursor.execute(sql, args)

    @_connectionctx
    def _execute_dml(self, sql, *args):
        cursor = self._cursor()
        try:
            self._execute(cursor, sql, *args)
            r = cursor.rowcount
            if not self.ctx.in_transaction():
                logging.info('auto commit')
                self.ctx.commit()
            return r
        finally:
            cursor.close()

    @_connectionctx
    def _execute_dql(self, sql, first, *args):
        cursor = self._cursor()
        try:
            self._execute(cursor, sql, *args)
            if cursor.description:
                names = [x[0] for x in cursor.description]
            if first:
                values = cursor.fetchone()
                if not values:
                    return None
                return Dict(names, values)
            return [Dict(names, x) for x in cursor.fetchall()]
        finally:
            cursor.close()

    def select(self, tables, what='*', where=None, order=None, group=None, 
        limit=None, offset=None, first= False, _test=False):
        r"""
        >>> db = DBEngine()
        >>> db.select('user', _test=True)
        ('SELECT * FROM user', ())
        >>> db.select(['user'], where=[('id', 1)], _test=True)
        ('SELECT * FROM user WHERE id = %s', (1,))
        >>> db.select('user', where=[('sex', 'male')], order='id', limit=3,_test=True)
        ('SELECT * FROM user WHERE sex = %s ORDER BY id LIMIT 3', ('male',))
        >>> db.select('user', where=[('sex', 'male'),('name', 'John')],_test=True)
        ('SELECT * FROM user WHERE sex = %s AND name = %s', ('male', 'John'))
        >>> db = DBEngine(placeholder=None)
        >>> db.select(['user'], where=[('id', 1)], _test=True)
        ('SELECT * FROM user WHERE id = 1', ())
        >>> db.select('user', where=[('sex', 'male')], order='id', limit=3,_test=True)
        ("SELECT * FROM user WHERE sex = 'male' ORDER BY id LIMIT 3", ())
        """
        where, args = self._extract_where(where)
        clauses = self._clauses(tables, what, where, order, group, limit, offset)
        sql = self._extract_clauses(clauses)
        if _test: return sql, args
        return self._execute_dql(sql, first, *args)

    def where(self, tables, what='*', order=None, group=None, 
        limit=None, offset=None, first= False, _test=False, **kwargs):
        r"""
        >>> db = DBEngine()
        >>> db.where('user', name='Lily', sex='female', _test=True)
        ('SELECT * FROM user WHERE name = %s AND sex = %s', ('Lily', 'female'))
        >>> db = DBEngine(placeholder=None)
        >>> db.where('user', age=18, sex='male', _test=True)
        ("SELECT * FROM user WHERE age = 18 AND sex = 'male'", ())
        """
        return self.select(tables, where=kwargs, what=what, order=order, 
            group=group, limit=limit, offset=offset, first=first, _test=_test)

    def select_one(self, tables, what='*', order=None, group=None, 
        limit=None, offset=None, _test=False, **kwargs):
        return self.select(tables, where=kwargs, what=what, order=order, 
            group=group, limit=limit, offset=offset, first=True)

    def select_int(self, tables, what='*', order=None, group=None, 
        limit=None, offset=None, _test=False, **kwargs):
        d = self.select(tables, where=kwargs, what=what, order=order, 
            group=group, limit=limit, offset=offset, first=True)
        if len(d) != 1:
            raise MultiColumnsError('Expect only one column.')
        return d.values()[0]

    def _extract_where(self, where, grouping = ' AND '):
        r"""
        >>> db = DBEngine()
        >>> db._extract_where("id=1 and name='Lily")
        ("id=1 and name='Lily", ())
        >>> db._extract_where([('id',1),('name','Lily')])
        ('id = %s AND name = %s', (1, 'Lily'))
        >>> db._extract_where({'id':1,'name':'Lily'})
        ('id = %s AND name = %s', (1, 'Lily'))
        """
        def _where_and_args(items):
            w = []
            args = []
            for k, v in items:
                if v is None:
                    w.append(k)
                elif self.placeholder:
                    w.append(k + ' = ' + self.placeholder)
                    args.append(v)
                else:
                    w.append("%s = %s" % (k, repr(v)))
            return grouping.join(w) if w else None, tuple(args)
        if isinstance(where, (list, tuple)):
            return _where_and_args(where)
        elif isinstance(where, dict):
            return _where_and_args(where.items())
        else:
            return where, ()

    def _clauses(self, tables, what, where, order, group, limit, offset):
        return (
            ('SELECT', what),
            ('FROM', tables),
            ('WHERE', where),
            ('GROUP BY', group),
            ('ORDER BY', order),
            ('LIMIT', limit),
            ('OFFSET', offset),
        )

    def _extract_clauses(self, clauses):
        r"""
        >>> db = DBEngine()
        >>> db._extract_clauses([('SELECT', '*'), ('FROM', 'user'), ('WHERE', None)])
        'SELECT * FROM user'
        """
        L = [self.gen_clause(key, val) for key, val in clauses if val is not None]
        return " ".join(L)

    def gen_clause(self, key, val):
        r"""
        >>> db = DBEngine()
        >>> db.gen_clause('SELECT', ('id', 'name'))
        'SELECT id, name'
        """
        if isinstance(val, (int, long, float)):
            val = repr(val)
        elif isinstance(val, (list, tuple)):
            val = ", ".join(val)
        if key and val:
            return key + " " + str(val)
        else:
            return key or val

    def update(self, tables, where, _test=False, **values):
        r"""
        >>> db = DBEngine()
        >>> db.update('user',where=[('id', 1)],name='Lily',_test=True)
        ('UPDATE user SET name = %s WHERE id = %s', ('Lily', 1))
        >>> db = DBEngine(placeholder=None)
        >>> db.update('user',where=[('id', 1)],name='Lily',_test=True)
        ("UPDATE user SET name = 'Lily' WHERE id = 1", ())
        """
        where, args = self._extract_where(where)
        values, valargs = self._extract_where(values, ', ')
        sql = self._extract_clauses((
            ('UPDATE', tables),
            ('SET', values),
            ('WHERE', where),
        ))
        args = valargs + args
        if _test: return sql, args
        return self._execute_dml(sql, *args)

    def insert(self, table, _test=False, **values):
        r"""
        >>> db = DBEngine()
        >>> db.insert('user', name='Lily', sex='female', age=18, _test=True)
        ('INSERT INTO user (age, name, sex) VALUES (%s, %s, %s)', [18, 'Lily', 'female'])
        >>> db = DBEngine(placeholder=None)
        >>> db.insert('user', name='Lily', sex='female', age=18, _test=True)
        ("INSERT INTO user (age, name, sex) VALUES (18, 'Lily', 'female')", ())
        """
        def b(s): return '(' + s + ')'
        sql = self._extract_clauses((
            ('INSERT INTO', table),
            (None, b(', '.join(values.keys()))),
            ('VALUES', b(', '.join([self.placeholder if self.placeholder else repr(v) 
                for v in values.values()]))
            )
        ))
        args = values.values() if self.placeholder else ()
        if _test: return sql, args
        return self._execute_dml(sql, *args)

    def delete(self, table, where, using=None, _test=False):
        r"""
        >>> db = DBEngine()
        >>> db.delete('user', where=[('name', 'Lily'), ('sex', 'M')],_test=True)
        ('DELETE FROM user WHERE name = %s AND sex = %s', ('Lily', 'M'))
        """
        where, args = self._extract_where(where)
        sql = self._extract_clauses((
            ('DELETE FROM', table),
            ('USING', using),
            ('WHERE', where)
        ))
        if _test: return sql, args
        return self._execute_dml(sql, *args)

    def transaction(self):
        return _TransactionCtx(self._ctx)

    def connection(self):
        return _ConnectionCtx(self._ctx)

    def data_type(self, key):
        raise NotImplementedError()

    def schema_create_table(self):
        raise NotImplementedError()

class MySQLDB(DBEngine):
    
    data_types = {
        'StringField': 'varchar(%(max_length)s)',
        'IntegerField': 'integer',
        'BigIntegerField': 'bigint',
        'FloatField': 'double precision',
        'BooleanField': 'bool',
        'TextField': 'longtext',
        'BlobField': 'blog',
        'BinaryField': 'longblob',
        'IPAddressField': 'char(15)',
        'GenericIPAddressField': 'char(39)',
        'SmallIntegerField': 'smallint',
        'TimeField': 'time',
        'BinaryField': 'longblob',
        'DateField': 'date',
        'DateTimeField': 'datetime',
        'FileField': 'varchar(%(max_length)s)',
        'AutoField': 'integer AUTO_INCREMENT',
        'VersionField': 'bigint'
    }

    def __init__(self, **kwargs):
        import mysql.connector
        params = dict(driver=mysql.connector,use_unicode=True, charset='utf8',
            autocommit=False, collation='utf8_general_ci')
        params.update(kwargs)
        super(MySQLDB, self).__init__(placeholder='%s', **params)

    def data_type(self, key):
        return self.data_types[key]

    def schema_create_table(self):
        return "CREATE TABLE %(table)s (%(definition)s)"

mysql = MySQLDB

class SqliteDB(DBEngine):

    def __init__(self, **kwargs):
        import sqlite3
        super(MySQLDB, self).__init__(driver=sqlite3, placeholder='?', **kwargs)

db = DBEngine(None)

def create_engine(**kwargs):
    """Create database engine from kwargs.

    create_engine(engine='db.mysql', user='root', password='root')
    """
    global db
    if db and db.driver:
        raise DBError("Database engine has already initialized!")
    kwargs = CaseInsensitiveDict(**kwargs)
    engine = kwargs.pop('ENGINE')
    if isinstance(engine, basestring):
        engine = load_module(engine)
    db = engine(**kwargs)
    return db

def with_transaction(func):
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with db.transaction():
            return func(*args, **kwargs)
    return _wrapper

def with_connection(func):
    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with db.connection():
            return func(*args, **kwargs)
    return _wrapper

def execute(sql, *args):
    return db.execute(sql, *args)

def select(tables, what='*', where=None, order=None, group=None, 
        limit=None, offset=None, first=False):
    return db.select(tables, what=what, where=where, order=order,group=group,
        limit=limit, offset=offset, first=first)

def where(tables, what='*', order=None, group=None, 
        limit=None, offset=None, first= False, **kwargs):
    return db.where(tables, what=what, order=order, group=group,
        limit=limit, offset=offset, first=first, **kwargs)

def select_one(tables, what='*', order=None, group=None, 
        limit=None, offset=None, **kwargs):
    return db.select_one(tables, what=what, order=order, group=group, 
        limit=limit, offset=offset, **kwargs)

def select_int(tables, what='*', order=None, group=None, 
        limit=None, offset=None, **kwargs):
    return db.select_int(tables, what=what, order=order, group=group, 
        limit=limit, offset=offset, **kwargs)

def update(tables, where, **values):
    return db.update(tables, where, **values)

def insert(table, **values):
    return db.insert(table, **values)

def delete(table, where, using=None):
    return db.delete(table, where, using=using)

def transaction():
    return db.transaction()

def connection():
    return db.connection()

def data_type(key):
    return db.data_type(key)

def schema_create_table():
    return db.schema_create_table()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    create_engine(engine=mysql, user='root', password='root', database='test')
    with db.connection():
        db.execute('drop table if exists user')
        db.execute('create table user(id int primary key, name text, sex char(2), passwd text)')
    with db.transaction():
        db.insert('user', id=100, name='Lily', sex='M', passwd='lily')
        db.insert('user', id=101, name='Lilei', sex='F', passwd='lilei')
        db.insert('user', id=102, name='Lilei', sex='F', passwd='lilei')
    import doctest
    doctest.testmod()
