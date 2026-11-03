"""NIMUS OS: shared navigation and the workshop's existing operational views."""
import sqlite3
import time
from pathlib import Path
import streamlit as st
from db import init_db
from services.queries import load_snapshot
from views.common import render_dialog
from views.sidebar_attention import render_panel
# Form modules are imported for their dialogs, so any page can open them.
from views import collection_forms, catalog_forms, machine_forms, quotation_forms, sales_forms, expense_forms, treasury_forms, reconciliation_forms, invoice_forms, sale_correction_forms, planning_forms, costing_forms, partner_forms
from views import quality_forms, expense_control_forms, cash_projection_ui, spending_plan_forms, purchase_forms
from views import photo_forms, board_forms, origin_forms, commerce_ui, assign_forms, consumables_ui, development_forms, capture_forms, shell

brand=Path(__file__).resolve().parent/'assets'/'brand'
st.set_page_config(page_title='NIMUS · OS',page_icon=str(brand/'originals'/'ni.png'),layout='wide')
st.logo(str(brand/'nimus-light.svg'),size='large',icon_image=str(brand/'ni-dark.svg'))
from views.theme import inject as inject_theme
inject_theme()
try:
    init_db()
    snapshot=load_snapshot()
except (RuntimeError,sqlite3.DatabaseError,OSError) as exc:
    st.error(f'No se pudo abrir NIMUS: {exc}')
    st.stop()
st.session_state.update(snapshot=snapshot,snapshot_loaded_at=time.monotonic())
if flash:=st.session_state.pop('flash',None):st.toast(flash,icon=':material/check_circle:')
page=shell.navigation()
current=shell.sidebar(page,snapshot)
# Each environment has its own accent: the page follows its area (or Colección Origen), the sidebar its switch.
from views.theme import environment
environment(current['area'],st.session_state.get('shell_area') or current['area'],origin=current['key']=='origen')
render_panel()
shell.header(page,current,snapshot)
render_dialog()
page.run()
