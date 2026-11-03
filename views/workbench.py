import streamlit as st
from services import sales,expenses,operations
from services.quotations import money
from services.workbench import operating_board,visible,urgency
from views.common import perform,order_form,deliver_dialog
from services import production
from views.components import job_card,status_badge
from views.sales_forms import direct_sale_form,sale_payment_form
from views.expense_forms import expense_form,expense_payment_form
from views.catalog_forms import recipe_order_form
from views.operations import order_checklist
from views.navigation import open_order,open_queue,open_assign
from views.kind_style import order_chip,order_kind,order_tone
from views.work_context import continue_button,open_record
from views.today_summary import summary
from services.order_board import tracking
from services.supply_board import board as supply_board
from views.supply_ui import supply_row
from utils.dates import fmt
from views.common import remembered
from views.emoji import tag


def reset_today_filters():
    st.session_state.update(today_search='', today_scope='Todos')


def workbench(snapshot):
    board=operating_board(snapshot,sales.list_sales(),expenses.list_expenses())
    daily=board['daily']
    supply=supply_board(snapshot['jobs'])
    from views.shell import actions
    with actions():
        with st.popover('Crear',icon=':material/add_circle:',help='Pedido desde receta, venta, gasto o impresión.'):
            if st.button('Desde receta',key='today_recipe',icon=':material/menu_book:',width='stretch'): recipe_order_form()
            if st.button('Nueva impresión',key='today_new_print',icon=':material/add_task:',width='stretch',help='Para un pedido, stock o prototipo, en una sola ventana.'):
                from views.capture_forms import new_print_form
                new_print_form()
            if st.button('Nueva venta',key='today_new_sale',icon=':material/point_of_sale:',width='stretch'): direct_sale_form()
            if st.button('Nuevo gasto',key='today_new_expense',icon=':material/receipt_long:',width='stretch'): expense_form()
        if st.button('Nuevo pedido',key='today_new_order',type='primary',icon=':material/add:'): order_form()
    continue_button()
    # The work areas stay on top, in the same place on every area: the page never jumps when switching.
    fronts=('Resumen','Producir','Entregar','Abastecer','Cobrar','Pagar')
    icons={'Resumen':'dashboard','Producir':'precision_manufacturing','Entregar':'local_shipping','Abastecer':'inventory','Cobrar':'south_west','Pagar':'north_east'}
    counts={'Producir':len(board['jobs']),'Entregar':len(board['deliveries']),'Abastecer':supply['attention'],'Cobrar':len(board['collections']),'Pagar':len(board['payables'])}
    if st.session_state.get('today_front') not in (None,*fronts):st.session_state['today_front']='Resumen'
    filtered=bool(st.session_state.get('today_search'))+(st.session_state.get('today_scope','Todos')!='Todos')
    with st.container(horizontal=True,vertical_alignment='center',gap='small',key='today-areas'):
        front=st.segmented_control('Área de trabajo',fronts,default=remembered('today_front', 'Resumen'),key='today_front',persist_state='session',
            width='stretch',label_visibility='collapsed',format_func=lambda f:f":material/{icons[f]}: {f}"+(f" · {counts[f]}" if counts.get(f) else '')) or 'Resumen'
        with st.popover('Filtrar'+(f' · {filtered}' if filtered else ''),icon=':material/tune:',width='content',help='Busca y acota por fecha los pedidos, cobros y pagos de todas las áreas.'):
            search=st.text_input('Buscar pendiente',placeholder='Cliente, proyecto, concepto o folio',key='today_search',persist_state='session',icon=':material/search:')
            scope=st.selectbox('Fecha',('Todos','Vencidos y hoy','Próximos 7 días'),key='today_scope',persist_state='session')
            limit=3 if front=='Resumen' else st.selectbox('Mostrar',(6,12,24,100),key='today_limit',persist_state='session')
    if search or scope!='Todos':
        with st.container(horizontal=True,vertical_alignment='center',gap='small'):
            st.caption('Consulta: ' + ' · '.join(v for v in (search,scope) if v and v!='Todos'))
            st.button('Limpiar búsqueda y fecha',key='today_clear',on_click=reset_today_filters,type='tertiary',icon=':material/filter_alt_off:')

    def matches(row,field,fields): return visible(row,search,scope,date_field=field,fields=fields)
    def date_badge(value):
        label,color=urgency(value)
        st.badge(label,color=color)
        if value: st.caption(f'Fecha: {fmt(value)}')
    def tail(rows,page):
        if not rows: st.info('No hay pendientes con estos filtros.')
        elif len(rows)>limit: st.caption(f'Mostrando {limit} de {len(rows)}. Aumenta Mostrar o ajusta los filtros.')
        st.page_link(page,label='Abrir gestión completa',icon=':material/arrow_forward:')

    if front=='Resumen':
        from views.today_brief import brief,pulse
        brief(board,snapshot,supply)
        pulse(board,supply)
        summary(board,snapshot,search,scope,limit,supply)
    elif front=='Abastecer':
        mode=st.segmented_control('Abastecimiento',('Por pedir','Por recibir','Todo'),default='Por pedir',key='today_supply_mode',persist_state='session', format_func=tag) or 'Por pedir'
        source={'Por pedir':supply['to_order'],'Por recibir':supply['arriving'],'Todo':supply['rows']}[mode]
        rows=[r for r in source if matches(r,'expected',('title','detail','kind','state'))]
        st.caption('Faltantes de insumos por pieza y consumibles (filamento contra la cola), y pedidos de compra abiertos. Los vencidos primero.')
        for row in rows[:limit]:supply_row(row,'today_supply')
        tail(rows,'views/collection.py')
    elif front=='Producir':
        mode=st.segmented_control('Pendientes de producción',('Trabajos','Máquinas','Piezas sin asignar','Pedidos por definir'),default='Trabajos',
                      key='today_production_mode',persist_state='session', format_func=tag) or 'Trabajos'
        if mode=='Máquinas':
            # Each printer with what it is doing and what comes next: start it or open its queue.
            from services.timeline import machine_timeline,availability_text
            machines=snapshot['machines']
            for start in range(0,len(machines),3):
                for col,machine in zip(st.columns(3),machines[start:start+3]):
                    with col,st.container(border=True,gap='xsmall',key=f"panel-today-machine-{machine['id']}"):
                        st.markdown(f"**{machine['code']}** :gray[· {machine['name']}]")
                        status_badge(machine['status'])
                        st.caption(availability_text(machine_timeline(machine,snapshot['jobs'])['availability']))
                        current,nxt=machine['current_job'],machine['next_job']
                        if current:st.caption(f"Imprimiendo {current['part_name']} · faltan {current['quantity_remaining']}")
                        elif nxt and machine['status']=='Disponible':
                            st.caption(f"Siguiente: {nxt['part_name']} ×{nxt['quantity_remaining']} · {nxt['project']}")
                            if st.button('Iniciar siguiente',key=f'today_start_{machine["id"]}',type='primary',icon=':material/play_arrow:',width='stretch'):
                                perform(production.job_action,nxt['id'],'start',expected_revision=nxt['updated_at'],message='Trabajo iniciado.')
                        else:st.caption('Sin impresión lista para iniciar.')
                        if st.button('Ver su cola',key=f'today_machine_queue_{machine["id"]}',type='tertiary',icon=':material/arrow_forward:'):open_queue(machine_id=machine['id'])
            st.page_link('views/machines.py',label='Administrar máquinas',icon=':material/settings:')
        elif mode=='Trabajos':
            rows=[j for j in board['jobs'] if matches(j,'deadline',('code','project','client','item_name','part_name','machine_code'))]
            st.caption('En marcha y pausados primero. La fecha del filtro corresponde a la entrega del pedido.')
            for job in rows[:limit]: job_card(job,f'hub_job_{job["id"]}',details=True)
            tail(rows,'views/queue.py')
        elif mode=='Piezas sin asignar':
            owners={r['id']:r for r in daily['orders']}
            rows=[dict(p,deadline=owners[p['order_id']]['deadline'],client=owners[p['order_id']]['client']) for p in daily['unassigned']]
            rows=[r for r in rows if matches(r,'deadline',('order_code','client','item_name','name','material'))]
            for part in rows[:limit]:
                kind=order_kind(owners[part['order_id']])
                with st.container(border=True,key=f"panel-order-{order_tone(part['order_id'],kind)[0]}-hub-part-{part['id']}"):
                    st.write(f"**{part['name']} · {part['quantity_unassigned']} sin asignar**")
                    with st.container(horizontal=True,gap='xsmall',vertical_alignment='center'):
                        order_chip(part['order_code'],part['order_id'],kind,help=part['project'])
                        st.caption(f"{part['item_name']} · {part['material']}")
                    date_badge(part['deadline'])
                    with st.container(horizontal=True):
                        if st.button('Asignar',key=f'hub_split_{part["id"]}',type='primary',icon=':material/call_split:',disabled=owners[part['order_id']]['status']=='Bloqueado',
                                     help='Abre el pedido en su vista Asignar con esta pieza elegida.'): open_assign(part)
                        if st.button('Abrir pedido',key=f'hub_part_order_{part["id"]}'): open_order(part['order_id'])
            tail(rows,'views/orders.py')
        else:
            rows=[r for r in daily['missing'] if matches(r,'deadline',('code','client','project'))]
            for row in rows[:limit]:
                with st.container(border=True):
                    st.write(f"**{row['code']} · {row['project']}**")
                    st.caption('Agrega items o reutiliza un despiece para definir qué fabricar.')
                    if st.button('Definir pedido',key=f'hub_define_{row["id"]}',type='primary'): open_order(row['id'])
            tail(rows,'views/orders.py')
    elif front=='Entregar':
        rows=[r for r in board['deliveries'] if matches(r,'deadline',('code','client','project'))]
        st.caption('Fechas vencidas y de hoy primero. Revisión y empaque son checks manuales; la entrega se confirma por separado.')
        for row in rows[:limit]:
            route=tracking(row)
            kind=order_kind(row)
            with st.container(border=True,gap='xsmall',key=f"panel-order-{order_tone(row['id'],kind)[0]}-hub-delivery-{row['id']}"):
                # Who and when on one line, the state on the next, then the next step: the same reading order as Resumen.
                with st.container(horizontal=True,gap='xxsmall',vertical_alignment='center'):
                    order_chip(f"{row['code']} · {row['client'] or 'Sin cliente'}",row['id'],kind)
                    status_badge(row['status'])
                    st.badge(route['lane'],color='green' if route['lane']=='Salida' else 'blue',icon=':material/route:')
                    st.space('stretch')
                    label,color=urgency(row['deadline'])
                    st.badge(f"{label} · {fmt(row['deadline'])}" if row['deadline'] else label,color=color,icon=':material/event:')
                st.markdown(f"**{row['project']}**")
                st.markdown(f":material/arrow_right_alt: **{route['action']}**")
                order_checklist(row,'hub_delivery',detailed=True,actions=True)
                with st.container(horizontal=True):
                    if row['status']=='Listo':
                        needed=('revision',) if row['fulfillment']=='Stock' else tuple(operations.STAGES)
                        next_stage=next((key for key in needed if not row['stages'][key]['checked_at']),None)
                        if st.button('Cerrar lote' if row['fulfillment']=='Stock' else 'Entregar',key=f'hub_deliver_{row["id"]}',type='primary' if not next_stage else 'secondary'):
                            deliver_dialog(row)
                    else:
                        from services.workflow import next_step
                        st.caption(next_step(row)['detail'])
                    if st.button('Abrir pedido',key=f'hub_delivery_order_{row["id"]}',icon=':material/open_in_new:'): open_order(row['id'])
        tail(rows,'views/orders.py')
    else:
        collecting=front=='Cobrar'
        rows=[r for r in board['collections' if collecting else 'payables'] if matches(r,'due_on',
              ('code','client','project') if collecting else ('code','concept','supplier'))]
        st.caption('Primero vencidos, después vencimientos próximos y registros sin fecha. Captura el importe realmente recibido o pagado.')
        for row in rows[:limit]:
            with st.container(border=True,gap='xsmall',key=f"panel-money-{front.lower()}-{row['id']}"):
                with st.container(horizontal=True,vertical_alignment='center',gap='small'):
                    st.markdown(f"**{row['code']} · {row['client'] if collecting else row['concept']}**  \n:gray[{(row['project'] or 'Sin referencia') if collecting else (row['supplier'] or 'Sin proveedor')}]",width='stretch')
                    label,color=urgency(row['due_on'])
                    st.badge(f"{label} · {fmt(row['due_on'])}" if row['due_on'] else label,color=color,icon=':material/event:')
                    st.markdown(f"#### {money(row['balance_cents'])}",width='content',help='Por cobrar' if collecting else 'Por pagar')
                with st.container(horizontal=True):
                    if st.button('Registrar cobro' if collecting else 'Registrar pago',key=f'hub_{"collect" if collecting else "pay"}_{row["id"]}',type='primary',icon=':material/payments:'):
                        if collecting: sale_payment_form(row)
                        else: expense_payment_form(row)
                    if st.button('Abrir venta' if collecting else 'Abrir gasto',key=f'hub_money_open_{front}_{row["id"]}',icon=':material/open_in_new:'):
                        open_record('Venta' if collecting else 'Gasto',row['id'])
        tail(rows,'views/sales.py' if collecting else 'views/expenses.py')
