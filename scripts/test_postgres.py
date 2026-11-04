"""Run the test suite against a real Postgres, the way the cloud will run the services.

Starts an embedded Postgres (pgserver) in a temporary folder, points NIMUS_PG_PER_PATH at it so every test
database (each NIMUS_DB_PATH) becomes its own Postgres database cloned from a template with the schema, and
runs unittest. Tests that inspect SQLite files directly (migrations of old databases, backups) are skipped
with SQLITE_ONLY, since in the cloud those files do not exist.

    python scripts/test_postgres.py                 # whole suite
    python scripts/test_postgres.py tests.test_sales  # one module or test
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv):
    import pgserver
    folder = Path(os.environ.get('NIMUS_PG_DATA') or tempfile.mkdtemp(prefix='nimus-pg-'))
    server = pgserver.get_server(folder, cleanup_mode='stop')
    os.environ['NIMUS_PG_PER_PATH'] = server.get_uri()
    os.environ.pop('DATABASE_URL', None)
    os.environ['NIMUS_TEST_BACKEND'] = 'postgres'
    os.chdir(ROOT)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(argv) if argv else loader.discover('tests', top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
