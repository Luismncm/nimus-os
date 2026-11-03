import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import db
from services import production as s
from services.queries import load_snapshot
from tests.ui_helpers import enter_option


class UITest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env=patch.dict(os.environ,{"NIMUS_DB_PATH":str(Path(self.temp.name)/"ui.db")})
        self.env.start()
        self.addCleanup(self.env.stop)
        db.init_db()
        self.app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=15)

    def assert_clean(self):
        self.assertFalse(self.app.exception,[e.message for e in self.app.exception])

    def click_label(self,label):
        next(button for button in self.app.button if button.label == label).click().run()
        self.assert_clean()

    def seed(self):
        order=s.create_order("Prueba","Cliente","2026-10-05","Alta")
        item=s.create_item(order,"Lámpara",10)
        part=s.create_part(item,"Base",10,"Impresión 3D")
        job=s.create_job(part,4,1)
        s.create_job(part,6,2)
        return order,item,part,job

    def test_empty_all_four_pages(self):
        self.app.run()
        self.assert_clean()
        for path in ("views/orders.py","views/queue.py","views/machines.py","views/today.py"):
            self.app.switch_page(path).run()
            self.assert_clean()

    def test_running_job_all_views_and_quick_actions(self):
        order,item,part,job=self.seed()
        s.job_action(job,"start")
        self.app.run()
        self.assert_clean()
        self.assertTrue(any('Pedidos por atender' in h.value for h in self.app.subheader))  # Hoy opens on its summary.
        for path in ("views/orders.py","views/queue.py","views/machines.py"):
            self.app.switch_page(path).run()
            self.assert_clean()
        # Máquinas is equipment only: its card reads the work and leads to the queue, where prints are operated.
        self.assertFalse(any(b.key.startswith(("machine_pause_","machine_start_","machine_finish_")) for b in self.app.button if b.key))
        self.app.button(key="machine_queue_1").click().run()
        self.assert_clean()
        # AppTest needs its selected page updated for subsequent runs after st.switch_page.
        self.app.switch_page("views/queue.py").run()
        self.assertEqual(self.app.selectbox(key="queue_machine").value,1)
        self.app.session_state["queue_view"]="Tabla";self.app.run()
        self.app.button(key=f"queue_{job}_pause").click().run()
        self.assert_clean()
        self.assertEqual(load_snapshot()["machines"][0]["status"],"Disponible")
        self.app.button(key=f"queue_{job}_start").click().run()
        self.assert_clean()
        self.app.button(key=f"queue_{job}_finish").click().run()
        self.assert_clean()
        self.assertEqual(load_snapshot()["orders"][0]["progress"],40)

    def test_queue_filters_and_edit_dialog(self):
        self.seed()
        self.app.run().switch_page("views/queue.py").run()
        self.app.selectbox(key="queue_machine").set_value(1).run()
        self.assert_clean()
        self.app.session_state["queue_view"] = "Tabla"
        self.app.run()
        self.assertEqual(len(self.app.dataframe[0].value),1)
        self.app.button(key="queue_1_edit").click().run()
        self.assert_clean()
        self.app.number_input(key="job_completed_1").set_value(2)
        self.click_label("Guardar trabajo")
        self.assertEqual(load_snapshot()["orders"][0]["progress"],20)

    def test_clear_filters_restores_active_jobs(self):
        self.seed()
        self.app.run().switch_page("views/queue.py").run()
        self.app.session_state["queue_view"] = "Tabla"
        self.app.selectbox(key="queue_machine").set_value(1)
        self.app.selectbox(key="queue_process").set_value("Ensamble").run()
        self.assert_clean()
        self.assertFalse(self.app.dataframe)
        self.app.button(key="queue_reset").click().run()
        self.assert_clean()
        self.assertEqual(self.app.selectbox(key="queue_machine").value, "Todas")
        self.assertEqual(self.app.selectbox(key="queue_process").value, "Todos")
        self.assertEqual(len(self.app.dataframe[0].value), 2)

    def test_material_is_saved_and_reused_in_single_and_batch_parts(self):
        self.seed()
        self.app.run().switch_page("views/orders.py").run()
        self.app.button_group(key='orders_view').set_value('Lista').run()
        self.app.button(key="orders_open_1").click().run()
        self.app.button(key="item_add_part_1").click().run()
        enter_option(self.app, "part_name", "Pantalla")
        enter_option(self.app, "part_material", " PETG   marfil ")
        self.click_label("Guardar pieza")
        self.assertEqual(load_snapshot()['parts'][-1]['material'], 'PETG marfil')
        self.app.button(key="item_parts_1").click().run()
        self.assertIn('PETG marfil', self.app.selectbox(key='parts_material_1').options)
        self.app.selectbox(key='parts_material_1').set_value('PETG marfil')
        self.app.text_area(key='parts_names_1').set_value('Tapa\nSoporte')
        self.app.button(key='parts_save').click().run()
        self.assert_clean()
        self.assertEqual([row['material'] for row in load_snapshot()['parts'][-2:]], ['PETG marfil', 'PETG marfil'])

    def test_create_entire_order_through_dialogs(self):
        self.app.run().switch_page("views/orders.py").run()
        self.click_label("Nuevo pedido")
        self.app.text_input(key="order_project").set_value("Nuevo proyecto")
        enter_option(self.app, "order_client", "Cliente")
        self.click_label("Guardar pedido")
        self.app.button(key="order_add_item_1").click().run()
        enter_option(self.app, "item_name", "Lámpara")
        self.app.number_input(key="item_quantity").set_value(10)
        self.click_label("Guardar producto")
        self.app.button(key="item_add_part_1").click().run()
        enter_option(self.app, "part_name", "Base")
        self.assertEqual(self.app.number_input(key="part_quantity").value,10)
        self.click_label("Guardar pieza")
        # Assigning a piece opens the order's Asignar view with that piece picked.
        self.app.button(key="part_split_1").click().run()
        self.assert_clean()
        self.assertEqual(self.app.session_state["order_production_view_1"], "Asignar")
        self.app.number_input(key="order_assign_1_1_v0_units").set_value(4)
        self.app.button(key="order_assign_1_1_v0_save").click().run()
        self.assert_clean()
        result=load_snapshot()
        self.assertEqual(result["jobs"][0]["quantity"],4)
        self.assertEqual(result["parts"][0]["quantity_unassigned"],6)

    def test_batch_parts_split_and_progress_from_cards(self):
        order = s.create_order("Despiece rápido", "Cliente")
        s.create_item(order, "Lámpara", 10)
        self.app.run().switch_page("views/orders.py").run()
        self.app.button_group(key='orders_view').set_value('Lista').run()
        self.app.button(key="orders_open_1").click().run()
        self.assert_clean()
        self.app.button(key="item_parts_1").click().run()
        self.app.text_area(key="parts_names_1").set_value("Base\nPantalla\nTapa\nPlaca")
        self.app.button(key="parts_save").click().run()
        self.assert_clean()
        self.assertEqual(load_snapshot()["orders"][0]["required_total"], 40)
        self.app.button(key="part_split_1").click().run()
        self.app.button(key="order_assign_1_split_1").click().run()
        self.assertEqual(self.app.button_group(key="split_mode_1").value, "Repartir en varias")
        self.app.number_input(key="split_1_1").set_value(4)
        self.app.number_input(key="split_1_2").set_value(4)
        self.app.number_input(key="split_1_3").set_value(2).run()
        self.app.button(key="split_save").click().run()
        self.assert_clean()
        self.assertEqual([j["quantity"] for j in load_snapshot()["jobs"]], [4, 4, 2])
        self.app.button(key="order_jobs_1").click().run()
        self.assertEqual(self.app.selectbox(key="queue_project").value, order)
        # AppTest needs its selected page updated for subsequent runs after st.switch_page.
        self.app.switch_page("views/queue.py").run()
        self.app.button(key="queue_1_start").click().run()
        self.assert_clean()
        self.app.button(key="queue_1_progress").click().run()
        self.app.number_input(key="progress_total_1").set_value(2)
        self.click_label("Registrar avance")
        self.assertEqual(load_snapshot()["orders"][0]["progress"], 5)

    def test_even_split_oversubscription_guard_and_machine_focus(self):
        order = s.create_order("Reparto")
        item = s.create_item(order, "Objeto", 10)
        part = s.create_part(item, "Base", 10, "Impresión 3D")
        s.update_machine(4, "Mantenimiento")
        self.app.run()
        # Hoy sends the piece to its order's Asignar view; splitting between printers starts there.
        self.app.button(key="today_split_1").click().run()
        self.app.switch_page("views/orders.py").run()
        self.assertEqual((self.app.session_state["order_production_view_1"], self.app.session_state["order_assign_1_piece"]), ("Asignar", part))
        self.app.button(key="order_assign_1_split_1").click().run()
        self.app.button_group(key="split_mode_1").set_value("Repartir en varias").run()
        self.click_label("Repartir entre máquinas disponibles")
        self.assertEqual([self.app.number_input(key=f"split_1_{mid}").value for mid in range(1, 5)], [4, 3, 3, 0])
        self.app.number_input(key="split_1_4").set_value(1).run()
        self.assertTrue(self.app.button(key="split_save").disabled)
        self.app.number_input(key="split_1_4").set_value(0).run()
        self.app.button(key="split_save").click().run()
        self.app.session_state["today_front"] = "Producir"
        self.app.session_state["today_production_mode"] = "Máquinas"
        self.app.switch_page("views/today.py").run()
        self.app.button(key="today_machine_queue_2").click().run()
        self.assert_clean()
        self.assertEqual(self.app.selectbox(key="queue_machine").value, 2)
        self.app.session_state["queue_view"] = "Tabla"
        self.app.switch_page("views/queue.py").run()
        self.assertEqual(len(self.app.dataframe[0].value), 1)


if __name__ == "__main__":
    unittest.main()
