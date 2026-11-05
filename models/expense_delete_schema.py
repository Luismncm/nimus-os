"""Let an expense be removed entirely, not just cancelled, when nothing outside its own ledger depends on it.

Cancelar keeps the row and its full history, for a gasto that still matters as a record (it just no
longer counts). Eliminar is for the opposite case: a duplicate, a test or a mistaken capture that
should leave no trace. The guard stays wherever something else would be left dangling: a partner's
coverage, a purchase order, an order's extra cost, or a row carried over from the historical import.
"""


def create_expense_delete_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS expense_delete_unlock (id INTEGER PRIMARY KEY CHECK(id=1))''')
    conn.execute('DROP TRIGGER IF EXISTS expense_keep')
    conn.execute('''CREATE TRIGGER expense_keep BEFORE DELETE ON expenses
        WHEN NOT EXISTS(SELECT 1 FROM expense_delete_unlock)
          OR EXISTS(SELECT 1 FROM partner_expense_settlements WHERE expense_id=OLD.id)
          OR EXISTS(SELECT 1 FROM inventory_inbound_expenses WHERE expense_id=OLD.id)
          OR EXISTS(SELECT 1 FROM order_extra_costs WHERE expense_id=OLD.id)
          OR EXISTS(SELECT 1 FROM sheet_import_rows WHERE expense_id=OLD.id)
          OR EXISTS(SELECT 1 FROM capital_movements WHERE linked_expense_id=OLD.id)
        BEGIN SELECT RAISE(ABORT,'Cancela el gasto para conservar su historial.'); END''')
    conn.execute('DROP TRIGGER IF EXISTS expense_payment_keep')
    conn.execute('''CREATE TRIGGER expense_payment_keep BEFORE DELETE ON expense_payments
        WHEN NOT EXISTS(SELECT 1 FROM expense_delete_unlock)
        BEGIN SELECT RAISE(ABORT,'Anula el pago para conservar el historial.'); END''')
