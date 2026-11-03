"""One block to set up a print, the same in every window that queues one.

How many (units and extra for inventory), how long and how much filament, which printer (ranked by
loaded filament and first free slot), when it starts, the optional machine rate and the notes.
New print, assigning a piece and prototypes all use it: each datum is captured once, in the same
place and with the same control.
"""
from datetime import datetime, time, timedelta
import streamlit as st
from services import assign_suggest, consumables, resources
from services.inventory import PRINT_PROCESSES
from services.timeline import when
from utils.dates import now
from views.tags import printer_tag

EXTERNAL = 'external'
SCHEDULES = ('Primer horario libre', 'Sin horario', 'Otra fecha')


def section(title, key, icon=None):
    """A quiet tinted block that groups related fields under a short title."""
    box = st.container(key=f'section-{key}', gap='small')
    box.markdown(f"**{f':material/{icon}: ' if icon else ''}{title}**")
    return box


def material_note(material, jobs):
    if not material:
        return
    stock = next((r for r in consumables.items(jobs) if r['identity'] == consumables.identity(material)), None)
    st.caption(f":material/science: {material} · {consumables.quantity_text(stock['balance'], 'g')} disponibles · la cola ya prevé "
               f"{consumables.quantity_text(stock['committed'], 'g')} · {consumables.cost_text(stock)}" if stock else
               f":material/science: {material} no está registrado en Filamento y consumibles: no se compara con su existencia; se costea con el precio por kg de arriba.")


def quantity_row(units_key, extra_key, *, value, top=None, process='Impresión 3D', extra=True, label='Unidades'):
    """Units of the print and, beside them, extra units for inventory; one line says what gets printed."""
    can_extra = extra and process in PRINT_PROCESSES
    with st.container(horizontal=True, gap='small', vertical_alignment='bottom'):
        units = int(st.number_input(label + (f' · de {top}' if top else ''), min_value=1, max_value=top, value=min(value, top) if top else value, step=1,
                                    key=units_key, icon=':material/deployed_code:',
                                    help='Si van menos que las pendientes, el resto queda para otra impresora.' if top else None))
        more = int(st.number_input('Extra para inventario', min_value=0, max_value=1000, value=0, step=1, key=extra_key, icon=':material/add_box:',
                                   help='Se imprimen además de las necesarias. Al terminar la impresión entran a Colección en Inventario.')) if can_extra else 0
    if more:
        st.caption(f":material/add_box: Se imprimen **{units + more}**: {units} para el pedido + {more} a inventario al terminar.")
    return units, more


def _pick(state_key, value):
    st.session_state[state_key] = value


def printer_cards(snapshot, material, duration, key):
    """Printers ranked for this material as cards; returns the machine picked (None = without machine)."""
    ranked = assign_suggest.rank(snapshot, material, duration)
    state = key + '_machine'
    ids = [r['machine']['id'] for r in ranked]
    if st.session_state.get(state) not in (*ids, EXTERNAL):
        st.session_state[state] = ids[0] if ids else EXTERNAL
    chosen = st.session_state[state]
    columns = st.columns(3)
    for index, row in enumerate(ranked):
        m = row['machine']
        picked = chosen == m['id']
        with columns[index % 3], st.container(border=True, gap='xxsmall', key=f"pick-{'on' if picked else 'off'}-{key}-{m['id']}"):
            with st.container(horizontal=True, gap='xsmall', vertical_alignment='center'):
                printer_tag(m, material=False)
                if index == 0:
                    st.badge('Sugerida', color='green', icon=':material/auto_awesome:')
            loaded = m.get('loaded_material')
            fit = (':green[:material/check: cargado]' if row['match'] else
                   f":orange[:material/swap_horiz: cambiar · {loaded}]" if loaded and row['change'] else ':gray[sin filamento registrado]')
            free = 'libre ahora' if row['free'] <= now() else f"libre {when(row['free'])}"
            st.caption(f"{fit}  \n:material/schedule: {free} · {m.get('pending_units', 0)} u. en cola")
            st.button('Elegida' if picked else 'Elegir', key=f"{key}_use_{m['id']}", icon=':material/check:' if picked else None,
                      type='primary' if picked else 'secondary', width='stretch', on_click=_pick, args=(state, m['id']))
    down = [m for m in snapshot['machines'] if m['id'] not in ids]
    with st.container(horizontal=True, vertical_alignment='center', gap='small'):
        st.button('Sin máquina / externo', key=f'{key}_use_external', icon=':material/do_not_disturb_on:',
                  type='primary' if chosen == EXTERNAL else 'tertiary', on_click=_pick, args=(state, EXTERNAL))
        if down:
            st.caption('No disponibles: ' + ' · '.join(f"{m['code']} ({m['status'].lower()})" for m in down))
    return None if chosen == EXTERNAL else chosen


def schedule_picker(machine_id, duration, key):
    """Start of the print: first free slot of the printer, none, or a chosen date. Returns ISO text or None."""
    if machine_id is None:
        return None
    if not duration:
        st.caption(':material/info: Captura la duración para reservar su horario en la impresora y saber cuándo termina.')
        return None
    free = resources.first_free(0, machine_id, duration)
    options = SCHEDULES if free else SCHEDULES[1:]
    labels = {SCHEDULES[0]: f"Primer libre · {when(free)} → {when(free + timedelta(minutes=duration))}" if free else '',
              SCHEDULES[1]: 'Sin horario', SCHEDULES[2]: 'Otra fecha'}
    # Defaults go through the session so the agenda can set them (picking a free gap) without a conflicting default.
    state = f'{key}_when_{machine_id}'
    if st.session_state.get(state) not in options:
        st.session_state[state] = options[0]
    choice = st.segmented_control('Horario', options, key=state, format_func=labels.get) or options[0]
    if choice == SCHEDULES[0]:
        return free.isoformat(timespec='minutes')
    if choice == SCHEDULES[2]:
        st.session_state.setdefault(f'{key}_day', (free or now()).date())
        st.session_state.setdefault(f'{key}_hour', free.time() if free else time(9))
        a, b = st.columns(2)
        day = a.date_input('Fecha de inicio', key=f'{key}_day')
        hour = b.time_input('Hora', key=f'{key}_hour', step=900)
        return datetime.combine(day, hour).isoformat(timespec='minutes')
    return None


def print_setup(snapshot, material, key, *, process='Impresión 3D', label=''):
    """Time, filament, printer, start, rate and notes of one print; returns the values to save it.

    Under the printers, the chosen one's agenda by day shows where this print falls among the others.
    """
    printing = process in PRINT_PROCESSES
    duration = grams = rate = price = None
    if printing:
        from services.capture import material_rate
        with st.container(horizontal=True, gap='small', vertical_alignment='bottom'):
            hours = st.number_input('Duración · h', min_value=0, max_value=8760, value=0, step=1, key=key + '_hours', icon=':material/schedule:')
            minutes = st.number_input('min', min_value=0, max_value=59, value=0, step=5, key=key + '_minutes')
            grams = st.number_input('Filamento · g', min_value=0.0, value=0.0, step=5.0, key=key + '_grams', icon=':material/scale:') or None
            price = st.number_input('Filamento · MXN/kg', min_value=0.0, value=material_rate(material) / 100, step=10.0, key=key + '_price',
                                    icon=':material/sell:', help='Precio del carrete: el de Filamento y consumibles si está registrado, si no el promedio de 380.')
            rate = st.number_input('Máquina · MXN/h', min_value=0.0, value=0.0, step=5.0, key=key + '_rate', icon=':material/payments:',
                                   help='Opcional: energía y desgaste por hora. En 0 la impresión cuesta solo su filamento.')
        duration = hours * 60 + minutes or None
        cost_line(grams, price, duration, rate)
        material_note(material, snapshot['jobs'])
        st.markdown('**Impresora**')
        machine_id = printer_cards(snapshot, material, duration, key)
    else:
        st.caption(f":material/info: {process}: se registra sin impresora.")
        machine_id = None
    start = schedule_picker(machine_id, duration, key)
    if machine_id is not None:
        from views.machine_agenda import agenda
        agenda(snapshot, machine_id, key, proposal=dict(start=datetime.fromisoformat(start) if start else None, minutes=duration, label=label))
    notes = st.text_input('Notas', key=key + '_notes', placeholder='Placa, orientación, soportes…')
    return dict(machine_id=machine_id, planned_start=start, duration_minutes=duration, estimated_grams=grams, machine_rate=rate,
                material_rate=price, notes=notes)


def cost_line(grams, price, duration, rate):
    """What the print costs with these values; they are its real cost, captured once."""
    from services.quotations import money
    if not grams:
        st.caption(':material/calculate: Captura los gramos para calcular el costo de la impresión.')
        return
    material = round(grams * (price or 0) / 1000, 2)
    machine = round((duration or 0) * (rate or 0) / 60, 2)
    parts = f"{grams:g} g × {money(round((price or 0) * 100))}/kg" + (f" + {duration // 60} h {duration % 60:02d} min × {money(round(rate * 100))}/h" if rate and duration else '')
    # Escaped dollar signs: Markdown would read a pair of them as a formula.
    st.markdown(f":material/calculate: **Costo de impresión {money(round((material + machine) * 100))}** :gray[· {parts} · se usa como costo real al terminar]".replace('$', '\\$'))


def save_label(verb, units, extra, machine_id, start, snapshot):
    """'Crear trabajo · 3 + 2 en P2 · hoy 10:00': what the button will do, said on the button."""
    code = next((m['code'] for m in snapshot['machines'] if m['id'] == machine_id), 'sin máquina')
    return f"{verb} · {units}{f' + {extra}' if extra else ''} en {code}" + (f" · {when(datetime.fromisoformat(start))}" if start else '')
