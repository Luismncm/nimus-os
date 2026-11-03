import csv
import io
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from services import expenses, treasury, sheet_migration
from tests import test_sheet_migration as fixtures


class TreasuryViewsTest(unittest.TestCase):
    setUp=fixtures.SheetMigrationTest.setUp

    def test_unknown_dates_filtering_export_and_exclusion_of_partner_purchases(self):
        sheet_migration.import_snapshot(self.source)
        period=treasury.ledger('2026-01-01','2026-12-31')
        history=treasury.ledger('0001-01-01','9999-12-31',include_undated=True)
        self.assertEqual((period['outflow'],history['outflow'],history['undated']),(12000,17000,1))
        bank,cash,_=treasury.accounts()
        filtered=treasury.ledger('0001-01-01','9999-12-31',include_undated=True,account_id=cash['id'],search='servicio',direction='Salidas',category='Sin clasificar')
        self.assertEqual(filtered['outflow'],5000)
        self.assertEqual(treasury.ledger('0001-01-01','9999-12-31',include_undated=True,direction='Entradas')['income'],0)
        exported=list(csv.reader(io.StringIO(treasury.csv_bytes(filtered['rows']).decode('utf-8-sig'))))
        self.assertEqual(len(exported),2)
        self.assertEqual(exported[1][4],'Servicio')
        self.assertEqual(exported[1][8],'50.00')
        self.assertEqual(exported[1][11],'Sin clasificar')
        pid=next(p['id'] for p in expenses.get_expense(filtered['rows'][0]['record_id'])['payments'])
        expenses.void_payment(pid,'Corrección')
        self.assertEqual(treasury.ledger('0001-01-01','9999-12-31',include_undated=True)['undated'],0)

    def test_classification_without_guessing_date_and_payment_stays_pending(self):
        sheet_migration.import_snapshot(self.source)
        row=next(r for r in expenses.list_expenses() if not r['expense_on'])
        expenses.update(row['id'],dict(expenses.editable(row),category='Operación general'),expected_revision=row['revision'])
        row=expenses.get_expense(row['id'])
        self.assertEqual(row['expense_on'],'')
        self.assertEqual(row['category'],'Operación general')
        expenses.update(row['id'],dict(expenses.editable(row),expense_on='2026-05-05'),expected_revision=row['revision'])
        review=next(r for r in treasury.review_expenses() if r['id']==row['id'])
        self.assertNotIn('Fecha del gasto',review['issues'])
        self.assertIn('Fecha del pago',review['issues'])
        with self.assertRaises(ValueError):
            expenses.update(row['id'],dict(expenses.editable(expenses.get_expense(row['id'])),expense_on=''),expected_revision=review['revision'])
        with self.assertRaises(ValueError): expenses.create(dict(expenses.defaults(),expense_on='',concept='Nuevo',amount=1),request_key='blank-date')

    def test_ui_period_search_partner_and_review_navigation(self):
        sheet_migration.import_snapshot(self.source)
        app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=30).run()
        app.switch_page('views/treasury.py').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(app.selectbox(key='treasury_period').value,'Todo el historial')
        self.assertEqual(next(m.value for m in app.metric if m.label=='Salidas'),'$170.00')
        app.text_input(key='treasury_search').set_value('Servicio').run()
        self.assertEqual(len(app.selectbox(key='treasury_source').options),1)
        self.assertEqual(next(m.value for m in app.metric if m.label=='Salidas de la búsqueda'),'$50.00')
        app.selectbox(key='treasury_period').set_value('Personalizado').run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertEqual(next(m.value for m in app.metric if m.label=='Movimientos encontrados'),'0')
        app.selectbox(key='treasury_period').set_value('Todo el historial').run()
        app.selectbox(key='treasury_review_issue').set_value('Fecha del pago').run()
        self.assertEqual(len(app.selectbox(key='treasury_review_selected').options),1)
        # Socios lives in its own page; Tesorería no longer repeats it as a tab.
        self.assertFalse(any(t.key=='partner_search' for t in app.text_input))
        app.button(key='treasury_review_open').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        self.assertTrue(any(b.key=='expense_back' for b in app.button))
        eid=app.session_state['open_expense_id']
        app.switch_page('views/partners.py').run()
        app.text_input(key='partner_search').set_value('Equipo').run()
        self.assertEqual(len(app.selectbox(key='partner_selected').options),1)
        app.switch_page('views/expenses.py').run()
        app.button(key='expense_edit').click().run()
        prefix='expense_'+app.session_state['dialog_request_key']
        app.selectbox(key=prefix+'_category').set_value('Operación / oficina')
        next(b for b in app.button if b.label=='Guardar cambios').click().run()
        self.assertFalse(app.exception,[e.message for e in app.exception])
        saved=expenses.get_expense(eid)
        self.assertEqual((saved['category'],saved['expense_on']),('Operación / oficina',''))
