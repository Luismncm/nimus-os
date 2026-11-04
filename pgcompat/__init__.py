"""Postgres behind the same `db.connect()` the services already use.

The services write SQLite SQL and expect sqlite3's behaviour: `?` parameters, `lastrowid`, rows readable by
name and position, one writer at a time, a failed statement that does not void the transaction, and
sqlite3's exceptions. This package gives them exactly that over Postgres, so the same 69 services and their
tests run unchanged in the cloud:

- translate.py  SQLite SQL → Postgres SQL (cached per statement).
- schema.py     the final SQLite schema (tables, indexes, the view and the 124 rule triggers) built in Postgres.
- connection.py the sqlite3-shaped connection, cursor and row over psycopg.
"""
