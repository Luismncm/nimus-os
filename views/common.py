from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, time
from functools import wraps

import pandas as pd
import streamlit as st

from models.constants import JOB_STATUSES, PRIORITIES, PROCESSES
from services import production as service
from services.workflow import even_split
from views.navigation import focus_item, focus_part, select_order
from views.properties import property_select
from views.emoji import tag


_DIALOGS = {}
_OWNERS = {}


def _close_dialog() -> None:
    st.session_state.pop("active_dialog",None)


def managed_dialog(title: str, **options):
    """Keep a form open across full reruns, including refreshes from other UI."""
    def decorate(function):
        @wraps(function)
        def contents(*args, **kwargs):
            if flash := st.session_state.pop('dialog_flash',None):
                st.success(flash)
            return function(*args, **kwargs)
        # Dialogs are reopened by name on every rerun: two modules with the same name would swap forms.
        owner = _OWNERS.setdefault(function.__name__, function.__module__)
        if owner != function.__module__:
            raise RuntimeError(f"Diálogo duplicado «{function.__name__}» en {owner} y {function.__module__}; renombra uno.")
        _DIALOGS[function.__name__] = st.dialog(title,on_dismiss=_close_dialog,**options)(contents)

        @wraps(function)
        def open_form(*args,**kwargs):
            st.session_state["active_dialog"] = (function.__name__,args,kwargs)
            st.session_state['dialog_request_key'] = uuid.uuid4().hex
            st.session_state.pop('recipe_quote_signature',None)
            st.rerun()
        return open_form
    return decorate


def request_key() -> str:
    """The open dialog's request key: one per form opening, so a double click saves once."""
    return st.session_state['dialog_request_key']


def remembered(key: str, default):
    """A widget's default only until the person picks something; afterwards their choice stays."""
    return None if key in st.session_state else default


def reason_form(form_key: str, title: str, note: str, button: str, action, *, placeholder: str = '') -> None:
    """A correction that keeps history: what it affects, what it does, a required reason and one confirm button.

    `action(reason)` runs through perform, so its message and errors look like any other save.
    """
    st.markdown(title)
    st.caption(note)
    with st.form(form_key):
        reason = st.text_input('Motivo *', placeholder=placeholder)
        if st.form_submit_button(button, type='primary', width='stretch'):
            action(reason)


def render_dialog() -> None:
    for key, value in st.session_state.pop('dialog_reset', {}).items():
        if value is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = value
    if active := st.session_state.get("active_dialog"):
        name,args,kwargs = active
        _DIALOGS[name](*args,**kwargs)


def perform(operation, *args, message: str = "Cambios guardados.", after=None, navigate: str | None = None, keep_open=False, reset_fields=None, **kwargs) -> None:
    try:
        with st.spinner('Guardando cambios…'):
            result = operation(*args,**kwargs)
    except (ValueError,sqlite3.IntegrityError) as exc:
        st.error(str(exc))
        return
    except sqlite3.OperationalError:
        st.error("No se pudo guardar. La base puede estar ocupada; actualiza la vista e inténtalo de nuevo.")
        return
    st.session_state['dialog_flash' if keep_open else 'flash'] = message
    if keep_open:
        st.session_state['dialog_reset'] = reset_fields or {}
    else:
        _close_dialog()
    if after:
        after(result)
    if navigate:
        st.switch_page(navigate)
    st.rerun()


def dataframe(frame, rows: list[dict], *, label: str, config: dict, open=None, key: str | None = None) -> None:
    """A table; with open, picking a row hands that row to open, so a listing reaches its record in one click.

    The selection is spent once: the table takes a fresh key afterwards, so coming back to the listing
    never reopens the same record.
    """
    if not open:
        st.dataframe(frame,hide_index=True,width="stretch",column_config=config,alt=label)
        return
    key = key or 'pick_' + label
    generation = st.session_state.get(key + '_gen', 0)
    event = st.dataframe(frame,hide_index=True,width="stretch",column_config=config,alt=label,
                         key=f'{key}_{generation}',on_select='rerun',selection_mode='single-row')
    if picked := event.selection.rows:
        st.session_state[key + '_gen'] = generation + 1
        open(rows[picked[0]])


def picks(key: str, field: str = 'id'):
    """The open for a table with a list below it: the picked row becomes that list's choice (its widget key)."""
    return lambda row: st.session_state.__setitem__(key, row[field])


def table(rows: list[dict], columns: dict[str,str], *, label: str, progress_column: str | None = None, open=None, key: str | None = None) -> None:
    if not rows:
        st.caption("Sin registros.")
        return
    from views.emoji import STATE_COLUMNS, status
    frame = pd.DataFrame(rows).reindex(columns=list(columns))
    for field in STATE_COLUMNS:
        if field in frame: frame[field] = frame[field].map(status)
    frame = frame.rename(columns=columns)
    config = {}
    if progress_column:
        config[columns[progress_column]] = st.column_config.ProgressColumn(min_value=0,max_value=100,format="%.1f%%")
    dataframe(frame,rows,label=label,config=config,open=open,key=key)


ORDER_COLUMNS = {"code":"Pedido","client":"Cliente","project":"Proyecto","deadline":"Entrega","priority":"Prioridad",
                 "operational_status":"Estado","manufacturing_progress":"Fabricación", "fabrication_label":"Avance de fabricación",
                 "manufacturing_remaining":"Por fabricar","supplies_remaining":"Insumos por reservar"}
JOB_COLUMNS = {"code":"Trabajo","machine_code":"Máquina","project":"Proyecto","part_name":"Pieza","process":"Proceso",
               "quantity":"Asignadas","quantity_completed":"Terminadas","status":"Estado","priority":"Prioridad","schedule":"Horario"}


def job_table(jobs: list[dict], label: str, *, open=None, key: str | None = None) -> None:
    from services.timeline import slot
    from views.timeline_ui import slot_line
    table([dict(j,schedule=slot_line(slot(j)) if j['status']!='Terminado' else 'Terminado') for j in jobs],JOB_COLUMNS,label=label,open=open,key=key)


def job_actions(job: dict, key: str) -> None:
    if job.get("commercial_cancelled"):
        st.caption("Pedido cancelado · histórico de solo lectura.")
        return
    if job["order_status"] == "Entregado":
        st.caption("Producción de un pedido entregado · solo lectura.")
        if st.button('Corregir costo',key=key+'_actual_cost',icon=':material/payments:'):
            from views.quality_forms import consumption_form
            consumption_form(job)
        return
    if job.get("rides_on") and job["status"] != "Terminado":
        # Its host print starts and finishes it; the only decision left is to take it out.
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            st.caption(f"Se termina con {job['rides_on']['code']}.")
            if st.button("Separar", key=f"{key}_detach", icon=":material/link_off:",
                         help="Sus unidades vuelven a quedar por asignar y regresan al excedente de esa impresión."):
                from services.piece_stock import detach_rider
                perform(detach_rider, job["id"], message="Separado: sus unidades vuelven a estar por asignar.")
        return
    states = {
        "En cola":[("Iniciar","start"),(f"Terminar (+{job['quantity_remaining']})","finish"),("Bloquear","block")],
        "En producción":[(f"Terminar (+{job['quantity_remaining']})","finish"),("Pausar","pause"),("Bloquear","block")],
        "Pausado":[("Reanudar","start"),(f"Terminar (+{job['quantity_remaining']})","finish"),("Bloquear","block")],
        "Bloqueado":[("Liberar a cola","unblock")],"Terminado":[]}
    snapshot = st.session_state["snapshot"]
    machine = next((m for m in snapshot["machines"] if m["id"] == job["machine_id"]), None)
    unavailable = job["order_blocked"] or (machine and machine["status"] != "Disponible")
    primary = states[job["status"]][:1]
    secondary = states[job["status"]][1:]
    with st.container(horizontal=True, gap="small"):
        if job["status"] == "En producción" and st.button("Avance", key=f"{key}_progress", type="primary", icon=":material/add_task:"):
            progress_form(job)
        for label,action in primary:
            if st.button(label,key=f"{key}_{action}",type="secondary" if action == "finish" else "primary",
                         icon=f":material/{'done_all' if action == 'finish' else 'lock_open' if action == 'unblock' else 'play_arrow'}:",
                         disabled=bool(action == "start" and unavailable)):
                perform(service.job_action,job["id"],action,expected_revision=job["updated_at"])
        if job["status"] not in ("Terminado", "En producción") and st.button("Avance", key=f"{key}_progress", icon=":material/add_task:"):
            progress_form(job)
        if job.get('started_at') and st.button('Falla',key=key+'_failure',icon=':material/report_problem:'):
            from views.quality_forms import failure_form
            failure_form(job)
        with st.popover("Más", icon=":material/more_horiz:"):
            # Work actions first; actions that stop or remove the print last, after a divider.
            icons = {"finish": "done_all", "pause": "pause", "block": "block"}
            for label,action in [s for s in secondary if s[1] != "block"]:
                if st.button(label, key=f"{key}_{action}", width="stretch", icon=f":material/{icons[action]}:"):
                    perform(service.job_action,job["id"],action,expected_revision=job["updated_at"])
            if st.button('Corregir costo',key=key+'_actual_cost',width='stretch',icon=':material/payments:'):
                from views.quality_forms import consumption_form
                consumption_form(job)
            if job.get('latest_failure_id') and job['quantity_remaining']>0 and job['status']!='En producción' and job.get('reprint_status') not in ('Pendiente','En curso'):
                if st.button('Reimprimir pendientes',key=key+'_reprint',width='stretch',icon=':material/replay:'):
                    from views.quality_forms import reprint_form
                    reprint_form(job)
            if st.button("Editar trabajo",key=f"{key}_edit",width="stretch",icon=":material/edit:"):
                job_form(snapshot,job=job)
            st.divider()
            for label,action in [s for s in secondary if s[1] == "block"]:
                if st.button(label, key=f"{key}_{action}", width="stretch", icon=":material/block:"):
                    perform(service.job_action,job["id"],action,expected_revision=job["updated_at"])
            if st.button("Eliminar trabajo", key=f"{key}_delete", width="stretch", icon=":material/delete:"):
                delete_dialog("job", job)
    if job["status"] in ("En cola", "Pausado") and unavailable:
        st.caption("Inicio pendiente: libera el bloqueo del pedido." if job["order_blocked"] else
                   f"Inicio pendiente: {machine['code']} está {machine['status'].lower()}.")


@managed_dialog("Registrar avance", width="small")
def progress_form(job: dict) -> None:
    st.write(f"**{job['code']} · {job['part_name']}**")
    st.caption(f"{job['project']} · {job['machine_code'] or 'Fuera de impresora'}")
    key = f"progress_total_{job['id']}"
    # Start from what is recorded each time the job changes, not from an old visit to this window.
    if st.session_state.get(key + '_rev') != job['updated_at']:
        st.session_state.update({key: job['quantity_completed'], key + '_rev': job['updated_at']})
    def set_total(value):
        st.session_state[key] = max(0, min(job['quantity'], value))
    completed = st.number_input("Unidades buenas en total", min_value=0, max_value=job["quantity"], step=1, key=key, icon=':material/check_circle:')
    with st.container(horizontal=True, gap='xsmall'):
        st.button('+1', key=key + '_plus', on_click=set_total, args=(completed + 1,), disabled=completed >= job['quantity'])
        st.button(f"Todas · {job['quantity']}", key=key + '_all', on_click=set_total, args=(job['quantity'],), disabled=completed >= job['quantity'])
    added = completed - job['quantity_completed']
    st.caption(f"Lote de {job['quantity']}. Ya registradas: {job['quantity_completed']}"
               + (f" · este registro suma {added}" if added > 0 else f" · este registro corrige {added}" if added < 0 else '')
               + ('. Al completar el lote se libera la máquina.' if completed == job['quantity'] else '.'))
    if st.button("Registrar avance", type="primary", width="stretch", key=key + '_save'):
        perform(service.record_progress, job["id"], completed, expected_revision=job["updated_at"], message="Avance registrado.")


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        st.warning(f"Fecha anterior no válida: {value}. Selecciona la fecha correcta al guardar.")
        return None


@managed_dialog("Pedido",width="medium")
def order_form(order: dict | None = None) -> None:
    row = order or {}
    with st.form("order_form"):
        a,b = st.columns(2)
        project = a.text_input("Proyecto *",value=row.get("project",""),key="order_project")
        client = property_select("Cliente", "client", current=row.get("client", ""), key="order_client", container=b)
        deadline = a.date_input("Fecha límite",value=_date(row.get("deadline")),key="order_deadline")
        priority = b.selectbox("Prioridad",PRIORITIES,index=PRIORITIES.index(row.get("priority","Media")),key="order_priority")
        notes = st.text_area("Notas",value=row.get("notes",""),key="order_notes")
        if st.form_submit_button("Guardar pedido",type="primary"):
            values = dict(project=project,client=client,deadline=deadline.isoformat() if deadline else "",priority=priority,notes=notes)
            if order:
                perform(service.update_order,order["id"],**values)
            else:
                perform(service.create_order, after=select_order, navigate="views/orders.py", message="Pedido creado. Agrega su primer item.", **values)


@managed_dialog("Producto del pedido")
def item_form(order_id: int, item: dict | None = None) -> None:
    row = item or {}
    if not item:
        from services.templates import reusable_items, clone_item
        templates = {r['id']: r for r in reusable_items()}
        mode = st.segmented_control('Cómo agregar', ['Nuevo', 'Reutilizar despiece'], default='Nuevo', key='item_mode', format_func=tag)
        if mode == 'Reutilizar despiece':
            if not templates:
                st.info('Guarda un producto con piezas para reutilizar aquí su despiece completo.')
                return
            sid = st.selectbox('Producto anterior', list(templates), key='item_template',
                format_func=lambda k: f"{templates[k]['name']} · {templates[k]['order_code']} · {templates[k]['part_count']} piezas")
            st.caption('Conserva nombres, material y proceso. Multiplica las piezas por la nueva cantidad de producto.')
            with st.form('reuse_item'):
                quantity = st.number_input('Cantidad de producto', min_value=1, value=1, step=1, key='reuse_item_quantity')
                if st.form_submit_button('Agregar producto con sus piezas', type='primary', width='stretch'):
                    perform(clone_item, order_id, sid, quantity, after=focus_item, message='Producto y despiece agregados. Listos para repartir.')
            return
    with st.form("item_form"):
        name = property_select("Nombre del producto / modelo *", "product", current=row.get("name", ""), key="item_name")
        quantity = st.number_input("Cantidad de producto",min_value=1,value=row.get("quantity",1),step=1,key="item_quantity")
        notes = st.text_input("Notas",value=row.get("notes",""),key="item_notes")
        collection = st.checkbox("Producir para inventario de Colección Origen", value=row.get('collection') == 'Origen', key='item_collection')
        st.caption("Origen: las unidades buenas de Impresión 3D y Resina ingresan por pieza al inventario. Usa el mismo nombre de modelo para acumular varios lotes.")
        st.caption("Cambiar la cantidad de producto conserva las cantidades de piezas. Revisa el despiece después de editarla.")
        if st.form_submit_button("Guardar producto",type="primary"):
            if item:
                perform(service.update_item,item["id"],name,quantity,notes,collection='Origen' if collection else '')
            else:
                perform(service.create_item,order_id,name,quantity,notes,collection='Origen' if collection else '',after=focus_item,message="Item creado. Define ahora sus piezas.")


@managed_dialog("Pieza",width="medium")
def part_form(item: dict, part: dict | None = None) -> None:
    row = part or {}
    st.caption(f"{item['code']} · {item['name']} ×{item['quantity']}")
    if not part:
        from services.templates import reusable_parts
        templates = {row['key']: row for row in reusable_parts()}
        mode = st.segmented_control('Cómo agregar', ['Nueva', 'Reutilizar pieza'], default='Nueva', key='part_mode', format_func=tag)
        if mode == 'Reutilizar pieza':
            if not templates:
                st.info('Agrega tu primera pieza o créala desde Catálogo para reutilizar sus propiedades.')
                return
            sid = st.selectbox('Pieza guardada', list(templates), key='part_template',
                format_func=lambda k: ' · '.join(str(templates[k][f]) for f in ('name','material','process','notes') if templates[k][f]))
            source = templates[sid]
            st.caption(f"{source['material'] or 'Sin material'} · {source['process']} · se conservan las propiedades de la pieza.")
            with st.form(f'reuse_part_{sid}'):
                units = st.number_input('Unidades por producto', min_value=1, value=int(source['units']), step=1, key=f'reuse_part_units_{sid}')
                st.caption(f"Se multiplicará por los {item['quantity']} productos de este item.")
                save = st.form_submit_button('Agregar pieza', type='primary')
                again = st.form_submit_button('Agregar y continuar', icon=':material/add:')
                if save or again:
                    perform(service.create_part, item['id'], source['name'], units*item['quantity'], source['process'], source['material'], source['notes'],
                            keep_open=again, after=lambda identity: focus_part(item['id'],identity), message='Pieza agregada con sus propiedades.')
            return
    with st.form("part_form"):
        a,b = st.columns(2)
        # The stored name, not the one shown with its model.
        name = property_select("Nombre de pieza *", "part", current=row.get("base_name", row.get("name", "")), key="part_name", container=a)
        quantity = b.number_input("Total de piezas para este producto",min_value=1,value=row.get("quantity_required",item["quantity"]),step=1,key="part_quantity")
        process = a.selectbox("Proceso",PROCESSES,index=PROCESSES.index(row.get("process",PROCESSES[0])),key="part_process")
        material = property_select("Material", "material", current=row.get("material", ""), key="part_material", container=b)
        notes = st.text_area("Notas",value=row.get("notes",""),key="part_notes")
        st.caption("Ejemplo: 10 lámparas con 1 base cada una requieren 10 bases. Esta cantidad ya es el total.")
        save = st.form_submit_button("Guardar pieza",type="primary", icon=':material/check:')
        again = st.form_submit_button('Guardar y agregar otra', icon=':material/add:') if not part else False
        if save or again:
            if part:
                perform(service.update_part,part["id"],name,quantity,process,material,notes)
            else:
                perform(service.create_part,item["id"],name,quantity,process,material,notes,
                        keep_open=again, reset_fields={'part_name': None, 'part_notes': ''},
                        after=lambda identity: focus_part(item['id'],identity), message='Pieza guardada. Puedes agregar la siguiente.')


@managed_dialog("Trabajo de producción",width="medium")
def job_form(snapshot: dict, part: dict | None = None, job: dict | None = None) -> None:
    row = job or {}
    candidates = [p for p in snapshot["parts"] if p["order_status"] != "Entregado" and
                  (p["quantity_unassigned"] > 0 or (job and p["id"] == job["part_id"]))]
    if not candidates:
        st.info("No hay piezas con unidades sin asignar. Agrega una pieza o ajusta sus trabajos.")
        return
    lookup = {p["id"]:p for p in candidates}
    selected = (part or {}).get("id") or row.get("part_id")
    part_id = st.selectbox("Pieza",list(lookup),index=list(lookup).index(selected) if selected in lookup else 0,
                          format_func=lambda pid:f"{lookup[pid]['code']} · {lookup[pid]['project']} · {lookup[pid]['item_name']} → {lookup[pid]['name']} · {lookup[pid]['material'] or 'Sin material'} · {lookup[pid]['process']}",
                          disabled=bool(part or job),key=f"job_part_{row.get('id','new')}")
    chosen = lookup[part_id]
    available = chosen["quantity_unassigned"] + row.get("quantity",0)
    st.caption(f"{available} unidades disponibles para este trabajo · {chosen['process']}")
    machines = {None:"Sin máquina / fuera de impresora",**{m["id"]:f"{m['code']} · {m['status']}" for m in snapshot["machines"]}}
    if row.get('machine_id') not in machines:
        st.info('Este trabajo pertenece a una máquina archivada. Reactívala desde Máquinas para editar el trabajo.')
        return
    with st.form(f"job_form_{part_id}_{row.get('id','new')}"):
        a,b,c = st.columns(3)
        quantity = a.number_input("Cantidad del trabajo",min_value=1,value=row.get("quantity",max(1,available)),step=1,key=f"job_quantity_{part_id}")
        machine_id = b.selectbox("Máquina",list(machines),index=list(machines).index(row.get("machine_id")),format_func=lambda mid:machines[mid],key=f"job_machine_{part_id}")
        priority = c.selectbox("Prioridad del trabajo",PRIORITIES,index=PRIORITIES.index(row.get("priority",chosen["order_priority"])),key=f"job_priority_{part_id}")
        if job:
            status = a.selectbox("Estado",JOB_STATUSES,index=JOB_STATUSES.index(job["status"]),key=f"job_status_{job['id']}")
            completed = b.number_input("Unidades terminadas",min_value=0,value=job["quantity_completed"],step=1,key=f"job_completed_{job['id']}")
            st.caption("Registra unidades buenas. Un avance parcial conserva las restantes; al completar la cantidad se marca Terminado.")
        else:
            status,completed = "En cola",0
        from views.planning_forms import plan_fields
        from services.planning import get as get_plan,defaults as plan_defaults
        plan_row=get_plan(job['id']) if job else plan_defaults()
        plan=plan_fields(plan_row,f"job_plan_{part_id}")
        with st.expander('Fin manual · opcional',key=f'job_manual_end_{part_id}',on_change='ignore'):
            st.caption('Se utiliza si todavía no capturas la duración. Al tener inicio y duración, el fin se calcula automáticamente.')
            end=row.get('expected_end')
            a,b=st.columns(2)
            end_date=a.date_input('Fin manual · fecha opcional',value=_date(end),key=f'job_date_{part_id}')
            initial_time=datetime.fromisoformat(end).time() if end else time(18)
            end_time=b.time_input('Fin manual · hora',value=initial_time,key=f'job_time_{part_id}')
        notes = st.text_area("Notas del trabajo",value=row.get("notes",""),key=f"job_notes_{part_id}")
        extra = None
        if row.get("extra_posted"):
            st.caption(f":material/add_box: Sus {row['extra']} unidades extra ya entraron a inventario.")
        elif chosen["process"] in ("Impresión 3D","Resina") and not next((o for o in snapshot["orders"] if o["id"] == chosen["order_id"]),{}).get("development"):
            extra = int(st.number_input("Unidades extra para inventario",min_value=0,max_value=1000,value=row.get("extra",0),step=1,key=f"job_extra_{part_id}",
                                        help="Se imprimen además de la cantidad del trabajo y entran a Colección en Inventario al terminar."))
        if st.form_submit_button("Guardar trabajo",type="primary"):
            expected = datetime.combine(end_date,end_time).isoformat(timespec="minutes") if end_date else ""
            if job:
                perform(service.update_job,job["id"],quantity=quantity,quantity_completed=completed,status=status,machine_id=machine_id,
                        priority=priority,expected_end=expected,notes=notes,expected_revision=job["updated_at"],plan=plan,expected_plan_revision=plan_row["revision"],extra=extra)
            else:
                perform(service.create_jobs,part_id,[{"quantity":quantity,"machine_id":machine_id,"extra":extra or 0}],priority=priority,expected_end=expected,notes=notes,plan=plan)


@managed_dialog("Despiece rápido", width="medium")
def parts_form(item: dict) -> None:
    st.write(f"**{item['name']} ×{item['quantity']}**")
    mode=st.segmented_control('Captura de piezas',('Lista rápida','Tabla detallada'),default='Lista rápida',key=f'parts_mode_{item["id"]}', format_func=tag) or 'Lista rápida'
    if mode=='Tabla detallada':
        st.caption(f"Define unidades por producto. El total se multiplicará por {item['quantity']} productos al guardar.")
        with st.form(f'parts_grid_form_{item["id"]}'):
            edited=st.data_editor([dict(name='',units=1,process='Impresión 3D',material='')],num_rows='dynamic',hide_index=True,
                key=f'parts_grid_{item["id"]}',column_config={
                    'name':st.column_config.TextColumn('Pieza',required=True),
                    'units':st.column_config.NumberColumn('Por producto',min_value=1,step=1,required=True),
                    'process':st.column_config.SelectboxColumn('Proceso',options=PROCESSES,required=True),
                    'material':st.column_config.TextColumn('Material')},alt='Piezas por producto para agregar al pedido')
            st.caption('Cada fila puede tener material, proceso y cantidad distintos. Completa el nombre de cada pieza.')
            if st.form_submit_button('Agregar piezas de la tabla',type='primary'):
                data=[r for r in edited if str(r.get('name') or '').strip()]
                perform(service.create_part_rows,item['id'],data,after=lambda result:focus_part(item['id'],result[0]),message='Piezas agregadas. Selecciona una para repartir o producir.')
        return
    st.caption("Agrega varias piezas que comparten proceso, material y cantidad por producto.")
    with st.form("batch_parts_form"):
        names = st.text_area("Nombres de piezas · uno por línea", placeholder="Base\nPantalla\nTapa\nPlaca", key=f"parts_names_{item['id']}")
        a, b = st.columns(2)
        units = a.number_input("Unidades de cada pieza por producto", min_value=1, value=1, step=1, key=f"parts_units_{item['id']}")
        process = b.selectbox("Proceso", PROCESSES, key=f"parts_process_{item['id']}")
        material = property_select("Material", "material", key=f"parts_material_{item['id']}")
        clean = [name.strip() for name in names.splitlines() if name.strip()]
        st.caption(f"Las unidades por producto se multiplican por {item['quantity']} productos al guardar.")
        st.caption("Después puedes editar cada pieza por separado. Para cantidades distintas, usa Agregar pieza.")
        if st.form_submit_button("Crear despiece", key="parts_save", type="primary", width="stretch"):
            perform(service.create_parts, item['id'], clean, units, process, material, after=lambda result:focus_part(item['id'],result[0]),message="Despiece creado. Reparte las piezas para producir.")



@managed_dialog("Asignar pieza", width="large")
def split_form(part: dict) -> None:
    snapshot = st.session_state["snapshot"]
    # The window stays open between jobs: read the piece again so its pending units are current.
    part = next((p for p in snapshot["parts"] if p["id"] == part["id"]), part)
    st.write(f"**{part['name']}**")
    st.caption(f"{part['project']} → {part['item_name']} · {part['process']} · {part['material'] or 'Sin material'}")
    remaining = part["quantity_unassigned"]
    if remaining <= 0:
        st.success(f"Las {part['quantity_required']} unidades ya tienen impresión. Revisa la cola para iniciarlas.", icon=":material/check_circle:")
        return
    st.info(f"{remaining} unidades por asignar de {part['quantity_required']} requeridas.")
    mode_key = f"split_mode_{part['id']}"
    mode = st.segmented_control("Cómo asignar", ("Una impresora", "Repartir en varias"), default=None if mode_key in st.session_state else "Una impresora",
                                key=mode_key, width="stretch", format_func=tag) or "Una impresora"
    if mode == "Una impresora":
        from views.assign_panel import single_print
        single_print(snapshot, part, "split_one", keep_open=True)
        return
    machines = snapshot["machines"]
    prefix = f"split_{part['id']}_"
    from views.piece_stock_ui import stock_notice, extra_input
    stock_notice(part, prefix + "stock")
    available = [m["id"] for m in machines if m["status"] == "Disponible"]
    from services import assign_suggest
    best = assign_suggest.best(snapshot, part["material"])
    if best:
        def all_to_best():
            for m in machines:st.session_state[prefix + str(m["id"])] = remaining if m["id"] == best["machine"]["id"] else 0
            st.session_state[prefix + "external"] = 0
        a, b = st.columns([3, 2], vertical_alignment="center")
        a.markdown(f":material/auto_awesome: Sugerida: **{best['machine']['code']}** · {assign_suggest.reason(best)}")
        b.button(f"Asignar todo a {best['machine']['code']}", key=prefix + "best", icon=":material/done:", on_click=all_to_best, width="stretch")
    if st.button("Repartir entre máquinas disponibles", icon=":material/grid_view:", disabled=not available):
        amounts = even_split(remaining, available)
        for machine in machines:
            st.session_state[prefix + str(machine["id"])] = amounts.get(machine["id"], 0)
        st.session_state[prefix + "external"] = 0
    allocations = []
    columns = [column for start in range(0, len(machines), 4) for column in st.columns(min(4, len(machines)-start))]
    for column, machine in zip(columns, machines):
        with column:
            quantity = st.number_input(machine["code"], min_value=0, max_value=remaining, step=1, key=prefix + str(machine["id"]))
            # When it is free matters more than its status when deciding where units go.
            from services.timeline import machine_timeline, availability_text
            st.caption(availability_text(machine_timeline(machine, snapshot["jobs"])["availability"]) if machine["status"] == "Disponible" else machine["status"])
            if quantity:
                allocations.append({"machine_id": machine["id"], "quantity": quantity})
    external = st.number_input("Fuera de impresora / sin máquina", min_value=0, max_value=remaining, step=1, key=prefix + "external")
    if external:
        allocations.append({"machine_id": None, "quantity": external})
    total = sum(row["quantity"] for row in allocations)
    if total > remaining:
        st.error(f"Sobran {total - remaining} unidades. Reduce el reparto antes de guardar.")
    else:
        st.caption(f"{total} a repartir · {len(allocations)} trabajos · {remaining - total} quedan sin asignar")
    development = bool(next((o for o in snapshot["orders"] if o["id"] == part["order_id"]), {}).get("development"))
    if allocations and (extra := extra_input(prefix + "x", allocations[0]["quantity"], part["process"], development=development)):
        # A plate prints as one job: the extra rides on the first one.
        allocations[0]["extra"] = extra
        if len(allocations) > 1:
            st.caption(f"El excedente va en el primer trabajo ({next((m['code'] for m in machines if m['id'] == allocations[0]['machine_id']), 'sin máquina')}).")
    with st.expander("Prioridad, fecha y notas"):
        priority = st.selectbox("Prioridad", PRIORITIES, index=PRIORITIES.index(part["order_priority"]), key=prefix + "priority")
        a, b = st.columns(2)
        end_date = a.date_input("Fin estimado", value=None, key=prefix + "date")
        end_time = b.time_input("Hora", value=time(18), key=prefix + "time")
        notes = st.text_area("Notas para estos trabajos", key=prefix + "notes")
    st.caption("Se crean en cola. Una máquina ocupada puede recibir trabajos para después.")
    if st.button(f"Crear {len(allocations)} trabajos", type="primary", disabled=not allocations or total > remaining, width="stretch", key="split_save"):
        expected = datetime.combine(end_date, end_time).isoformat(timespec="minutes") if end_date else ""
        perform(service.create_jobs, part["id"], allocations, priority=priority, expected_end=expected, notes=notes,
                message=f"{len(allocations)} trabajos creados. Ya puedes iniciarlos desde la cola o las máquinas.")


@managed_dialog("Eliminar registro")
def delete_dialog(kind: str, row: dict) -> None:
    st.write(f"Eliminar {row['code']} · {row.get('name',row.get('project',''))}")
    st.caption("También se eliminarán sus registros dependientes, incluidos trabajos terminados. Se bloquea solo si ya movió piezas a inventario o tiene una falla registrada.")
    confirmed = st.checkbox("Confirmo eliminar este registro y sus dependientes",key="delete_confirm")
    if st.button("Eliminar definitivamente",disabled=not confirmed,type="primary",key="delete_execute"):
        perform(service.delete_record,kind,row["id"],message="Registro eliminado.")


@managed_dialog("Entregar pedido")
def deliver_dialog(order: dict) -> None:
    stock = order.get('fulfillment') == 'Stock'
    st.write(f"{order['code']} · {order['project']} · {order['completed_total']} componentes cubiertos" if order.get('fulfillment') != 'Personalizado' else f"{order['code']} · {order['project']} · {order['completed_total']} unidades terminadas")
    if order.get('fulfillment') != 'Personalizado':
        st.info('Las piezas reservadas quedarán disponibles en Stock.' if stock else f"Se descontarán las piezas reservadas y se registrará su entrega a {order['client']}. Esto no confirma ensamble de productos.")
    st.caption("Quedará en el histórico de pedidos entregados, visible y de solo lectura.")
    # Handing over is when the balance is collected: show what the linked sale still owes and, if asked,
    # open its payment form right after the delivery is saved.
    from services import sales as sales_service
    from services.quotations import money
    sale = None if stock else next((r for r in sales_service.list_sales() if r['order_id'] == order['id'] and r['status'] == 'Activa' and r['balance_cents'] > 0), None)
    collect = False
    if sale:
        st.warning(f"{sale['code']} tiene {money(sale['balance_cents'])} MXN por cobrar.", icon=":material/payments:")
        collect = st.checkbox("Registrar el cobro al confirmar la entrega", value=True, key="deliver_collect")
    def then_collect(_):
        if collect:
            from views.sales_forms import sale_payment_form
            sale_payment_form(sales_service.get_sale(sale['id']))
    if st.button('Cerrar lote y liberar a stock' if stock else "Confirmar entrega",type="primary",key="deliver_confirm",icon=":material/task_alt:"):
        perform(service.deliver_order,order["id"],message='Lote cerrado. Piezas disponibles en Stock.' if stock else "Pedido entregado; conservado en el histórico.",
                after=then_collect)
