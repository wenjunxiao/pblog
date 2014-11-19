#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, functools
import db
from utils import Dict

class Field(object):

    _counter = 0

    def __init__(self, name=None, max_length=None, default=None, primary_key=False,
        nullable=False, updatable=True, insertable=True):
        self.name = name
        self.max_length = max_length
        self._default = default
        self.primary_key = primary_key
        self.nullable = nullable
        self.updatable = updatable
        self.insertable = insertable
        self._order, Field._counter = Field._counter, Field._counter + 1

    @property
    def default(self):
        d = self._default
        return d() if callable(d) else d

    def __str__(self):
        s = ['<%s:%s,default(%s),' % (self.__class__.__name__, self.name, self._default)]
        self.nullable and s.append('N')
        self.updatable and s.append('U')
        self.insertable and s.append('I')
        s.append('>')
        return ''.join(s)

    __repr__ = __str__

class AutoField(Field):

    def __init__(self, *args, **kwargs):
        kwargs['updatable'] = False
        kwargs['nullable'] = False
        kwargs['primary_key'] = True
        super(AutoField, self).__init__(*args, **kwargs)

class StringField(Field):

    def __init__(self, max_length=255, default='', **kwargs):
        super(StringField, self).__init__(max_length=max_length, default=default, **kwargs)

class IntegerField(Field):

    def __init__(self, default=0, **kwargs):
        super(IntegerField, self).__init__(default=default, **kwargs)

class BigIntegerField(IntegerField):
    pass

class FloatField(Field):

    def __init__(self, default=0.0, **kwargs):
        super(FloatField, self).__init__(default=default, **kwargs)

class BooleanField(Field):

    def __init__(self, default=False, **kwargs):
        super(BooleanField, self).__init__(default=default, **kwargs)

class TextField(Field):

    def __init__(self, default='', **kwargs):
        super(TextField, self).__init__(default=default, **kwargs)

class BlobField(Field):

    def __init__(self, default='', **kwargs):
        super(BlobField, self).__init__(default=default, **kwargs)

class VersionField(Field):

    def __init__(self, name=None):
        super(VersionField, self).__init__(name=name, default=0)

_triggers = frozenset(['pre_insert', 'pre_update', 'pre_delete'])

class ModelMetaclass(type):

    def __new__(cls, name, bases, attrs):
        # skip base model class
        parents = [b for b in bases if isinstance(b, ModelMetaclass)]
        if not parents:
            return super(ModelMetaclass, cls).__new__(cls, name, bases, attrs)
        logging.info("Scan ORMapping %s..." % name)
        fields = dict()
        primary_key = None
        for k, v in attrs.iteritems():
            if isinstance(v, Field):
                if not v.name:
                    v.name = k
                if v.primary_key:
                    if v.updatable:
                        logging.warning('NOTE: change primary key %s(in %s) to non-updatable.',
                            v.name, name)
                        v.updatable = False
                    if v.nullable:
                        logging.warning('NOTE: change primary key %s(in %s) to non-nullable.',
                            v.name, name)
                        v.nullable = False
                    primary_key = v
                fields[k] = v
        if not primary_key:
            raise TypeError('primary key not defined in class: %s' % name)
        for k in fields.iterkeys():
            attrs.pop(k)
        if not '__table__' in attrs:
            attrs['__table__'] = name.lower()
        attrs['__fields__'] = fields
        attrs['__primary_key__'] = primary_key
        for trigger in _triggers:
            if not trigger in attrs:
                attrs[trigger] = None
        return super(ModelMetaclass, cls).__new__(cls, name, bases, attrs)

def _model_init(func):
    @functools.wraps(func)
    def _wrapper(self, *args, **kwargs):
        for k, v in self.__fields__.iteritems():
            setattr(self, k, v.default)
        func(self, *args, **kwargs)
    return _wrapper

class Model(Dict):
    r"""
    Base class for ORM.
    
    >>> import time
    >>> class User(Model):
    ...     id = IntegerField(primary_key=True)
    ...     name = StringField()
    ...     email = StringField(updatable=False)
    ...     passwd = StringField(default=lambda: '******')
    ...     last_modified = FloatField()
    ...     def pre_insert(self):
    ...         self.last_modified = time.time()
    >>> u = User(id=10190, name='Michael', email='orm@db.org')
    >>> r = u.insert()
    >>> u.email
    'orm@db.org'
    >>> u.passwd
    '******'
    >>> u.last_modified > (time.time() - 2)
    True
    >>> f = User.get(10190)
    >>> f.name
    u'Michael'
    >>> f.email
    u'orm@db.org'
    >>> f.email = 'changed@db.org'
    >>> r = f.update() # change email but email is non-updatable!
    >>> len(User.find_all())
    1
    >>> g = User.get(10190)
    >>> g.email
    u'orm@db.org'
    >>> r = g.delete()
    >>> len(db.where('user',id=10190))
    0
    >>> print User.sql_create_table()
    CREATE TABLE user (id integer not null,
        name varchar(255) not null,
        email varchar(255) not null,
        passwd varchar(255) not null,
        last_modified double precision not null,
        primary key(id))
    """
    __metaclass__ = ModelMetaclass

    @_model_init
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    @classmethod
    def get(cls, pk):
        d = db.select_one(cls.__table__, **{cls.__primary_key__.name: pk})
        return cls(**d) if d else None

    @classmethod
    def find_first(cls, order=None, group=None, limit=None, offset=None, **kwargs):
        d = db.select_one(cls.__table__, order=order, group=group, limit=limit,
            offset=offset, **kwargs)
        return cls(**d) if d else None

    @classmethod
    def find_all(cls, order=None):
        l = db.select(cls.__table__, order=order)
        return [cls(**d) for d in l]

    @classmethod
    def find_by(cls, what='*', order=None, group=None, limit=None, offset=None, **kwargs):
        l = db.select(cls.__table__, what=what, where=kwargs, order=order, group=group,
            limit=limit, offset=offset)
        return [cls(**d) for d in l]

    @classmethod
    def count_all(cls):
        return db.select_int(cls.__table__, what='count(%s)' % cls.__primary_key__.name)

    @classmethod
    def count_by(cls, order=None, group=None, limit=None, offset=None, **kwargs):
        return db.select_int(cls.__table__, what='count(%s)' % cls.__primary_key__.name,
            where=kwargs, order=order, group=group, limit=limit, offset=offset)

    def update(self):
        self.pre_update and self.pre_update()
        pk = self.__primary_key__.name
        db.update(self.__table__, where=[(self.__primary_key__.name, getattr(self, pk))],
            **dict([(f.name, getattr(self, f.name)) for f in self.__fields__.itervalues()
                if f.updatable]))
        return self

    def delete(self):
        self.pre_delete and self.pre_delete()
        pk = self.__primary_key__.name
        db.delete(self.__table__, where=[(self.__primary_key__.name, getattr(self, pk))])
        return self

    def insert(self):
        self.pre_insert and self.pre_insert()
        db.insert(self.__table__,**dict([(f.name, getattr(self, f.name)) 
            for f in self.__fields__.itervalues() if f.insertable]))
        return self

    @classmethod
    def sql_create_table(cls):
        schema = db.schema_create_table()
        L = []
        pk = None
        for field in sorted(cls.__fields__.values(),lambda a, b: cmp(a._order, b._order)):
            if field.primary_key:
                pk = field
            data_type = db.data_type(field.__class__.__name__) % field.__dict__
            L.append('%s %s%s' % (field.name, data_type, '' if field.nullable else ' not null'))
        L.append('primary key(%s)' % pk.name)
        return schema % {'table':cls.__table__, 'definition':',\n    '.join(L)}

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    db.create_engine(engine='db.mysql', user='root', password='root', database='test')
    db.execute('drop table if exists user')
    db.execute('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
    import doctest
    doctest.testmod()
