"""Run from the project root: python scripts/import_control.py source.json."""
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import db
from services.sheet_migration import import_snapshot
from services import expenses, sheet_migration

if __name__=='__main__':
    source=Path(sys.argv[1])
    db.backup_database(label='pre-import-control')
    db.init_db()
    stats=import_snapshot(json.loads(source.read_text(encoding='utf-8')))
    rows=expenses.list_expenses()
    result=dict(imported=stats,expense_count=len(rows),total_cents=sum(r['total_cents'] for r in rows),
        unpaid_cents=sum(r['balance_cents'] for r in rows),partners=sheet_migration.partner_rows(),
        scope='Solo gastos; ingresos existentes conservados. Sin importar inyecciones de socios ni ventas.')
    target=source.with_name('migration_report.json')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='partners'},ensure_ascii=False,indent=2))
