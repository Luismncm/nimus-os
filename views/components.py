"""Small native Streamlit components shared across the workshop views."""
import re
import streamlit as st

from models.constants import MACHINE_STATUSES
from services import production as service
from services.workflow import due_label
from utils.dates import fmt
from views.common import deliver_dialog, job_actions, perform
from views.navigation import open_order, open_queue
from views.progress_ui import production_progress
from views.kind_style import order_chip, order_kind, order_tone
from services.order_progress import display_status


COLORS = {"En producción": "blue", "Imprimiendo": "blue", "Bloqueado": "red",
          "Disponible": "green", "Listo": "green", "Terminado": "green",
          "Entregado": "gray", "Pausado": "orange", "Mantenimiento": "orange",
          "Fuera de servicio": "red", "Listo para preparar": "green",
          "Insumos pendientes": "orange", "Componentes pendientes": "orange"}


def status_badge(status: str) -> None:
    from views.emoji import status as with_emoji
    st.badge(with_emoji(status), color=COLORS.get(status, "gray"))


def order_card(order: dict, key: str, *, controls: bool = False) -> None:
    from services.order_board import tracking
    t = order.get('tracking') or tracking(order)
    kind = order_kind(order)
    # The card's edge and its code chip share the order's color, so it is found again in the queue and in the prints.
    with st.container(border=True, gap='xsmall', key=f"panel-order-{order_tone(order['id'], kind)[0]}-{key}-{order['id']}"):
        with st.container(horizontal=True, horizontal_alignment='distribute', vertical_alignment='center'):
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                order_chip(order['code'], order['id'], kind, help=f"Pedido {order['code']} · {order['project']}")
                st.caption(order['client'] or 'Sin cliente asignado')
            st.badge('Prototipo' if kind == 'Prototipo' else 'Stock' if order.get('fulfillment') == 'Stock' else 'Cliente',
                     color='violet' if kind == 'Prototipo' else 'gray', icon=':material/science:' if kind == 'Prototipo' else None)
        # Escape user-entered punctuation before using a native Markdown emphasis.
        title = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', order['project'].replace('\n', ' '))
        st.markdown(f'**{title}**')
        # State, priority and delivery in one row: the date is said once.
        with st.container(horizontal=True, gap='xxsmall'):
            status_badge('Cancelado' if order.get('commercial_cancelled') else display_status(order))
            if order['priority'] == 'Alta': st.badge('Alta', color='orange', icon=':material/flag:')
            if t['delivered']:
                st.badge(f"Cierre {fmt(order['updated_at'])}", color='gray', icon=':material/event_available:')
            else:
                due, color = due_label(order['deadline'])
                st.badge(due, color=color, icon=':material/event:', help=f"Entrega {fmt(order['deadline'])} · prioridad {order['priority'].lower()}")
        production_progress(order)
        st.caption(' · '.join(x for x in (f"{t['products']} productos", f"{t['checked']}/{t['items']} revisados",
                                         f"{t['running']} en curso" if t['running'] else '', f"{t['unassigned']} piezas por asignar" if t['unassigned'] else '') if x))
        st.markdown(f":gray[Cancelación ·] {order['cancellation_reason']}" if order.get('commercial_cancelled') else f":material/arrow_right_alt: **{t['action']}**")
        with st.container(horizontal=True, gap='xsmall'):
            if st.button('Abrir', key=f"{key}_{order['id']}", icon=':material/arrow_forward:', icon_position='right', type='primary', width='stretch'):
                open_order(order['id'])
            if controls and kind == 'Prototipo':
                prototype_follow_up(order, t, key)
            elif controls and not t['delivered'] and not order.get('commercial_cancelled'):
                quick_follow_up(order, t, key)


def prototype_follow_up(order, t, key):
    """A project is followed by its prints: launch the next test, start one, finish and close, or reopen."""
    from services.board_moves import token
    from views.board_forms import board_move_form
    oid = order['id']
    if t['delivered']:
        if st.button('Reabrir', key=f"{key}_reopen_{oid}", icon=':material/lock_open:', width='stretch'):
            board_move_form(oid, 'Planificar', token(order))
        return
    if not t['jobs']:
        if st.button('Lanzar impresión', key=f"{key}_launch_{oid}", icon=':material/rocket_launch:', width='stretch'):
            from views.capture_forms import new_print_form
            new_print_form(order_id=oid, purpose='Prototipo')
        return
    jobs = [j for i in order['items'] for p in i['parts'] for j in p['jobs'] if j['status'] != 'Terminado']
    queued = sum(j['status'] in ('En cola', 'Pausado') for j in jobs)
    with st.popover('Seguimiento', icon=':material/checklist:', width='stretch'):
        st.caption(f"{order['code']} · {order['project']}")
        st.caption(f"{t['running']} imprimiendo · {queued} en cola · {t['jobs'] - len(jobs)} terminadas")
        if st.button('Lanzar impresión', key=f"{key}_launch_{oid}", icon=':material/rocket_launch:', width='stretch'):
            from views.capture_forms import new_print_form
            new_print_form(order_id=oid, purpose='Prototipo')
        if queued and st.button(f'Iniciar impresión · {queued} en cola', key=f"{key}_start_{oid}", icon=':material/play_arrow:', width='stretch'):
            board_move_form(oid, 'Producir', token(order))
        if st.button('Terminar y cerrar proyecto', key=f"{key}_close_{oid}", icon=':material/task_alt:', type='primary', width='stretch'):
            board_move_form(oid, 'Entregados', token(order))


def quick_follow_up(order, t, key):
    """Steps already done, date and delivery of an order, without opening it."""
    from views.operations import stage_actions, item_check
    from views.common import order_form
    with st.popover('Seguimiento', icon=':material/checklist:', width='stretch'):
        st.caption(f"{order['code']} · {order['project']}")
        st.caption('Registra únicamente pasos realizados. La columna se actualiza con producción y revisiones.')
        stage_actions(order, f'{key}_quick')
        for item in order['items']:
            item_check(item, False, f'{key}_quick')
        if st.button('Editar fecha y prioridad', key=f'{key}_edit_{order["id"]}', icon=':material/edit:'):
            order_form(order)
        if order['status'] == 'Listo':
            if t['pending']: st.caption('Revisiones pendientes: ' + ' · '.join(t['pending']))
            if st.button('Liberar a stock' if order.get('fulfillment') == 'Stock' else 'Confirmar entrega',
                         key=f'{key}_deliver_{order["id"]}', icon=':material/task_alt:'):
                deliver_dialog(order)


def job_card(job: dict, key: str, *, details: bool = False) -> None:
    from views.kind_style import card, kind_of
    kind = kind_of(job)
    with card(kind, f"job-{key}", gap='small', order_id=job['order_id']):
        a, b = st.columns([3, 2], vertical_alignment="center")
        with a:
            st.write(f"**{job['part_name']}** · {job['machine_code'] or 'Fuera de impresora'}")
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                order_chip(f"{job['order_code']} · {job['client'] or job['project']}", job['order_id'], kind, help=job['project'])
                st.caption(f"{job['code']} · {job['item_name']}")
        with b:
            with st.container(horizontal=True, gap="xsmall", horizontal_alignment="right"):
                status_badge(job["status"])
                if job["priority"] == "Alta":
                    st.badge("Alta", color="orange")
        st.progress(job["quantity_completed"] / job["quantity"],
                    text=f"{job['quantity_completed']}/{job['quantity']} terminadas · faltan {job['quantity_remaining']}")
        if details:
            st.caption(f"{job['process']} · Entrega {fmt(job['deadline'])} · Fin estimado {fmt(job.get('estimated_finish') or job['expected_end'], time=True)}")
            if job["notes"]:
                st.caption(job["notes"])
        if job.get('collection') and job['process'] in ('Impresión 3D', 'Resina'):
            st.caption('Destino de las unidades buenas: Inventario colección · Origen')
        if job.get('planned_start') or job.get('duration_minutes') or job.get('estimated_grams') is not None:
            duration=job.get('duration_minutes')
            grams=job.get('estimated_grams')
            st.caption(f"Inicio programado: {fmt(job.get('planned_start'),time=True)} · Duración: {duration or 'Pendiente'} min · Material: {f'{grams:g} g' if grams is not None else 'Pendiente'}")
        job_actions(job, key)
        if job.get('order_status')!='Entregado' and not job.get('commercial_cancelled'):
            from views.planning_forms import planning_form
            if st.button('Programar / consumos',key=key+'_plan',icon=':material/calendar_month:',type='tertiary'): planning_form(job)


def machine_card(machine: dict, manage=None) -> None:
    """One printer as equipment: what it does now and next, its availability and notes, and the way to its queue.

    Starting, pausing and finishing prints happen in one place, the queue (and Hoy or the order for a single
    print), so this card reads the work instead of repeating its buttons. manage draws the card's setup actions.
    """
    mid = machine["id"]
    with st.container(border=True, height='stretch'):
        a, b = st.columns([2, 3], vertical_alignment="center")
        a.subheader(machine["code"])
        a.caption(machine["name"])
        with b:
            status_badge(machine["status"])
        current, nxt = machine["current_job"], machine["next_job"]
        st.caption("AHORA")
        if current:
            st.write(f"**{current['part_name']}**")
            st.caption(f"{current['code']} · {current['project']}")
            st.progress(current["quantity_completed"] / current["quantity"], text=f"{current['quantity_completed']}/{current['quantity']} terminadas")
            st.caption(f"Fin estimado · {fmt(current['expected_end'], time=True)}")
        else:
            st.write("**Sin trabajo en curso**")
        st.caption("SIGUIENTE")
        if nxt:
            st.write(f"**{nxt['part_name']} ×{nxt['quantity_remaining']}**")
            st.caption(f"{nxt['code']} · {nxt['project']} · Prioridad {nxt['priority']}")
        else:
            st.caption("Sin siguiente trabajo. Asigna piezas desde un pedido o la cola.")
        st.caption(f"Carga asignada · {machine['pending_units']} unidades pendientes")
        if machine["notes"]:
            st.caption(machine["notes"])
        with st.popover("Disponibilidad y notas", icon=":material/settings:", width="stretch"):
            with st.form(f"machine_settings_{mid}"):
                state = st.selectbox("Estado", MACHINE_STATUSES, index=MACHINE_STATUSES.index(machine["status"]), key=f"machine_status_{mid}")
                notes = st.text_area("Notas", value=machine["notes"], key=f"machine_notes_{mid}")
                if st.form_submit_button("Guardar máquina", type="primary"):
                    perform(service.update_machine, mid, state, notes)
        # The one way to operate it: its queue, already filtered to this printer.
        if st.button("Operar en la cola", key=f"machine_queue_{mid}", width="stretch",
                     type="primary" if current or nxt else "secondary", icon=":material/play_circle:"):
            open_queue(machine_id=mid)
        if manage:
            manage()
