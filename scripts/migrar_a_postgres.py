"""Copy the workshop's SQLite database into an empty Postgres, verified table by table.

    set DATABASE_URL=postgresql://…   (the Neon database from Vercel)
    python scripts/migrar_a_postgres.py                      # data/nimus_production.db
    python scripts/migrar_a_postgres.py --origen otra.db

What it does, in this order:
1. Backs up the local database (data/backups/…-antes-postgres-….db). The local file is only read.
2. Checks the local database is at the schema version this code expects.
3. Builds the schema in Postgres (without the default rows a new database gets) and refuses to continue
   if Postgres already holds data.
4. Copies every table keeping ids, then, still inside the same transaction, compares row counts and money
   totals per table. Any difference rolls everything back: Postgres stays empty.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MONEY = ('total_cents', 'amount_cents', 'subtotal_cents', 'tax_cents', 'balance_cents', 'cost_cents')


def checks(source, raw, tables):
    """Row counts and money totals that must match between SQLite and Postgres."""
    report, problems = [], []
    for table in tables:
        columns = [r[1] for r in source.execute(f'PRAGMA table_info("{table}")')]
        local = source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        cloud = raw.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        line = [table, local, cloud]
        if local != cloud:
            problems.append(f'{table}: {local} filas locales, {cloud} en Postgres')
        for column in (c for c in columns if c in MONEY):
            a = source.execute(f'SELECT COALESCE(SUM("{column}"), 0) FROM "{table}"').fetchone()[0]
            b = int(raw.execute(f'SELECT COALESCE(SUM({column}), 0) FROM {table}').fetchone()[0])
            line.append(f'{column}={a}')
            if a != b:
                problems.append(f'{table}.{column}: {a} local, {b} en Postgres')
        report.append(line)
    return report, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--origen', default=str(ROOT / 'data' / 'nimus_production.db'))
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith(('postgres://', 'postgresql://')):
        sys.exit('Define DATABASE_URL con la dirección de Postgres (Vercel → Storage → Neon → .env.local).')
    origin = Path(args.origen).resolve()
    if not origin.exists():
        sys.exit(f'No existe la base local: {origin}')

    import psycopg
    import db
    from pgcompat import schema

    backup = db.backup_database(origin, label='antes-postgres')
    print(f'Respaldo local: {backup}')
    source = sqlite3.connect(f'{origin.as_uri()}?mode=ro', uri=True)
    version = source.execute('PRAGMA user_version').fetchone()[0]
    if version != db.SCHEMA_VERSION:
        sys.exit(f'La base local está en la versión {version}; abre la app una vez para actualizarla a {db.SCHEMA_VERSION}.')

    with psycopg.connect(url, autocommit=True) as raw:
        schema.ensure(raw, seed=False)
        tables = schema.table_order(schema.objects(source))
        occupied = [t for t in tables if raw.execute(f'SELECT EXISTS(SELECT 1 FROM {t})').fetchone()[0]]
        if occupied:
            sys.exit('Postgres ya tiene datos (' + ', '.join(occupied[:5]) + '…). No se copió nada para no mezclar registros.')
        with raw.transaction():
            counts = schema.copy_tables(source, raw, tables)
            report, problems = checks(source, raw, tables)
            if problems:
                print('Diferencias encontradas; no se guardó nada en Postgres:')
                for p in problems:
                    print('  -', p)
                raise SystemExit(1)
    source.close()
    total = sum(counts.values())
    print(f'Copiadas {total} filas de {len([c for c in counts.values() if c])} tablas con datos; conteos y totales coinciden.')
    for table, local, cloud, *money in report:
        if local:
            print(f'  {table:34} {local:>6}  ' + '  '.join(money))


if __name__ == '__main__':
    main()
