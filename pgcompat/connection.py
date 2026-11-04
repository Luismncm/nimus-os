"""A sqlite3-shaped connection over psycopg, so the services keep their SQL and their habits.

What the services rely on, and how it is kept:
- `conn.execute(sql, params)` with `?` parameters, returning a cursor with fetchone/fetchall/lastrowid/rowcount.
- Rows readable by column name and by position, and convertible with dict(row), like sqlite3.Row.
- One writer at a time (SQLite's BEGIN IMMEDIATE): every write transaction takes the same advisory lock first,
  so revision checks and balances never race.
- A failed statement leaves the transaction usable (SQLite's statement-level rollback): writes run inside
  a savepoint.
- Errors arrive as sqlite3's own exceptions with the trigger's message, so every `except sqlite3.…` and
  every message shown on screen stays the same.
- Dates and booleans are passed the way sqlite3 stores them: ISO text and 0/1.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal
import os
import sqlite3
import threading
from contextlib import contextmanager

import psycopg
from psycopg import errors as pgerrors

from pgcompat.translate import explicit_id, insert_target, to_postgres

WRITER_LOCK = 0x4E494D5553  # "NIMUS": one advisory lock shared by every write transaction.
_ID_TABLES: dict[str, set[str]] = {}
_TEMPLATE_LOCK = threading.Lock()
_READY: set[str] = set()


class Row(tuple):
    """sqlite3.Row's interface: row['col'], row[0], row.keys(), dict(row)."""

    def __new__(cls, values, names):
        row = super().__new__(cls, values)
        row._names = names
        row._index = {n: i for i, n in reversed(list(enumerate(names)))}
        return row

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._index[key])
            except KeyError:
                lowered = key.lower()
                if lowered in self._index:
                    return tuple.__getitem__(self, self._index[lowered])
                raise IndexError(f'No item with that key: {key}') from None
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._names)


def _plain(value):
    """Postgres sums come back as Decimal; SQLite gives int for whole numbers and float otherwise."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _row_factory(cursor):
    names = [c.name for c in cursor.description] if cursor.description else []
    return lambda values: Row(tuple(_plain(v) for v in values), names)


def _value(value):
    """A parameter as sqlite3 would store it."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=' ')
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, float) and not value.is_integer():
        # As text, Postgres reads it by the column's type: a decimal column takes 1.5, an integer column refuses it
        # (SQLite's TYPEOF='integer' checks) instead of silently rounding it to 2.
        return repr(value)
    return value


def _translate_error(exc: Exception) -> Exception:
    diag = getattr(exc, 'diag', None)
    message = (diag.message_primary if diag and diag.message_primary else str(exc)).strip()
    table = getattr(diag, 'table_name', None) if diag else None
    column = getattr(diag, 'column_name', None) if diag else None
    if isinstance(exc, pgerrors.RaiseException):
        return sqlite3.IntegrityError(message)
    if isinstance(exc, pgerrors.UniqueViolation):
        detail = (diag.message_detail or '') if diag else ''
        cols = detail.split('(', 1)[1].split(')', 1)[0] if '(' in detail else ''
        return sqlite3.IntegrityError('UNIQUE constraint failed: ' + ', '.join(f'{table}.{c.strip()}' for c in cols.split(',')) if cols else message)
    if isinstance(exc, pgerrors.ForeignKeyViolation):
        return sqlite3.IntegrityError('FOREIGN KEY constraint failed')
    if isinstance(exc, pgerrors.CheckViolation):
        return sqlite3.IntegrityError(f'CHECK constraint failed: {diag.constraint_name if diag else message}')
    if isinstance(exc, pgerrors.NotNullViolation):
        return sqlite3.IntegrityError(f'NOT NULL constraint failed: {table}.{column}')
    if isinstance(exc, pgerrors.IntegrityError):
        return sqlite3.IntegrityError(message)
    if isinstance(exc, (pgerrors.InvalidTextRepresentation, pgerrors.NumericValueOutOfRange)):
        # A fraction where only whole units fit: SQLite refuses it through a CHECK constraint.
        return sqlite3.IntegrityError(f'CHECK constraint failed: {message}')
    if isinstance(exc, (pgerrors.LockNotAvailable, pgerrors.QueryCanceled, pgerrors.SerializationFailure, pgerrors.DeadlockDetected)):
        return sqlite3.OperationalError('database is locked')
    if isinstance(exc, psycopg.OperationalError):
        return sqlite3.OperationalError(message)
    return sqlite3.OperationalError(message)


class Cursor:
    def __init__(self, rows=None, lastrowid=None, rowcount=-1, description=None):
        self._rows = list(rows or [])
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self.description = description

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, size=1):
        rows, self._rows = self._rows[:size], self._rows[size:]
        return rows

    def __iter__(self):
        while self._rows:
            yield self._rows.pop(0)


class Connection:
    """The subset of sqlite3.Connection the services use, inside one transaction opened by connect()."""

    def __init__(self, raw: psycopg.Connection, *, write: bool):
        self._raw = raw
        self._write = write
        self._savepoint = 0
        self.row_factory = None

    def _id_tables(self):
        key = self._raw.info.dsn
        if key not in _ID_TABLES:
            _ID_TABLES[key] = {r[0] for r in self._raw.execute(
                "SELECT table_name FROM information_schema.columns WHERE table_schema = current_schema() "
                "AND column_name = 'id' AND is_identity = 'YES'").fetchall()}
        return _ID_TABLES[key]

    def execute(self, sql, params=()):
        text = sql.strip()
        head = text[:10].upper()
        if head.startswith('PRAGMA'):
            return self._pragma(text)
        if head.startswith(('BEGIN', 'COMMIT', 'ROLLBACK', 'SAVEPOINT', 'RELEASE')):
            return Cursor()
        if head.startswith('CREATE TRI') or head.startswith('DROP TRIGG'):
            return self._trigger(text)
        statement = to_postgres(sql)
        target = insert_target(sql)
        wants_id = bool(target) and target in self._id_tables() and 'RETURNING' not in statement.upper()
        if wants_id:
            statement += ' RETURNING id'
        values = {k: _value(v) for k, v in params.items()} if isinstance(params, dict) else tuple(_value(v) for v in params)
        writes = not head.startswith(('SELECT', 'WITH'))
        self._savepoint += 1
        name = f'nimus_sp_{self._savepoint}'
        try:
            if writes:
                self._raw.execute(f'SAVEPOINT {name}')
            cur = self._raw.cursor(row_factory=_row_factory)
            cur.execute(statement, values)
            rows = cur.fetchall() if cur.description else []
            lastrowid = rows[0][0] if wants_id and rows else None
            if wants_id:
                rows = []
            result = Cursor(rows, lastrowid, cur.rowcount, cur.description)
            if target and target in self._id_tables() and explicit_id(sql):
                # A folio inserted with its own id (production._code): the identity must continue after it.
                self._raw.execute(f"SELECT setval(pg_get_serial_sequence('{target}', 'id'), "
                                  f"GREATEST((SELECT COALESCE(MAX(id), 1) FROM {target}), 1))")
                result.lastrowid = lastrowid
            if writes:
                self._raw.execute(f'RELEASE SAVEPOINT {name}')
            return result
        except psycopg.Error as exc:
            if writes:
                self._raw.execute(f'ROLLBACK TO SAVEPOINT {name}')
            raise _translate_error(exc) from exc

    def executemany(self, sql, seq):
        total = 0
        for params in seq:
            total += max(self.execute(sql, params).rowcount, 0)
        return Cursor(rowcount=total)

    def _trigger(self, text):
        """A rule trigger created or dropped at runtime, in SQLite syntax, done the Postgres way."""
        import re
        from pgcompat.schema import trigger
        try:
            if text[:10].upper().startswith('CREATE TRI'):
                for statement in trigger(text):
                    self._raw.execute(statement)
            else:
                name = re.match(r"DROP TRIGGER\s+(?:IF EXISTS\s+)?\"?(\w+)", text, re.I).group(1)
                table = self._raw.execute('SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid '
                                          'WHERE t.tgname = %s AND NOT t.tgisinternal', (name.lower(),)).fetchone()
                if table:
                    self._raw.execute(f'DROP TRIGGER {name} ON {table[0]}')
        except psycopg.Error as exc:
            raise _translate_error(exc) from exc
        return Cursor()

    def _pragma(self, text):
        """The PRAGMAs the services read at runtime; the rest only matter to SQLite."""
        lowered = text.lower()
        if lowered.startswith('pragma table_info'):
            table = lowered.split('(', 1)[1].split(')', 1)[0].strip().strip('"\'')
            rows = self._raw.execute(
                "SELECT ordinal_position - 1, column_name, data_type, (is_nullable = 'NO')::int, column_default, 0 "
                "FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
                (table,)).fetchall()
            names = ['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk']
            return Cursor([Row(r, names) for r in rows])
        if lowered.startswith('pragma user_version'):
            value = self._raw.execute("SELECT value FROM nimus_meta WHERE key='schema_version'").fetchone()
            return Cursor([Row((int(value[0]) if value else 0,), ['user_version'])])
        if lowered.startswith('pragma foreign_key_check'):
            return Cursor()
        return Cursor()

    def create_function(self, *args, **kwargs):
        """Functions are defined once in the Postgres schema (see pgcompat.schema)."""

    def commit(self):
        """connect() commits when its block ends, like the SQLite path."""

    def rollback(self):
        """connect() rolls back when its block fails."""

    def close(self):
        """connect() closes the connection."""


def _admin_url():
    return os.environ.get('NIMUS_PG_PER_PATH') or os.environ['DATABASE_URL']


def _with_database(url, name):
    base, _, rest = url.rpartition('/')
    query = ('?' + rest.split('?', 1)[1]) if '?' in rest else ''
    return f'{base}/{name}{query}'


def database_url(path_hint: str | None = None) -> str:
    """The Postgres URL to use.

    In the cloud it is DATABASE_URL. For tests, NIMUS_PG_PER_PATH points at a local cluster and every
    NIMUS_DB_PATH gets its own database, cloned from a template that already has the schema.
    """
    if not os.environ.get('NIMUS_PG_PER_PATH'):
        return os.environ['DATABASE_URL']
    import db
    path = str(path_hint or db.database_path())
    name = 'nimus_' + hashlib.sha1(path.encode()).hexdigest()[:16]
    if name in _READY:
        return _with_database(_admin_url(), name)
    with _TEMPLATE_LOCK:
        admin = _admin_url()
        with psycopg.connect(admin, autocommit=True) as raw:
            if not raw.execute('SELECT 1 FROM pg_database WHERE datname = %s', (name,)).fetchone():
                template = 'nimus_template_' + str(db.SCHEMA_VERSION)
                if not raw.execute('SELECT 1 FROM pg_database WHERE datname = %s', (template,)).fetchone():
                    raw.execute(f'CREATE DATABASE {template}')
                    from pgcompat import schema
                    with psycopg.connect(_with_database(admin, template), autocommit=True) as tpl:
                        schema.ensure(tpl)
                raw.execute(f'CREATE DATABASE {name} TEMPLATE {template}')
        _READY.add(name)
    return _with_database(_admin_url(), name)


@contextmanager
def connect(*, write: bool = False, migration: bool = False, reconciliation: bool = False):
    try:
        # No server-side prepared statements: Neon's pooled URL (PgBouncer, transaction mode) does not keep them.
        raw = psycopg.connect(database_url(), autocommit=False, connect_timeout=15, prepare_threshold=None)
    except psycopg.OperationalError as exc:
        raise sqlite3.OperationalError(f'No se pudo conectar a la base: {exc}') from exc
    try:
        raw.execute("SET LOCAL lock_timeout = '15s'")
        if write:
            raw.execute('SELECT pg_advisory_xact_lock(%s)', (WRITER_LOCK,))
        if write and reconciliation:
            raw.execute("SELECT set_config('nimus.reconciling', '1', true)")
        conn = Connection(raw, write=write)
        yield conn
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()


def ensure_schema():
    """Create or check the schema of the database in use (init_db's Postgres path)."""
    from pgcompat import schema
    with psycopg.connect(database_url(), autocommit=True) as raw:
        return schema.ensure(raw)
