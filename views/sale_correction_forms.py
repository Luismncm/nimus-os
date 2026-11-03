import streamlit as st
from services import sale_corrections as corrections, quotations as q
from views.common import managed_dialog,perform


def back_to_sales(_=None):
    st.session_state.pop('open_sale_id',None)
    st.session_state.pop('last_work_record',None)


@managed_dialog('Eliminar venta errónea',width='medium')
def delete_sale_form(sale):
    st.write(f"**{sale['code']} · {sale['client']} · {q.money(sale['total_cents'])} MXN**")
    st.caption('Se retirará del listado y los totales. Podrás recuperarla desde Papelera de ventas; su historial y documentos se conservan.')
    with st.form('sale_delete'):
        reason=st.text_input('Motivo *',placeholder='Duplicada, prueba, error de captura…')
        if st.form_submit_button('Mover a papelera',type='primary',width='stretch'):
            perform(corrections.remove_sale,sale['id'],reason,expected_revision=sale['revision'],after=back_to_sales,
                navigate='views/sales.py',message='Venta retirada. Puedes recuperarla desde Papelera de ventas.')


@managed_dialog('Eliminar partidas erróneas',width='large')
def remove_lines_form(sale):
    lines=sale['data']['lines']
    st.write(f"**{sale['code']} · {sale['client']}**")
    lock=corrections.line_lock(sale)
    if lock:
        st.info(lock)
        return
    indices=st.multiselect('Partidas a eliminar',list(range(len(lines))),format_func=lambda i:f"{i+1}. {lines[i]['description']} · {lines[i]['quantity']:g} × {q.money(q.cents(lines[i]['price']))}",key='sale_remove_indices')
    remaining=[r for i,r in enumerate(lines) if i not in indices]
    if remaining:
        new=q.calculate(dict(sale['data'],lines=remaining))
        st.write(f"Total actual: {q.money(sale['total_cents'])} → Total corregido: **{q.money(new['totals']['total'])} MXN**")
    else:st.warning('Para eliminar todas las partidas, usa Eliminar venta.')
    with st.form('sale_remove_lines'):
        reason=st.text_input('Motivo de la corrección *')
        if st.form_submit_button('Eliminar partidas seleccionadas',type='primary',width='stretch',disabled=not indices or not remaining):
            perform(corrections.remove_lines,sale['id'],indices,reason,expected_revision=sale['revision'],message='Partidas eliminadas y total recalculado.')
