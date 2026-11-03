"""Create development projects; their prints are launched with the shared Nueva impresión window."""
import streamlit as st
from models.constants import PRIORITIES
from services import development, consumables
from services.catalog import saved_values
from views.common import managed_dialog, perform
from views.common import request_key as _key


@managed_dialog('Proyecto de desarrollo', width='medium')
def project_form(row=None):
    prefix = 'dev_project_' + _key()
    info = row['development'] if row else {}
    with st.form(prefix):
        name = st.text_input('Nombre del proyecto *', value=row['project'] if row else '', disabled=bool(row), key=prefix + '_name',
                             placeholder='Prototipo lámpara Nimbus, pruebas de tolerancia, plantilla de ensamble…')
        goal = st.text_area('Objetivo', value=info.get('goal', ''), key=prefix + '_goal', placeholder='Qué se quiere validar con estas impresiones')
        a, b = st.columns(2)
        budget = a.number_input('Presupuesto · MXN sin IVA (opcional)', min_value=0.0, step=100.0, key=prefix + '_budget',
                                value=info['budget_cents'] / 100 if info.get('budget_cents') is not None else None)
        priority = b.selectbox('Prioridad en la cola', PRIORITIES, index=PRIORITIES.index(row['priority']) if row else 1, key=prefix + '_priority', disabled=bool(row))
        st.caption('Sus impresiones usan máquinas, filamento e insumos y tienen costo real, pero no son ventas ni entregas a clientes.')
        if st.form_submit_button('Guardar proyecto', type='primary', width='stretch'):
            if row:perform(development.update_project, row['id'], goal=goal, budget=budget, message='Proyecto actualizado.')
            else:perform(development.create_project, name, goal=goal, budget=budget, priority=priority, message='Proyecto creado. Ya puedes lanzar sus impresiones.')


def materials():
    names = [r['name'] for r in consumables.items([]) if r['unit'] == 'g']
    return list(dict.fromkeys([*names, *saved_values('material')]))
