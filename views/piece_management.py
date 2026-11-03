"""One row per piece: what it is, how far it is and the one action it needs now."""
import re
import streamlit as st
from services.order_progress import piece_rows, breakdown
from services.timeline import slot, issues
from views.common import job_actions, part_form, delete_dialog
from views.components import status_badge
from views.progress_ui import stacked_bar, breakdown_text
from views.timeline_ui import slot_line, schedule_tag
from views.kind_style import card, kind_of
from views.navigation import focus_assign
from views.tags import extra_tag, printer_tag

# Recipe orders note every piece this way; the product name already carries the variant.
AUTO_NOTE=re.compile(r'Faltante de receta( · .*)?')


def visible_rows(item, search=''):
    term=search.strip().casefold()
    rows=piece_rows(item)
    if not term or term in f"{item['name']} {item.get('label','')}".casefold(): return rows
    return [r for r in rows if term in f"{r['name']} {r['material']} {r['process']}".casefold()]


def piece_list(item, rows, *, readonly, recipe_order, snapshot):
    """The pieces of a product as cards, three across: each one shows its state and its one action."""
    parts={p['id']:p for p in item['parts']}
    focus=st.session_state.pop('focus_part_id',None)
    pending=sum(r['unassigned'] for r in rows)
    st.markdown(f"**Piezas · {len(rows)}**" + (f" :orange[· {pending} unidades sin asignar]" if pending else ''))
    for start in range(0,len(rows),3):
        for col,row in zip(st.columns(3,gap='small'),rows[start:start+3]):
            with col:
                piece_card(row,parts.get(row['part_id']),item,readonly=readonly,recipe_order=recipe_order,snapshot=snapshot,new=row['part_id']==focus)


def piece_card(row, part, item, *, readonly, recipe_order, snapshot, new=False):
    """Name, one bar, where the units are, the action it needs and its prints folded under it."""
    with st.container(border=True,gap='xsmall',key=f"panel-piece-{item['id']}-{row['part_id'] or 'r'+str(row['requirement_id'])}"):
        st.markdown(f"**{row['name']}**" + (' :blue-badge[Nueva]' if new else ''))
        st.caption(' · '.join(x for x in (row['material'],row['process'],row['code'] if part else '') if x))
        if not part:
            st.caption(f":material/warehouse: {row['from_stock']}/{row['required']} cubiertas desde inventario · no se fabrica")
        else:
            b=breakdown(part)
            stacked_bar(b,caption=False)
            st.caption(breakdown_text(b)+(f" · {row['from_stock']} de inventario" if row['from_stock'] else ''))
            if part['quantity_unassigned']>0:
                # Before assigning a print: the same piece may already be in inventory or printing as another job's extra.
                if part.get('stock_free') or part.get('stock_incoming'):
                    st.caption(':blue['+' · '.join(x for x in (f":material/inventory_2: {part['stock_free']} en inventario" if part.get('stock_free') else '',
                                                               f":material/local_shipping: {part['stock_incoming']} en camino" if part.get('stock_incoming') else '') if x)+']')
                else:st.caption(':gray[:material/inventory_2: Sin inventario: hay que imprimirla]')
        with st.container(horizontal=True,vertical_alignment='center',gap='xsmall'):
            piece_action(part,readonly)
            if part and not readonly and not recipe_order:
                with st.popover('Opciones',icon=':material/more_vert:',type='tertiary',help=f"Más opciones de {row['name']}"):
                    if not recipe_order and st.button('Editar pieza',key=f"part_edit_{part['id']}",icon=':material/edit:',width='stretch'):
                        part_form(item,part)
                    if not recipe_order and st.button('Eliminar pieza',key=f"part_delete_{part['id']}",icon=':material/delete:',width='stretch'):
                        delete_dialog('part',part)
        if part and part['notes'] and not AUTO_NOTE.fullmatch(part['notes']):st.caption(part['notes'])
        if part and part['jobs']:
            active=[j for j in part['jobs'] if j['status']!='Terminado']
            done=[j for j in part['jobs'] if j['status']=='Terminado']
            if active:
                # One fold per piece; it opens by itself while something is printing.
                with st.expander(f"{len(active)} {'impresión' if len(active)==1 else 'impresiones'}",icon=':material/print:',
                                 expanded=any(j['status']=='En producción' for j in active)):
                    for job in active:job_line(job)
            if done:st.caption(':material/check_circle: '+' · '.join(f"{j['code']} {'de inventario' if j.get('from_stock') else j['machine_code'] or 'sin máquina'} ×{j['quantity']}"+(f" +{j['extra']} a inventario" if j.get('extra') else '') for j in done)+' · terminados')


def job_line(job):
    """Machine, units, state, time and actions of one print of the piece, stacked to fit a card."""
    s=slot(job)
    with card(kind_of(job),f"piece-job-{job['id']}",order_id=job['order_id']):
        with st.container(horizontal=True,gap='xsmall',vertical_alignment='center'):
            printer_tag(next((m for m in st.session_state['snapshot']['all_machines'] if m['id']==job['machine_id']),None))
            st.markdown(f"{job['quantity_completed']}/{job['quantity']} u. :gray[· {job['code']}]")
            status_badge(job['status'])
            schedule_tag(s)
            extra_tag(job)
        problems=issues(s)
        st.caption(f":material/schedule: {slot_line(s)}"+(f"  \n:red[:material/warning: {problems[0]}]" if problems else ''))
        job_actions(job,f"order_status_job_{job['id']}")


def piece_action(part, readonly):
    """The single thing this piece needs now, or its state when nothing is needed."""
    if not part:
        st.badge('Cubierta',color='green',icon=':material/check:')
    elif part['quantity_remaining']==0:
        st.badge('Terminada',color='green',icon=':material/check:')
    elif not readonly and part['quantity_unassigned']>0:
        st.button(f"Asignar {part['quantity_unassigned']}",key=f"part_split_{part['id']}",icon=':material/call_split:',on_click=focus_assign,args=(part,),
                  help=f"Abre la vista Asignar con {part['name']} elegida: impresora, horario, notas o reparto entre varias.")
    else:
        st.badge('Asignada',color='blue',icon=':material/schedule:')


def order_prints(order, snapshot, dest, *, readonly):
    """The order's own queue: every print grouped by machine, with the same line as the production queue."""
    from services.timeline import machine_timeline, availability_text
    from views.queue_board import operate_row
    jobs=[j for i in order['items'] for p in i['parts'] for j in p['jobs']]
    active=[j for j in jobs if j['status']!='Terminado']
    pending=sum(p['quantity_unassigned'] for i in order['items'] for p in i['parts'])
    with st.container(horizontal=True,gap='small',vertical_alignment='center'):
        if not readonly:
            if st.button('Nueva impresión',key=f"order_new_print_{order['id']}",type='primary',icon=':material/add_task:',
                         help='Pieza existente por asignar o pieza nueva, con máquina, duración y horario.'):
                from views.capture_forms import new_print_form
                new_print_form(order_id=order['id'])
            # Pending pieces are assigned from the order's header (Repartir piezas), each product or the Asignar view.
            if pending:st.caption(f':orange[{pending} unidades sin asignar] · repártelas desde la vista Asignar')
        st.caption(f"{len(active)} impresiones abiertas · {sum(j['status']=='En producción' for j in active)} en marcha · {len(jobs)-len(active)} terminadas")
    if not active:
        st.info('Sin impresiones abiertas. Asigna las piezas pendientes o agrega una impresión.', icon=':material/print:')
    groups={}
    for job in active:groups.setdefault(job['machine_id'],[]).append(job)
    machines={m['id']:m for m in snapshot['all_machines']}
    for mid,own in sorted(groups.items(),key=lambda g:(g[0] is None,machines[g[0]]['code'] if g[0] in machines else '')):
        m=machines.get(mid)
        st.markdown(f"**{m['code']}** :gray[· {availability_text(machine_timeline(m,snapshot['jobs'])['availability'])}]" if m else '**Sin máquina / externo**')
        for job in sorted(own,key=lambda j:(j['status']!='En producción',j.get('planned_start') or '9999',j['id'])):operate_row(job,dest,'order')
    done=[j for j in jobs if j['status']=='Terminado']
    if done:
        st.caption(':material/check_circle: Terminadas · '+' · '.join(f"{j['code']} {j['part_name']} ×{j['quantity']} ({j['machine_code'] or 'sin máquina'})" for j in done))
