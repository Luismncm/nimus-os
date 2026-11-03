"""Units printed beyond an order's need, sent to Stock when the job finishes.

A job's quantity stays within its piece's requirement (the capacity triggers are untouched); the
extra is tracked here and posted to inventory as production of that job.
"""


def create_share_schema(conn):
    """Pieces of other orders printed inside a job's extra, and pieces taken from physical stock."""
    # A rider is a normal job of its own piece that travels in the host's print and finishes with it.
    conn.execute('''CREATE TABLE IF NOT EXISTS job_riders (
        job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
        host_job_id INTEGER NOT NULL REFERENCES production_jobs(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL, CHECK(job_id<>host_job_id))''')
    conn.execute('CREATE INDEX IF NOT EXISTS job_riders_host ON job_riders(host_job_id)')
    # A pull is a finished job whose units came out of inventory instead of a printer.
    conn.execute('''CREATE TABLE IF NOT EXISTS stock_pulls (
        job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
        quantity INTEGER NOT NULL CHECK(typeof(quantity)='integer' AND quantity>0),
        created_at TEXT NOT NULL)''')


def create_job_extra_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS job_extras (
        job_id INTEGER PRIMARY KEY REFERENCES production_jobs(id) ON DELETE CASCADE,
        extra INTEGER NOT NULL CHECK(typeof(extra)='integer' AND extra>=0),
        posted INTEGER NOT NULL DEFAULT 0 CHECK(typeof(posted)='integer' AND posted>=0),
        updated_at TEXT NOT NULL)''')
