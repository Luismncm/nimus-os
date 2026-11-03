"""Manufacturing, procurement and fulfillment remain independent controls."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from tests import test_origin as fixture
import db
from services import recipes as r, production as p, origin, operations, inventory, order_board, board_moves
from services.queries import load_snapshot, dashboard
from services.daily import daily_board
from services.workflow import next_step
from services.order_progress import fabrication_label, display_status


class ManufacturingProgressTest(unittest.TestCase):
    setUp = fixture.OriginTest.setUp
    publish = fixture.OriginTest.publish
    get_order = fixture.OriginTest.get_order
    receive = fixture.OriginTest.receive

    def order(self, quantity=1, **kwargs):
        return r.create_recipe_order(self.rid, quantity, client='Cliente prueba', **kwargs)

    def finish(self, oid):
        for part in self.get_order(oid)['items'][0]['parts']:
            p.job_action(p.create_job(part['id'], part['quantity_required']), 'finish')

    def cover_supplies(self, oid, qty=1):
        for cid in self.supplies.values():
            self.receive(cid, qty)
        origin.reserve_supplies(oid)

    def test_purchases_never_advance_manufacturing_or_start_its_stage(self):
        oid = self.order()
        self.cover_supplies(oid)
        o = self.get_order(oid)
        self.assertEqual((o['manufacturing']['required'], o['manufacturing']['progress']), (4, 0))
        self.assertEqual((o['supplies']['required'], o['supplies']['covered']), (3, 3))
        self.assertEqual(o['status'], 'Pendiente')
        self.assertEqual(order_board.tracking(o)['lane'], 'Planificar')
        self.assertEqual(dashboard(load_snapshot())['metrics']['pending_units'], 4)
        # Even a historical stored status cannot make inventory look like active work.
        o['status'] = 'En producción'
        self.assertEqual(order_board.tracking(o)['lane'], 'Planificar')
        self.assertEqual(display_status(o), 'Pendiente')
        part = o['items'][0]['parts'][0]
        p.job_action(p.create_job(part['id'], 1), 'finish')
        self.assertEqual(self.get_order(oid)['manufacturing']['progress'], 25)

    def test_printing_can_finish_while_supplies_block_every_exit_path(self):
        oid = self.order()
        self.finish(oid)
        o = self.get_order(oid)
        self.assertEqual(o['manufacturing']['progress'], 100)
        self.assertEqual(o['remaining_total'], 3)  # full coverage retained for delivery/costs
        self.assertEqual(o['supplies']['remaining'], 3)
        self.assertEqual(next_step(o)['action'], 'supplies')
        t = order_board.tracking(o)
        self.assertEqual((t['lane'], t['complete'], t['manufacturing_complete']), ('Preparar', False, True))
        self.assertEqual(display_status(o), 'Insumos pendientes')
        item = o['items'][0]
        operations.update_item(item['id'], checked=True, expected_revision=0)
        for stage in operations.STAGES:
            operations.set_stage(oid, stage, True, expected_revision=0)
        with self.assertRaises(ValueError):
            p.deliver_order(oid)
        with self.assertRaises(ValueError):
            board_moves.proposal(self.get_order(oid), 'Salida')
        self.assertIn('Insumos pendientes', daily_board(load_snapshot())['attention'][0]['reasons'])
        self.cover_supplies(oid)
        o = self.get_order(oid)
        self.assertEqual(order_board.tracking(o)['lane'], 'Salida')
        p.deliver_order(oid)
        delivered = self.get_order(oid)
        self.assertEqual(delivered['status'], 'Entregado')
        self.assertEqual(delivered['manufacturing']['progress'], 100)
        self.assertEqual(delivered['supplies']['covered'], 3)  # consumed reservations stay covered

    def test_existing_printed_pieces_are_separate_and_only_shortages_count(self):
        self.receive(self.shade, 1)
        oid = self.order(2)
        o = self.get_order(oid)
        self.assertEqual((o['manufacturing']['required'], o['manufactured_from_stock']), (7, 1))
        self.assertEqual(o['manufacturing']['completed'], 0)
        self.assertEqual((o['supplies']['required'], o['required_total']), (6, 14))
        self.finish(oid)
        o = self.get_order(oid)
        self.assertEqual(o['manufacturing']['progress'], 100)
        self.assertEqual(o['supplies']['covered'], 0)
        self.assertEqual(o['manufactured_from_stock'], 1)

    def test_all_printed_parts_from_inventory_show_no_manufacturing_required(self):
        for line in r.quote_order(self.rid, 1)['lines']:
            if line['supply'] == 'Fabricar':
                self.receive(line['component_id'], 1)
        oid = self.order()
        o = self.get_order(oid)
        self.assertFalse(o['manufacturing']['applicable'])
        self.assertTrue(o['manufacturing']['complete'])
        self.assertIsNone(o['manufacturing_progress'])
        self.assertEqual(fabrication_label(o), 'Sin fabricación requerida')
        self.assertEqual((o['manufactured_from_stock'], o['supplies']['remaining']), (4, 3))
        self.assertEqual(order_board.tracking(o)['lane'], 'Preparar')
        with self.assertRaises(ValueError):
            p.deliver_order(oid)

    def test_purchased_only_recipe_never_displays_zero_over_zero_manufacturing(self):
        pid = r.create_product('Kit eléctrico', collection='Origen')
        rid = r.publish_recipe(pid, [dict(component_id=c, quantity=1) for c in self.supplies.values()])
        oid = r.create_recipe_order(rid, 2, client='Cliente')
        o = self.get_order(oid)
        self.assertEqual((len(o['items'][0]['parts']), o['supplies']['required']), (0, 6))
        self.assertEqual(fabrication_label(o), 'Sin fabricación requerida')
        self.assertEqual(next_step(o)['action'], 'supplies')

    def test_manual_items_are_weighted_by_pieces_and_undefined_items_do_not_complete(self):
        oid = p.create_order('Pedido personalizado')
        i1 = p.create_item(oid, 'Producto A', 1)
        i2 = p.create_item(oid, 'Producto B', 1)
        part = p.create_part(i1, 'Pieza A', 2, 'Impresión 3D')
        p.job_action(p.create_job(part, 2), 'finish')
        o = self.get_order(oid)
        self.assertFalse(o['manufacturing']['complete'])
        self.assertEqual(o['undefined_items'], 1)
        p.create_part(i2, 'Pieza B', 6, 'Producción externa')
        o = self.get_order(oid)
        self.assertEqual(o['manufacturing']['progress'], 25)
        self.assertEqual(o['supplies']['required'], 0)
        self.assertEqual(o['manufacturing']['required'], 8)

    def test_inventory_filter_finds_supply_shortages_without_changing_manufacturing(self):
        waiting = self.order()
        covered = self.order()
        self.cover_supplies(covered)
        rows = order_board.query(load_snapshot()['orders'], attention='Insumos pendientes')
        self.assertEqual([o['id'] for o in rows], [waiting])
        self.assertEqual(rows[0]['manufacturing']['progress'], 0)

    def test_snapshot_reads_do_not_reclassify_or_change_stored_records(self):
        oid = self.order()
        self.finish(oid)
        def values():
            with db.connect() as conn:
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                return {t: [tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
        before = values()
        for _ in range(2):
            daily_board(load_snapshot())
        self.assertEqual(values(), before)

    def test_native_order_ui_separates_tables_and_reserves_without_moving_bar(self):
        oid = self.order()
        self.finish(oid)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'), default_timeout=30).run()
        app.switch_page('views/orders.py').run()
        app.session_state['open_order_id'] = oid
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.button(key=f'order_step_next_{oid}').label, 'Gestionar insumos')
        app.button(key=f'order_step_next_{oid}').click().run()
        self.assertEqual(app.session_state[f'order_detail_tabs_{oid}'], 'Insumos')
        frames = [d.value for d in app.dataframe]
        purchased = next(d for d in frames if 'Insumo' in d.columns)
        self.assertEqual(len(purchased), 3)
        # Manufactured pieces are the product's piece list; purchased supplies never appear in it.
        self.assertTrue(any(m.value.startswith('**Piezas · 4**') for m in app.markdown))
        for name in purchased['Insumo']:
            self.assertFalse(any(m.value.startswith(f'**{name}**') for m in app.markdown), name)
        self.assertTrue(any(m.label == 'Por fabricar' and m.value == '0' for m in app.metric))
        for cid in self.supplies.values(): self.receive(cid, 1)
        app.run()
        app.button(key=f'order_supplies_{oid}').click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(self.get_order(oid)['supplies']['remaining'], 0)
        self.assertEqual(self.get_order(oid)['manufacturing']['progress'], 100)
        self.assertEqual(app.button(key=f'order_step_next_{oid}').label, 'Continuar preparación')
