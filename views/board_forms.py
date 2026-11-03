import streamlit as st
from services import board_moves
from views.common import managed_dialog,perform
from views.navigation import open_order

@managed_dialog('Mover tarjeta',width='medium')
def board_move_form(order_id,target,expected_token):
    order=next((o for o in st.session_state['snapshot']['orders'] if o['id']==order_id),None)
    if not order:
        st.error('El pedido ya no existe.');return
    st.text(f"{order['code']} · {order['project']}")
    st.caption(f"Destino: {target}")
    job_id=None
    try:
        if board_moves.token(order)!=expected_token: raise ValueError('El pedido cambió. Actualiza el tablero antes de moverlo.')
        plan=board_moves.proposal(order,target)
    except ValueError as exc:
        st.info(str(exc))
        if st.button('Abrir pedido para continuar',key='board_move_open',icon=':material/arrow_forward:'):
            st.session_state.pop('active_dialog',None);open_order(order_id)
        return
    st.write(plan['detail'])
    finished=()
    if plan['action']=='launch':
        if st.button(plan['label'],key='board_move_launch',type='primary',icon=':material/rocket_launch:'):
            from views.capture_forms import new_print_form
            new_print_form(order_id=order_id,purpose='Prototipo')
        return
    if plan['action']=='close_project':
        for job in plan['started']:
            st.caption(f"Se termina · {job['code']} · {job['part_name']} · {job['quantity']} piezas")
        if plan['pending']:
            pending={j['id']:j for j in plan['pending']}
            finished=st.multiselect('Impresiones en cola que sí se hicieron',list(pending),key='board_move_done_'+st.session_state['dialog_request_key'],
                format_func=lambda i:f"{pending[i]['code']} · {pending[i]['part_name']} · {pending[i]['quantity']} piezas",
                placeholder='Ninguna: se descartan')
            dropped=len(pending)-len(finished)
            if dropped: st.warning(f'{dropped} impresión(es) en cola se descartan y liberan su máquina y su filamento.',icon=':material/delete_sweep:')
    if plan['action']=='start':
        jobs={j['id']:j for j in plan['jobs']}
        job_id=st.selectbox('Trabajo que inicia',list(jobs),key='board_move_job_'+st.session_state['dialog_request_key'],
            format_func=lambda i:f"{jobs[i]['code']} · {jobs[i]['part_name']} · {jobs[i]['machine_code'] or 'Sin máquina'} · {jobs[i]['quantity_remaining']} pendientes")
    if st.button(plan['label'],key='board_move_confirm',type='primary',icon=':material/check:'):
        perform(board_moves.apply,order_id,target,expected_token=expected_token,job_id=job_id,finished=finished,
            request_key=st.session_state['dialog_request_key'],message=f"{'Prototipo' if order.get('development') else 'Pedido'} actualizado · {plan['label']}.")
