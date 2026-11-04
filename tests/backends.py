"""Which database the suite runs against: SQLite (default) or Postgres (scripts/test_postgres.py).

Tests that build an old SQLite file and migrate it, or inspect the SQLite file itself, only make sense on
SQLite: in the cloud the Postgres schema is built already current (pgcompat.schema) and there is no file.
"""
import os
import unittest

POSTGRES = os.environ.get('NIMUS_TEST_BACKEND') == 'postgres'

sqlite_only = unittest.skipIf(POSTGRES, 'Migra o inspecciona un archivo SQLite; en Postgres el esquema nace actualizado.')
